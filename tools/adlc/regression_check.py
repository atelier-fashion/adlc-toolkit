#!/usr/bin/env python3
"""The regression-test check (REQ-691, architecture ADR-691-A to ADR-691-D).

Reads a project's ``bugfix.regression_test`` setting and sorts its bug reports
into passed, waived, legacy and failed. Every deterministic REQ-691 rule is
decided here; ``/bugfix`` keeps only the protocol. People and CI run it as
``adlc regression-check``; skill fences reach it through
``partials/regression-check.sh``, which runs the installed toolkit's copy::

    python3 tools/adlc/regression_check.py mode  [--root DIR]
    python3 tools/adlc/regression_check.py check [--root DIR] [--require-recorded] [BUG-nnn ...]

``--root`` is the project root, the directory holding ``.adlc/``. It defaults
to the current directory. Standard library only, plus the sibling
``harness_yaml.py``: the answer must be the same on every machine, including a
plugin install with no delegate venv and so no PyYAML (ADR-691-A).

Contract
--------
``mode`` prints a verdict line, then one line saying where the value came from::

    regression-test: required | off | error

rc 0 for ``required`` and ``off``. rc 2 for ``error``, whose second line names
the key ``bugfix.regression_test``, what was found, and the allowed values.

``check`` prints::

    regression-check: pass | fail | off | error
    passed=N waived=N legacy=N failed=N        (pass and fail only)
    BUG-nnn: <reason>[; <reason>]              (one line per failed bug)

rc 0 for pass or off, 1 for fail, 2 for error. ``off`` is followed by one line
saying regression tests are off for this project, and no bug report is opened
(BR-11). ``error`` is followed by one line saying why, and carries no counts
line: no count was made, and ``passed=0 ...`` would read as a fact about the
bugs (``lane_check.py``'s rule). **An error is never a pass and never off**
(BR-17, LESSON-581): bad arguments, an unreadable setting, a bugs directory
that cannot be listed and any exception nobody planned for all produce it.
There is no ``--help``, for the reason ``lane_check.py`` has none: an rc 0
that printed usage would read as a pass.

Output names only bug ids, report file names, the paths a report lists, repo
ids and reasons. It never carries a file's contents or the root's absolute
path, and an absolute path a report lists is named by its position instead.

The setting (ADR-691-A)
-----------------------
``.adlc/config.yml`` in the working tree. A missing file is ``off`` (BR-1). A
file whose bytes carry no ``regression_test`` outside whole-line comments is
``off`` without being parsed, by the byte prefilter ``lane_check.may_carry_lanes``
uses: a backslash (a quoted key spelled with escapes) or a NUL (a UTF-16 file)
on a non-comment line forces a parse, which is the safe direction. Anything
else is parsed by ``harness_yaml.loads``, the toolkit's stdlib closed-subset
loader. ``bugfix`` must then be a mapping whose only key is
``regression_test``, with the value ``required`` or ``off``; an absent
``bugfix``, or a ``bugfix`` without the key, is ``off``. Everything else is an
error: a file the subset refuses, a ``bugfix`` that is not a mapping, an
unknown key under it, another value, a ``regression_test`` at the top level, a
config that is a directory or a dangling symlink. A file that names the key
and fails to parse stops the caller; it is never read as ``off``.

The bug reports (ADR-691-B)
---------------------------
Without ids, every ``.adlc/bugs/BUG-*.md`` whose ``status`` is ``resolved`` or
``closed`` (the set ``/spec`` Step 1.6 uses). With ids, exactly those reports,
whatever their status; an id with no report, or with two, is a failure. A
report whose status cannot be read is checked, because it might be resolved.

Frontmatter is read by this module's own strict one-line reader, modelled on
``partials/lesson-check.sh``'s ``_alc_field``, not by ``lessons.py``'s lenient
one (which lets the last duplicate win and loses block-list items, each of
which would turn a malformed report into a silent ``legacy``). It reads
``id``, ``status``, ``regression_tests`` and ``regression_waiver`` and ignores
other keys, except that any key given twice fails the report. One of the four
keys fails the report when it is written in a spelling other than ``key: value``
at column 0, when its value continues onto the next line (a block list), when
a quote or a flow list is not closed on its line, or when its value is not the
type the System Model gives it: a flow list of strings, and a string.

Classification (BR-9): **passed** when ``regression_tests`` lists at least one
path and every path passes the path rules; **waived** when
``regression_waiver`` is non-blank and ``regression_tests`` is empty;
**legacy** when neither is present, where an empty list ``[]``, an empty
string ``""`` and an empty value all count as absent (the bug template ships
them empty); **failed** otherwise, including both fields set (BR-7) and a
whitespace-only waiver with no tests (BR-6). ``--require-recorded`` turns
legacy into failed, for ``/bugfix`` Phase 6 (BR-13).

The path rules (ADR-691-C, ADR-691-D)
-------------------------------------
Each entry is a path relative to its repository, optionally prefixed
``<repo-id>:``. A prefix resolves through ``repos.<repo-id>.path`` in the same
parse of the config, relative to the root; the primary's own id
(``primary: true``) and no prefix both mean the root. An undeclared id, an
entry with no path, and a sibling that is not cloned at its path each fail,
naming the repo. A prefix is a leading ``[A-Za-z0-9][A-Za-z0-9_.-]*:``, so a
root-level file whose name holds a colon reads as a prefix and fails loudly.

A path passes when it is not absolute, has no ``..`` segment, exists, is not a
symlink, resolves inside its repository, is a regular file, is tracked
(``git ls-files --error-unmatch`` with literal pathspecs, its output equal to
the path), and its working-tree bytes cite the bug id: ``BUG-<n>`` with no
letter or digit before it and no digit after it, so BUG-26 never matches
BUG-261. The verdict reads only the working tree and git's index. This module
never fetches, never names a remote ref and never diffs (BR-12, LESSON-782),
and git runs from a fixed argv, never through a shell.
"""

import argparse
import collections
import os
import posixpath
import re
import stat
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import harness_yaml  # noqa: E402  (sibling, pure stdlib; REQ-657 ADR-1)

# --- vocabulary -------------------------------------------------------------

MODE_REQUIRED = "required"
MODE_OFF = "off"
MODES = (MODE_REQUIRED, MODE_OFF)

MODE_LINE = "regression-test: "
CHECK_LINE = "regression-check: "
RESULT_PASS = "pass"
RESULT_FAIL = "fail"
RESULT_OFF = "off"
RESULT_ERROR = "error"

RC_PASS = 0
RC_FAIL = 1
RC_ERROR = 2

PASSED = "passed"
WAIVED = "waived"
LEGACY = "legacy"
FAILED = "failed"
CLASSES = (PASSED, WAIVED, LEGACY, FAILED)

SETTING_KEY = "bugfix.regression_test"
CONFIG_RELPATH = ".adlc/config.yml"
BUGS_RELDIR = ".adlc/bugs"
#: The statuses an unnamed run checks: the set /spec Step 1.6 already uses.
IN_SCOPE_STATUSES = ("resolved", "closed")

#: Where an ``off`` came from, so a caller can name the key that turns it on.
SOURCE_NO_CONFIG = "no-config"
SOURCE_ABSENT = "absent"
SOURCE_SET = "set"

USAGE = ("regression_check.py mode [--root DIR] | "
         "check [--root DIR] [--require-recorded] [BUG-nnn ...]")


class RegressionCheckError(Exception):
    """Anything that prevents a decision. The message is one line of reason."""


# --- output safety ------------------------------------------------------------

#: The backslash itself, C0, DEL, C1, the Arabic letter mark, zero-width and
#: directional marks, the Unicode line and paragraph separators, bidi
#: embeddings and isolates, the BOM, and lone surrogates (an undecodable byte
#: in a file name). Each is written as an escape, so a path or a reason stays
#: one printable line that no ``splitlines()`` reader splits (lane_check.py).
_UNSAFE_RE = re.compile(
    "[\\\\\x00-\x1f\x7f-\x9f؜​-‏  ‪-‮"
    "⁦-⁩﻿\ud800-\udfff]")


def _escape(match):
    char = match.group(0)
    if char == "\\":
        return "\\\\"
    code = ord(char)
    return "\\x%02x" % code if code < 0x100 else "\\u%04x" % code


def one_line(value):
    """``value`` as a single line of printable, unambiguous text."""
    return _UNSAFE_RE.sub(_escape, str(value))


def _reason(exc):
    """An OSError's reason without its file name, which may be a home path."""
    return getattr(exc, "strerror", None) or type(exc).__name__


def _type_name(value):
    if value is None:
        return "empty"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int):
        return "an integer"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "a mapping"
    return "a %s" % type(value).__name__


# --- the setting (ADR-691-A) --------------------------------------------------

#: Bytes whose presence means the config may carry the key: the word itself
#: (bare, quoted, in a flow mapping, indented or in a comment), a backslash
#: (a double-quoted key can spell it with escapes) and a NUL (a UTF-16 or
#: UTF-32 file carries the word as ``r\0e\0...``). A false positive only means
#: the file is parsed and validated, the safe direction; a false negative would
#: read a project's ``required`` as ``off``. lane_check.py's _LANES_MARKERS.
_KEY_MARKERS = (b"regression_test", b"\\", b"\x00")

#: Every character a YAML parser may treat as a line break. Splitting on a
#: superset of the parser's breaks can only turn one line into several, and a
#: fragment that does not start with ``#`` is then scanned: the safe direction.
_YAML_LINE_BREAKS = re.compile("\r\n|[\r\n\x85  ]")


def may_carry_setting(data):
    """True unless the raw config bytes certainly carry no ``regression_test``.

    Whole-line comments are skipped, so a config that only mentions the key in
    a comment is not parsed. Bytes that are not UTF-8 are never skipped: the
    markers are searched in the raw bytes.
    """
    if not any(marker in data for marker in _KEY_MARKERS):
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    if text.startswith("﻿"):
        text = text[1:]
    for line in _YAML_LINE_BREAKS.split(text):
        if line.lstrip(" \t").startswith("#"):
            continue
        if any(marker.decode("ascii") in line for marker in _KEY_MARKERS):
            return True
    return False


class Setting(object):
    """The resolved mode, where it came from, and the parsed config (or None)."""

    __slots__ = ("mode", "source", "document")

    def __init__(self, mode, source, document):
        self.mode = mode
        self.source = source
        self.document = document


def _setting_error(detail):
    return RegressionCheckError(
        "%s (%s: the allowed values are %s; a setting that cannot be read is "
        "never taken as off)" % (detail, SETTING_KEY,
                                 " and ".join("'%s'" % m for m in MODES)))


def _describe(value):
    if isinstance(value, str):
        return "'%s'" % value
    if isinstance(value, (bool, int)):
        return "%s (%s)" % (value, _type_name(value))
    return _type_name(value)


def _parse_config(data):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _setting_error("%s is not UTF-8 text" % CONFIG_RELPATH)
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace("\r\n", "\n")
    try:
        return harness_yaml.loads(text, CONFIG_RELPATH)
    except harness_yaml.YamlError as exc:
        raise _setting_error("the config does not parse (%s)" % exc)


def setting_from_document(document):
    """``(mode, source)`` from a parsed config; raises on anything else."""
    if not isinstance(document, dict):
        raise _setting_error("%s is %s, not a mapping"
                             % (CONFIG_RELPATH, _type_name(document)))
    if "regression_test" in document:
        raise _setting_error("regression_test is a top-level key in %s; it "
                             "belongs under bugfix:" % CONFIG_RELPATH)
    if "bugfix" not in document:
        return MODE_OFF, SOURCE_ABSENT
    section = document["bugfix"]
    if not isinstance(section, dict):
        raise _setting_error("bugfix in %s is %s; it must be a mapping holding "
                             "regression_test" % (CONFIG_RELPATH, _type_name(section)))
    unknown = [key for key in section if key != "regression_test"]
    if unknown:
        raise _setting_error("unknown key%s %s under bugfix in %s (bugfix holds "
                             "only regression_test)" % (
                                 "s" if len(unknown) > 1 else "",
                                 ", ".join("'%s'" % k for k in unknown),
                                 CONFIG_RELPATH))
    if "regression_test" not in section:
        return MODE_OFF, SOURCE_ABSENT
    value = section["regression_test"]
    if isinstance(value, str) and value in MODES:
        return value, SOURCE_SET
    raise _setting_error("%s in %s is %s" % (SETTING_KEY, CONFIG_RELPATH, _describe(value)))


def read_setting(root):
    """The project's :class:`Setting`. Raises :class:`RegressionCheckError`.

    A missing config is ``off``. One that exists but cannot be read, or is not
    a regular file (a directory, a symlink that does not resolve), is an error,
    never ``off`` (BR-17).
    """
    path = os.path.join(root, *CONFIG_RELPATH.split("/"))
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return Setting(MODE_OFF, SOURCE_NO_CONFIG, None)
    except OSError as exc:
        raise _setting_error("%s cannot be read (%s)" % (CONFIG_RELPATH, _reason(exc)))
    if stat.S_ISLNK(info.st_mode):
        try:
            info = os.stat(path)
        except OSError:
            raise _setting_error("%s is a symlink that does not resolve" % CONFIG_RELPATH)
    if not stat.S_ISREG(info.st_mode):
        raise _setting_error("%s is not a regular file" % CONFIG_RELPATH)
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise _setting_error("%s cannot be read (%s)" % (CONFIG_RELPATH, _reason(exc)))
    if not may_carry_setting(data):
        return Setting(MODE_OFF, SOURCE_ABSENT, None)
    document = _parse_config(data)
    mode, source = setting_from_document(document)
    return Setting(mode, source, document)


def setting_line(setting):
    """The second line of ``mode``: where the value came from (BR-8)."""
    if setting.source == SOURCE_SET:
        return "%s is %s in %s" % (SETTING_KEY, setting.mode, CONFIG_RELPATH)
    if setting.source == SOURCE_ABSENT:
        return ("%s is not set in %s, which means off; set it to required to turn "
                "regression tests on" % (SETTING_KEY, CONFIG_RELPATH))
    return ("%s does not exist, which means off; set %s: required in it to turn "
            "regression tests on" % (CONFIG_RELPATH, SETTING_KEY))


# --- the strict frontmatter reader (ADR-691-B) --------------------------------

#: The four keys this module reads. Every other key is ignored, except that a
#: key given twice fails the report, as the dataset recognizer would
#: (tools/dataset/frontmatter.py).
READ_KEYS = ("id", "status", "regression_tests", "regression_waiver")
#: Fields whose failure means the status is unknown, so an unnamed run must
#: check the report rather than skip it. A bad file name (``name``) is not one:
#: a misnamed report whose status reads ``open`` is skipped like any open bug.
_STATUS_FIELDS = ("file", "frontmatter", "status")
#: Failures reported without a ``<field>:`` prefix, because they name no field.
_UNPREFIXED_FIELDS = ("file", "frontmatter", "name")

#: A canonical key line: the key at column 0, a colon, then a blank or the end.
_KEY_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*?))?[ \t]*$")
#: A line that starts a key in any spelling (quoted, a blank before the colon,
#: nothing after it). The line after a read key must look like this, or the
#: key's value continues onto it (partials/lesson-check.sh's continuation rule).
_ANY_KEY_RE = re.compile(r"""^["']?[A-Za-z_][A-Za-z0-9_-]*["']?[ \t]*:""")
#: One of the read keys in any spelling, indented or not. Matched on a line
#: that is not a canonical key line, it is a misspelling: one reader would see
#: the key and another would not (``regression_tests:["x"]``, ``"id": x``).
_MISSPELT_RE = dict((key, re.compile(r"""^[ \t]*["']?%s["']?[ \t]*:""" % key))
                    for key in READ_KEYS)
_TRAILING_COMMENT_RE = re.compile(r"(^|[ \t])#.*$")
_NULLS = ("", "~", "null", "Null", "NULL")
_UNCLOSED_LIST = "the flow list is not closed on the key's line"


def _rest_is_comment(rest):
    return not rest.strip() or re.match(r"^[ \t]+#", rest) is not None


def _quoted(raw):
    """Parse the quoted scalar opening ``raw``: ``(value, rest, error)``.

    Double quotes decode ``\\"`` and ``\\\\`` only; any other escape is refused
    rather than guessed at. Single quotes decode ``''``.
    """
    quote = raw[0]
    out = []
    k = 1
    while k < len(raw):
        char = raw[k]
        if quote == '"' and char == "\\":
            following = raw[k + 1:k + 2]
            if following in ('"', "\\"):
                out.append(following)
                k += 2
                continue
            return None, None, ("a backslash escape other than \\\" or \\\\, which "
                                "this reader does not decode")
        if char == quote:
            if quote == "'" and raw[k + 1:k + 2] == "'":
                out.append("'")
                k += 2
                continue
            return "".join(out), raw[k + 1:], None
        out.append(char)
        k += 1
    return None, None, "the opening %s quote is never closed on the key's line" % (
        "double" if quote == '"' else "single")


_PLAIN_ITEM_RE = re.compile(r"[^,\[\]{}]*")


def _flow_list(raw):
    """Parse the flow list opening ``raw``: ``(items, rest, error)``."""
    items = []
    size = len(raw)
    k = 1
    while True:
        while k < size and raw[k] in " \t":
            k += 1
        if k >= size:
            return None, None, _UNCLOSED_LIST
        char = raw[k]
        if char == "]":
            # Reached only at the start or after a comma: `[]`, or a trailing
            # comma before the bracket, which YAML allows.
            return items, raw[k + 1:], None
        if char in "\"'":
            item, rest, error = _quoted(raw[k:])
            if error:
                return None, None, error
            k = size - len(rest)
        elif char in "[{":
            return None, None, "an entry is a nested collection, not a path"
        elif char == ",":
            return None, None, "the list holds an empty entry"
        else:
            token = _PLAIN_ITEM_RE.match(raw, k).group(0)
            if re.search(r"(^|[ \t])#", token):
                # A comment ends the line before the list closes.
                return None, None, _UNCLOSED_LIST
            item = token.strip()
            k += len(token)
            if item[:1] in tuple("&*!|>%@`"):
                return None, None, "an entry starts with a YAML indicator (quote it)"
        items.append(item)
        while k < size and raw[k] in " \t":
            k += 1
        if k >= size:
            return None, None, _UNCLOSED_LIST
        if raw[k] == ",":
            k += 1
            continue
        if raw[k] == "]":
            return items, raw[k + 1:], None
        return None, None, "unexpected text after an entry"


def parse_value(raw):
    """``(kind, value, error)`` for the text after ``key:``.

    ``kind`` is ``null``, ``str``, ``list`` or ``map``; ``error`` is set, and
    the other two are ``None``, when the value cannot be read on its line.
    """
    if raw == "" or raw.startswith("#"):
        return "null", None, None
    first = raw[0]
    if first in "\"'":
        value, rest, error = _quoted(raw)
        if error:
            return None, None, error
        if not _rest_is_comment(rest):
            return None, None, "text follows the closing quote"
        return "str", value, None
    if first == "[":
        items, rest, error = _flow_list(raw)
        if error:
            return None, None, error
        if not _rest_is_comment(rest):
            return None, None, "text follows the closing ]"
        return "list", items, None
    if first == "{":
        return "map", None, None
    if first in "|>":
        return None, None, "a block scalar, whose value continues onto the next line"
    if first in "&*!%@`":
        return None, None, "a YAML construct this reader does not accept ('%s')" % first
    value = _TRAILING_COMMENT_RE.sub("", raw).strip()
    if value in _NULLS:
        return "null", None, None
    return "str", value, None


def frontmatter_lines(text):
    """``(lines, None)`` for the frontmatter block, or ``(None, reason)``.

    Found the way ``partials/lesson-check.sh`` finds it: a leading BOM and each
    line's trailing CR are dropped, blank lines and HTML comments before it are
    skipped, the first other line must be exactly ``---``, and the block closes
    at the next ``---``.
    """
    if text.startswith("﻿"):
        text = text[1:]
    lines = [line[:-1] if line.endswith("\r") else line for line in text.split("\n")]
    i, size, in_comment = 0, len(lines), False
    while i < size:
        stripped = lines[i].strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            i += 1
            continue
        if not stripped:
            i += 1
            continue
        if stripped.startswith("<!--"):
            in_comment = "-->" not in stripped
            i += 1
            continue
        break
    if i >= size or lines[i] != "---":
        return None, "no frontmatter block (its first line must be ---)"
    for j in range(i + 1, size):
        if lines[j] == "---":
            return lines[i + 1:j], None
    return None, "the frontmatter opens with --- and never closes"


class Report(object):
    """One bug report: its id, the four fields, and every reason it fails."""

    def __init__(self, name):
        self.name = name
        match = _REPORT_NAME_RE.match(name)
        self.bug_id = match.group(1) if match else None
        self.status = None
        self.tests = None
        self.waiver = None
        self.errors = []

    @property
    def label(self):
        return self.bug_id or self.name

    def fail(self, field, reason):
        self.errors.append((field, reason))

    def status_known(self):
        return not any(field in _STATUS_FIELDS for field, _ in self.errors)

    def reasons(self):
        out = []
        for field, reason in self.errors:
            out.append(reason if field in _UNPREFIXED_FIELDS else
                       "%s: %s" % (field, reason))
        return out


def _significant(line):
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def read_fields(lines, report):
    """Read the four keys out of the frontmatter ``lines`` into ``report``."""
    counts = collections.Counter()
    first_at = {}
    misspelt = set()
    for index, line in enumerate(lines):
        if not _significant(line):
            continue
        match = _KEY_LINE_RE.match(line)
        if match:
            key = match.group(1)
            counts[key] += 1
            if key in READ_KEYS and key not in first_at:
                first_at[key] = (index, match.group(2) or "")
            continue
        for key in READ_KEYS:
            if _MISSPELT_RE[key].match(line):
                misspelt.add(key)
    for key in sorted(counts):
        if counts[key] > 1:
            # Filed under the key itself, so a repeated `tags` fails the report
            # without making its status unknown.
            report.fail(key, "appears %d times; keep exactly one %s: line"
                        % (counts[key], key))
    values = {}
    for key in READ_KEYS:
        if key in misspelt:
            report.fail(key, "written in a spelling not every reader agrees on; "
                             "write exactly '%s: <value>' at the start of the line" % key)
            continue
        if key not in first_at or counts[key] > 1:
            continue
        index, raw = first_at[key]
        following = next((line for line in lines[index + 1:] if _significant(line)), None)
        if following is not None and not _ANY_KEY_RE.match(following):
            report.fail(key, "the value continues onto the next line; keep the whole "
                             "value on the key's line as a flow list or a quoted string")
            continue
        kind, value, error = parse_value(raw)
        if error:
            report.fail(key, error)
            continue
        values[key] = (kind, value)
    _type_fields(values, report)


def _type_fields(values, report):
    """Check each read value's type against the System Model; store it."""
    for key in ("id", "status"):
        if key not in values:
            continue
        kind, value = values[key]
        if kind == "null":
            continue
        if kind != "str":
            report.fail(key, "must be a string, not %s" % ("a list" if kind == "list"
                                                          else "a mapping"))
            continue
        if key == "status":
            report.status = value
        elif report.bug_id is not None and value != report.bug_id:
            report.fail("id", "the frontmatter says %s but the file name says %s"
                        % (value, report.bug_id))
    if "regression_tests" in values:
        kind, value = values["regression_tests"]
        if kind == "list":
            blank = [item for item in value if not item.strip()]
            if blank:
                report.fail("regression_tests", "the list holds an empty entry")
            else:
                report.tests = value
        elif kind != "null":
            report.fail("regression_tests", "must be a flow list of paths "
                        "([\"tests/...\"]), not %s" % ("a string" if kind == "str"
                                                       else "a mapping"))
    if "regression_waiver" in values:
        kind, value = values["regression_waiver"]
        if kind == "str":
            report.waiver = value
        elif kind != "null":
            report.fail("regression_waiver", "must be a quoted string, not %s"
                        % ("a list" if kind == "list" else "a mapping"))


def read_report_text(text, name):
    """A :class:`Report` from a report's text and its file name."""
    report = Report(name)
    if report.bug_id is None:
        report.fail("name", "the file name does not start with BUG-<digits>")
    lines, reason = frontmatter_lines(text)
    if reason:
        report.fail("frontmatter", reason)
        return report
    read_fields(lines, report)
    return report


def read_report(path, name):
    """A :class:`Report` read from ``path``; a read failure is a failure."""
    try:
        info = os.stat(path)
    except OSError as exc:
        report = Report(name)
        report.fail("file", "cannot be read (%s)" % _reason(exc))
        return report
    if not stat.S_ISREG(info.st_mode):
        report = Report(name)
        report.fail("file", "is not a regular file")
        return report
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        report = Report(name)
        report.fail("file", "cannot be read (%s)" % _reason(exc))
        return report
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        report = Report(name)
        report.fail("file", "is not UTF-8 text")
        return report
    return read_report_text(text, name)


# --- the bug reports ------------------------------------------------------------

_REPORT_NAME_RE = re.compile(r"^(BUG-[0-9]+)(?:-.*)?\.md$", re.DOTALL)
_ID_ARG_RE = re.compile(r"^BUG-[0-9]+$")


def _report_sort_key(name):
    match = _REPORT_NAME_RE.match(name)
    return (int(match.group(1)[4:]) if match else float("inf"), name)


def list_reports(bugs_dir):
    """Every ``BUG-*.md`` name in ``bugs_dir``, in id order; ``[]`` if absent."""
    try:
        names = os.listdir(bugs_dir)
    except FileNotFoundError:
        return []
    except NotADirectoryError:
        raise RegressionCheckError("%s is not a directory" % BUGS_RELDIR)
    except OSError as exc:
        raise RegressionCheckError("%s cannot be listed (%s)" % (BUGS_RELDIR, _reason(exc)))
    return sorted((n for n in names if n.startswith("BUG-") and n.endswith(".md")),
                  key=_report_sort_key)


# --- git ------------------------------------------------------------------------

#: Variables dropped from git's environment: lane_check.py's set (anything that
#: points git at another repository, index or object store, injects config, or
#: grafts or replaces history), plus the pathspec switches, which would turn the
#: literal pathspec below back into a glob or make it case-insensitive.
_GIT_ENV_SCRUB = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                  "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                  "GIT_PREFIX", "GIT_NAMESPACE",
                  "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
                  "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
                  "GIT_GRAFT_FILE", "GIT_SHALLOW_FILE", "GIT_REPLACE_REF_BASE",
                  "GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS",
                  "GIT_NOGLOB_PATHSPECS", "GIT_ICASE_PATHSPECS")
_GIT_ENV_SCRUB_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
_GIT_ENV_SET = {"GIT_NO_REPLACE_OBJECTS": "1"}
#: On every git run: no replace objects, no optional lock taken by a read, no
#: fsmonitor hook from any config file, and every pathspec literal, so a listed
#: ``tests/t[1].py`` never matches a tracked ``tests/t1.py``.
_GIT_GLOBAL_OPTS = ("--no-replace-objects", "--no-optional-locks", "--literal-pathspecs",
                    "-c", "core.fsmonitor=false")


def _git_env(environ=None):
    environ = os.environ if environ is None else environ
    env = dict((k, v) for k, v in environ.items()
               if k not in _GIT_ENV_SCRUB and not k.startswith(_GIT_ENV_SCRUB_PREFIXES))
    env.update(_GIT_ENV_SET)
    return env


def _git(repo_dir, args):
    """``git -C <repo_dir> <args>`` from a fixed argv; ``None`` if git cannot run."""
    try:
        return subprocess.run(["git"] + list(_GIT_GLOBAL_OPTS) + ["-C", repo_dir] + list(args),
                              stdin=subprocess.DEVNULL, capture_output=True, env=_git_env())
    except (OSError, ValueError):
        return None


def tracked_reason(repo_dir, rel):
    """``None`` when ``rel`` is in the index of ``repo_dir``'s work tree, else why not."""
    proc = _git(repo_dir, ["ls-files", "-z", "--error-unmatch", "--", rel])
    if proc is None:
        return "cannot be checked: git could not be run"
    if proc.returncode == 1:
        return "is not tracked by git"
    if proc.returncode != 0:
        return "is not tracked by git (git exit %d: no index here)" % proc.returncode
    entries = [os.fsdecode(e) for e in proc.stdout.split(b"\0") if e]
    if entries != [posixpath.normpath(rel)]:
        return "is not tracked by git"
    return None


# --- classification (BR-9) ------------------------------------------------------

#: ``<repo-id>:`` at the start of an entry (ADR-691-D).
_PREFIX_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*):(.*)$", re.DOTALL)


class Checker(object):
    """The path rules, against one root and the config parse that set ``required``."""

    def __init__(self, root, document):
        self.root = root
        self.document = document if isinstance(document, dict) else {}

    def repo_dir(self, repo_id):
        """``(directory, None)`` for a repo id (``None`` = the root), or ``(None, why)``."""
        if repo_id is None:
            return self.root, None
        repos = self.document.get("repos")
        if not isinstance(repos, dict) or repo_id not in repos:
            return None, ("repo '%s' is not declared under repos: in %s"
                          % (repo_id, CONFIG_RELPATH))
        entry = repos[repo_id]
        if not isinstance(entry, dict):
            return None, "repos.%s in %s is not a mapping" % (repo_id, CONFIG_RELPATH)
        if entry.get("primary") in ("true", True):
            return self.root, None
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            return None, "repos.%s in %s declares no path" % (repo_id, CONFIG_RELPATH)
        if os.path.isabs(path):
            target, shown = path, "its repos.%s.path" % repo_id
        else:
            target, shown = os.path.join(self.root, path), path
        if not os.path.isdir(target):
            return None, "repo '%s' is not cloned at %s" % (repo_id, shown)
        return target, None

    def entry_reason(self, entry, position, bug_id):
        """``None`` when one ``regression_tests`` entry passes, else why it fails."""
        match = _PREFIX_RE.match(entry)
        repo_id, rel = (match.group(1), match.group(2)) if match else (None, entry)
        shown = entry
        if not rel:
            return "regression_tests[%d] names no path" % position
        if rel.startswith("/"):
            return ("regression_tests[%d] is an absolute path; list it relative to "
                    "its repository" % position)
        if ".." in rel.split("/"):
            return "%s has a '..' segment" % shown
        repo_dir, why = self.repo_dir(repo_id)
        if why:
            return "%s: %s" % (shown, why)
        full = os.path.join(repo_dir, *rel.split("/"))
        try:
            info = os.lstat(full)
        except (FileNotFoundError, NotADirectoryError):
            return "%s does not exist" % shown
        except OSError as exc:
            return "%s cannot be read (%s)" % (shown, _reason(exc))
        except ValueError:
            # An embedded NUL: fail this bug, not the whole run.
            return "%s is not a usable path" % shown
        if stat.S_ISLNK(info.st_mode):
            return "%s is a symlink; list the file itself" % shown
        real_repo = os.path.realpath(repo_dir)
        if os.path.commonpath([real_repo, os.path.realpath(full)]) != real_repo:
            return "%s resolves outside its repository" % shown
        if not stat.S_ISREG(info.st_mode):
            return "%s is not a regular file" % shown
        why = tracked_reason(repo_dir, rel)
        if why:
            return "%s %s" % (shown, why)
        try:
            with open(full, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            return "%s cannot be read (%s)" % (shown, _reason(exc))
        if not cites(data, bug_id):
            return "%s does not cite %s" % (shown, bug_id)
        return None

    def classify(self, report, require_recorded):
        """``(class, reasons)`` for one report."""
        if report.errors:
            return FAILED, report.reasons()
        tests, waiver = report.tests, report.waiver
        has_tests = bool(tests)
        has_waiver = bool(waiver and waiver.strip())
        if has_tests and has_waiver:
            return FAILED, ["regression_tests and regression_waiver are both set; "
                            "record one or the other (BR-7)"]
        if has_tests:
            reasons = []
            for position, entry in enumerate(tests, start=1):
                why = self.entry_reason(entry, position, report.bug_id)
                if why:
                    reasons.append(why)
            return (FAILED, reasons) if reasons else (PASSED, [])
        if has_waiver:
            return WAIVED, []
        if waiver:
            return FAILED, ["regression_waiver is blank and regression_tests is empty; "
                            "a waiver needs a one-line reason (BR-6)"]
        if require_recorded:
            return FAILED, ["neither regression_tests nor regression_waiver is recorded"]
        return LEGACY, []


def cites(data, bug_id):
    """True when the bytes cite ``bug_id`` as a whole id (BUG-26 is not BUG-261)."""
    pattern = re.compile(rb"(?<![A-Za-z0-9])" + re.escape(bug_id.encode("ascii"))
                         + rb"(?![0-9])")
    return pattern.search(data) is not None


def check(root, ids=(), require_recorded=False):
    """Run the check. Returns ``(setting, results)``; ``results`` is ``None`` when off.

    Each result is ``(label, class, reasons)``. Raises :class:`RegressionCheckError`
    for anything that prevents a decision.
    """
    setting = read_setting(root)
    if setting.mode == MODE_OFF:
        return setting, None  # BR-11: no bug report is opened
    checker = Checker(root, setting.document)
    bugs_dir = os.path.join(root, *BUGS_RELDIR.split("/"))
    results = []
    names = list_reports(bugs_dir)
    if ids:
        by_id = collections.defaultdict(list)
        for name in names:
            match = _REPORT_NAME_RE.match(name)
            if match:
                by_id[match.group(1)].append(name)
        for bug_id in ids:
            found = by_id.get(bug_id, [])
            if not found:
                results.append((bug_id, FAILED, ["no bug report in %s" % BUGS_RELDIR]))
                continue
            if len(found) > 1:
                results.append((bug_id, FAILED, ["%d reports in %s carry this id"
                                                 % (len(found), BUGS_RELDIR)]))
                continue
            report = read_report(os.path.join(bugs_dir, found[0]), found[0])
            cls, reasons = checker.classify(report, require_recorded)
            results.append((report.label, cls, reasons))
        return setting, results
    for name in names:
        report = read_report(os.path.join(bugs_dir, name), name)
        if report.status_known() and report.status not in IN_SCOPE_STATUSES:
            continue
        cls, reasons = checker.classify(report, require_recorded)
        results.append((report.label, cls, reasons))
    return setting, results


def format_check(setting, results):
    """``(lines, rc)`` for a finished check."""
    if results is None:
        return ([CHECK_LINE + RESULT_OFF,
                 "regression tests are off for this project: " + setting_line(setting)],
                RC_PASS)
    counts = collections.Counter(cls for _, cls, _ in results)
    failed = counts[FAILED]
    lines = [CHECK_LINE + (RESULT_FAIL if failed else RESULT_PASS),
             " ".join("%s=%d" % (cls, counts[cls]) for cls in CLASSES)]
    for label, cls, reasons in results:
        if cls == FAILED:
            lines.append("%s: %s" % (one_line(label), "; ".join(one_line(r) for r in reasons)))
    return lines, (RC_FAIL if failed else RC_PASS)


# --- the CLI ----------------------------------------------------------------------

class _ArgumentParser(argparse.ArgumentParser):
    """argparse that raises instead of exiting, so a usage error still prints
    the error contract on stdout."""

    def error(self, message):
        raise RegressionCheckError("usage: %s (%s)" % (USAGE, message))


def _parse_args(argv):
    if not argv:
        raise RegressionCheckError("usage: %s (a verb is required)" % USAGE)
    verb = argv[0]
    if verb not in ("mode", "check"):
        raise RegressionCheckError("usage: %s (unknown verb '%s')" % (USAGE, verb))
    parser = _ArgumentParser(prog="regression_check.py " + verb, add_help=False,
                             allow_abbrev=False)
    parser.add_argument("--root", default=None)
    if verb == "check":
        parser.add_argument("--require-recorded", action="store_true")
        parser.add_argument("ids", nargs="*")
    # Intermixed, so `check BUG-1 --require-recorded BUG-2` keeps both ids.
    args = parser.parse_intermixed_args(argv[1:])
    args.verb = verb
    if verb == "check":
        ids = []
        for bug_id in args.ids:
            if not _ID_ARG_RE.match(bug_id):
                raise RegressionCheckError("usage: %s ('%s' is not a BUG-nnn id)"
                                           % (USAGE, bug_id))
            if bug_id not in ids:
                ids.append(bug_id)
        args.ids = ids
    return args


def _root(value):
    root = os.path.abspath(value if value is not None else os.getcwd())
    if not os.path.isdir(root):
        raise RegressionCheckError("--root does not name a directory")
    return root


def _write(lines):
    text = "\n".join(lines) + "\n"
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.write(text.encode("ascii", "backslashreplace").decode("ascii"))
    sys.stdout.flush()


def main(argv=None):
    """CLI entry point. Returns 0 pass or off, 1 fail, 2 error."""
    argv = list(sys.argv[1:] if argv is None else argv)
    prefix = MODE_LINE if argv[:1] == ["mode"] else CHECK_LINE
    try:
        args = _parse_args(argv)
        root = _root(args.root)
        if args.verb == "mode":
            setting = read_setting(root)
            lines, rc = [MODE_LINE + setting.mode, setting_line(setting)], RC_PASS
        else:
            setting, results = check(root, args.ids, args.require_recorded)
            lines, rc = format_check(setting, results)
    except RegressionCheckError as exc:
        lines, rc = [prefix + RESULT_ERROR, one_line(exc)], RC_ERROR
    except Exception as exc:
        # LESSON-581: the fall-through for anything unplanned is error, never
        # pass. Only the type and an OSError's reason: its file name may be a
        # home path.
        lines, rc = [prefix + RESULT_ERROR, one_line("unexpected %s%s" % (
            type(exc).__name__,
            ": " + _reason(exc) if isinstance(exc, OSError) else ""))], RC_ERROR
    try:
        _write(lines)
    except Exception:
        # Nothing reached the caller; a 0 or 1 here would be a verdict with no
        # facts behind it.
        return RC_ERROR
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
