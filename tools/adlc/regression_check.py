#!/usr/bin/env python3
"""The regression-test check (REQ-691, architecture ADR-691-A to ADR-691-D).

Reads a project's ``bugfix.regression_test`` setting and sorts its bug reports
into passed, waived, legacy and failed. Every deterministic REQ-691 rule is
decided here; ``/bugfix`` keeps only the protocol. People and CI run it as
``adlc regression-check``; skill fences reach it through
``partials/regression-check.sh``, which runs the installed toolkit's copy::

    python3 tools/adlc/regression_check.py mode  [--root DIR] [--base REF]
    python3 tools/adlc/regression_check.py check [--root DIR] [--base REF]
                                                 [--require-recorded] [BUG-nnn ...]

``--root`` is the project root, the directory holding ``.adlc/``. It defaults
to the current directory. ``--base`` names a commit whose ``.adlc/config.yml``
supplies the setting and ``repos:`` (see The setting). Standard library only, plus the sibling
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
``.adlc/config.yml`` in the working tree, or, with ``--base REF``, the copy
committed at ``REF`` (``git ls-tree`` and ``git cat-file`` at the root's
repo-relative prefix), never the disk: a gate that reads the tree under check
lets the branch switch its own gate off or re-point a sibling, so the
``/bugfix`` Gate passes the integration branch's remote-tracking ref
(``lane_check.py``'s rule). ``REF`` is a full ref, ``refs/remotes/...`` or
``refs/heads/...``, in branch-name characters (``[A-Za-z0-9._/-]``, no ``..``,
no empty or dot-led component, no ``.lock``); a short name (which a tag of the
same name shadows), ``HEAD``, ``FETCH_HEAD``, ``ORIG_HEAD`` or a bare sha is a
usage error. It is resolved with ``git show-ref --verify``, which takes the ref
exactly as written, and a ref that names no commit is an error. Bug reports and
test files are still read from the working tree and the index (BR-12, amended:
only the policy comes from the ref).

A missing file is ``off`` (BR-1). A file whose bytes carry neither
``regression_test`` nor ``bugfix`` outside whole-line comments is ``off``
without being parsed, by the byte prefilter ``lane_check.may_carry_lanes``
uses: a backslash (a quoted key spelled with escapes) or a NUL (a UTF-16 file)
on a non-comment line forces a parse, which is the safe direction. Anything
else is parsed by ``harness_yaml.loads``, the toolkit's stdlib closed-subset
loader. When the subset refuses the file, it stops the caller only if the file
may still define the setting: ``regression_test`` shaped as a key anywhere,
``bugfix`` as a top-level or flow key, or a double-quoted key holding a
backslash, which an escape could spell as either. Otherwise (a backslash in a
value, a ``>`` block, an anchor elsewhere) it cannot, and the setting is
``off``. A parsed ``bugfix`` must be a mapping whose only key is
``regression_test``, with the value ``required`` or ``off``; an absent
``bugfix``, or a ``bugfix`` without the key, is ``off``. Everything else is an
error: a file that may define the setting and does not parse, one that is not
UTF-8, a ``bugfix`` that is not a mapping, an unknown key under it (a typo
included), another value, a ``regression_test`` at the top level, a config that
is a directory, a dangling symlink, or a link that resolves outside the root.

The bug reports (ADR-691-B)
---------------------------
Without ids, every ``.adlc/bugs/BUG-*.md`` whose ``status`` is ``resolved`` or
``closed`` (the set ``/spec`` Step 1.6 uses). With ids, exactly those reports,
whatever their status; an id with no report, or with two, is a failure, and an
unnamed run fails each in-scope report whose id another report also carries,
with the same reason. A report whose status cannot be read is checked, because
it might be resolved. A report that is a symlink fails without being opened,
and a ``.adlc`` or ``.adlc/bugs`` that resolves outside the root is an error.

Frontmatter is read by this module's own strict one-line reader, modelled on
``partials/lesson-check.sh``'s ``_alc_field``, not by ``lessons.py``'s lenient
one (which lets the last duplicate win and loses block-list items, each of
which would turn a malformed report into a silent ``legacy``). It reads
``id``, ``status``, ``regression_tests`` and ``regression_waiver`` and ignores
other keys, except that any key given twice fails the report. One of the four
keys fails the report when it is written in a spelling other than ``key: value``
at column 0, when its value continues onto the next line (a block list), when
a quote or a flow list is not closed on its line, or when its value is not the
type the System Model gives it: a flow list of strings, and a string, which
for ``regression_waiver`` must be quoted (a plain ``false``, ``0`` or
``reason: x`` means something different to every reader, LESSON-716). An
indented line naming a read key is a misspelling only when no block is open
above it: a key with no value on its line, or a ``|`` / ``>`` block scalar,
opens one for every more-indented line below it (LESSON-404).

Classification (BR-9): **passed** when ``regression_tests`` lists at least one
path and every path passes the path rules; **waived** when
``regression_waiver`` is non-blank and ``regression_tests`` is empty;
**legacy** when neither is present, where an empty list ``[]``, an empty
string ``""`` and an empty value all count as absent (the bug template ships
them empty); **failed** otherwise, including both fields set (BR-7) and a
whitespace-only waiver with no tests (BR-6). ``--require-recorded`` turns
legacy into failed, for ``/bugfix`` Phase 6 (BR-13), and requires every listed
test to be committed (The path rules).

The path rules (ADR-691-C, ADR-691-D)
-------------------------------------
Each entry is a path relative to its repository, optionally prefixed
``<repo-id>:``. A prefix resolves through ``repos.<repo-id>.path`` in the same
parse of the config. A relative path is relative to the project's directory in
the repository's main worktree, as ``/proceed`` resolves it from the primary
checkout (``partials/id-alloc.sh``'s main-worktree rule, BUG-210), so a fix
worktree under ``.worktrees/`` finds the same sibling; an absolute path is used
as it is. The primary's own id (``primary: true``) and no prefix both mean the
root. An undeclared id, an
entry with no path, and a sibling that is not cloned at its path each fail,
naming the repo. A prefix is a leading ``[A-Za-z0-9][A-Za-z0-9_.-]*:``, so a
root-level file whose name holds a colon reads as a prefix and fails loudly.

A path passes when it is not absolute, has no ``..`` segment, exists, is not a
symlink, resolves inside its repository, is a regular file, is tracked
(``git ls-files --error-unmatch`` with literal pathspecs, its output equal to
the path), and its working-tree bytes cite the bug id: ``BUG-<n>`` with no
letter or digit before it and no digit after it, so BUG-26 never matches
BUG-261. With ``--require-recorded`` the path must also be committed in its
repository's ``HEAD``, and that committed copy must cite the id
(``git cat-file`` at ``HEAD:./<path>``), so a test that is only staged, or
whose citation is only in the working tree, fails as not committed. The verdict
on a bug reads only the working tree, git's index and, under
``--require-recorded``, each repository's own ``HEAD``. This module never
fetches and never diffs, and the only other ref it reads is the one a caller
names with ``--base``, for the config alone (BR-12, LESSON-782). Git runs from
a fixed argv, never through a shell.
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

USAGE = ("regression_check.py mode [--root DIR] [--base REF] | "
         "check [--root DIR] [--base REF] [--require-recorded] [BUG-nnn ...]")

#: A ``--base`` ref: a full ref under ``refs/remotes/`` or ``refs/heads/``, in
#: branch-name characters only, so it can never carry a revision suffix (``^``,
#: ``~``, ``@{``), a path (``REF:path``), a range (``..``) or an option (a
#: leading ``-``). A short name is refused: git resolves ``origin/main`` to a tag
#: of that name before the remote-tracking branch, so a tag could pick the
#: config the gate reads. ``HEAD``, ``FETCH_HEAD``, ``ORIG_HEAD`` and a bare sha
#: are refused for the same reason: none of them names the integration branch.
_REF_RE = re.compile(r"^refs/(?:remotes|heads)/[A-Za-z0-9._/-]+$")
_OID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_REGULAR_BLOB_MODES = (b"100644", b"100755")
_SYMLINK_MODE = b"120000"
_TREE_MODE = b"040000"


class RegressionCheckError(Exception):
    """Anything that prevents a decision. The message is one line of reason."""


# --- output safety ------------------------------------------------------------

#: The backslash itself, C0, DEL, C1, the Arabic letter mark, zero-width and
#: directional marks, the Unicode line and paragraph separators, bidi
#: embeddings and isolates, the BOM, and lone surrogates (an undecodable byte
#: in a file name). Each is written as an escape, so a path or a reason stays
#: one printable line that no ``splitlines()`` reader splits (lane_check.py).
#: A copy, not an import: this engine loads nothing but ``harness_yaml``, so a
#: change to ``lane_check.py``'s import surface can never stop the gate.
#: ``test_output_escaping_matches_lane_check`` pins the two copies together.
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
    # lane_check._type_name with one deliberate difference: None is "empty", not
    # "a null". Here it only ever names a key written with no value (`bugfix:`
    # alone), and "bugfix ... is empty" is how its author would put it.
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
#: (bare, quoted, in a flow mapping, indented or in a comment), ``bugfix``, so a
#: ``bugfix:`` block is always validated and a misspelt key under it
#: (``regresion_test``) stops rather than reading as off, a backslash (a
#: double-quoted key can spell either with escapes) and a NUL (a UTF-16 or
#: UTF-32 file carries the word as ``r\0e\0...``). A false positive only means
#: the file is parsed and validated, the safe direction; a false negative would
#: read a project's ``required`` as ``off``. lane_check.py's _LANES_MARKERS.
_KEY_MARKERS = (b"regression_test", b"bugfix", b"\\", b"\x00")
#: The same markers as text, for the per-line scan of a decoded config.
_KEY_MARKER_TEXT = tuple(marker.decode("ascii") for marker in _KEY_MARKERS)

#: Every character a YAML parser may treat as a line break. Splitting on a
#: superset of the parser's breaks can only turn one line into several, and a
#: fragment that does not start with ``#`` is then scanned: the safe direction.
_YAML_LINE_BREAKS = re.compile("\r\n|[\r\n\x85  ]")


def may_carry_setting(data):
    """True unless the raw config bytes certainly carry no ``regression_test``
    and no ``bugfix``.

    Whole-line comments are skipped, so a config that only mentions either in
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
        if any(marker in line for marker in _KEY_MARKER_TEXT):
            return True
    return False


class Setting(object):
    """The resolved mode, where it came from, the parsed config (or None), and
    the ``--base`` ref it was read at (``None``: the working tree)."""

    __slots__ = ("mode", "source", "document", "ref")

    def __init__(self, mode, source, document, ref=None):
        self.mode = mode
        self.source = source
        self.document = document
        self.ref = ref


def config_where(ref=None):
    """How output names the config: ``.adlc/config.yml``, ``... at <ref>``."""
    return CONFIG_RELPATH if ref is None else "%s at %s" % (CONFIG_RELPATH, ref)


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


#: After the subset refuses a config, the shapes that mean it may still define
#: the setting: ``regression_test`` as a key anywhere (block, flow, quoted or
#: indented), ``bugfix`` as a top-level or flow key, and a double-quoted key
#: holding a backslash, whose escapes could spell either name (the subset
#: decodes no ``\x`` escape, so such a file never parses here). Searched on
#: every line that is not a whole-line comment, with NULs removed, so a UTF-16
#: file's ``b\0u\0g\0f\0i\0x\0:`` still reads as ``bugfix:``.
_SETTING_KEY_SHAPES = (
    re.compile(r"""regression_test["']?[ \t]*:"""),
    re.compile(r"""^["']?bugfix["']?[ \t]*:"""),
    re.compile(r"""[{,][ \t]*["']?bugfix["']?[ \t]*:"""),
    re.compile(r'''"[^"]*\\[^"]*"[ \t]*:'''),
)


def may_define_setting(text):
    """True when ``text``, a config the subset refused, may define the setting.

    False only when neither key is written as a key anywhere: the prefilter's
    false positives (a backslash in a value, the word in a trailing comment)
    then read as ``off`` rather than stopping a project that never set it.
    """
    for line in _YAML_LINE_BREAKS.split(text.replace("\x00", "")):
        if line.lstrip(" \t").startswith("#"):
            continue
        if any(shape.search(line) for shape in _SETTING_KEY_SHAPES):
            return True
    return False


def _parse_config(data, ref=None):
    """The parsed config, or ``None`` when the bytes cannot define the setting."""
    where = config_where(ref)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        # Nothing in it can be seen, so nothing can be ruled out (LESSON-716).
        raise _setting_error("%s is not UTF-8 text" % where)
    if text.startswith("﻿"):
        text = text[1:]
    if "\x00" in text:
        if may_define_setting(text):
            raise _setting_error("%s holds NUL bytes; save it as UTF-8" % where)
        return None
    text = text.replace("\r\n", "\n")
    try:
        return harness_yaml.loads(text, CONFIG_RELPATH)
    except harness_yaml.YamlError as exc:
        if not may_define_setting(text):
            return None
        raise _setting_error("the config%s does not parse (%s)"
                             % ("" if ref is None else " at %s" % ref, exc))


def setting_from_document(document, where=CONFIG_RELPATH):
    """``(mode, source)`` from a parsed config; raises on anything else."""
    if not isinstance(document, dict):
        raise _setting_error("%s is %s, not a mapping" % (where, _type_name(document)))
    if "regression_test" in document:
        raise _setting_error("regression_test is a top-level key in %s; it "
                             "belongs under bugfix:" % where)
    if "bugfix" not in document:
        return MODE_OFF, SOURCE_ABSENT
    section = document["bugfix"]
    if not isinstance(section, dict):
        raise _setting_error("bugfix in %s is %s; it must be a mapping holding "
                             "regression_test" % (where, _type_name(section)))
    unknown = [key for key in section if key != "regression_test"]
    if unknown:
        raise _setting_error("unknown key%s %s under bugfix in %s (bugfix holds "
                             "only regression_test)" % (
                                 "s" if len(unknown) > 1 else "",
                                 ", ".join("'%s'" % k for k in unknown), where))
    if "regression_test" not in section:
        return MODE_OFF, SOURCE_ABSENT
    value = section["regression_test"]
    if isinstance(value, str) and value in MODES:
        return value, SOURCE_SET
    raise _setting_error("%s in %s is %s" % (SETTING_KEY, where, _describe(value)))


def inside_root(root, path):
    """True when ``path``, every symlink followed, stays under ``root``."""
    real_root = os.path.realpath(root)
    return os.path.commonpath([real_root, os.path.realpath(path)]) == real_root


def read_disk_config(root):
    """The bytes of the working tree's config, or ``None`` when there is none.

    One that exists but cannot be read, or is not a regular file (a directory,
    a symlink that does not resolve), or resolves outside the root, is an
    error, never ``off`` (BR-17). Its target is never named.
    """
    path = os.path.join(root, *CONFIG_RELPATH.split("/"))
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _setting_error("%s cannot be read (%s)" % (CONFIG_RELPATH, _reason(exc)))
    if stat.S_ISLNK(info.st_mode):
        try:
            info = os.stat(path)
        except OSError:
            raise _setting_error("%s is a symlink that does not resolve" % CONFIG_RELPATH)
    # Checked whether or not the file itself is a link: a symlinked .adlc moves
    # a regular config.yml outside the root just as well.
    if not inside_root(root, path):
        raise _setting_error("%s resolves outside the project root; the check reads "
                             "only a config inside it" % CONFIG_RELPATH)
    if not stat.S_ISREG(info.st_mode):
        raise _setting_error("%s is not a regular file" % CONFIG_RELPATH)
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise _setting_error("%s cannot be read (%s)" % (CONFIG_RELPATH, _reason(exc)))


def check_ref(ref):
    """``ref`` when it is a usable ``--base``; a usage error otherwise.

    Usable is a full ref, ``refs/remotes/<remote>/<branch>`` or
    ``refs/heads/<branch>``, whose every component is non-empty, does not start
    with ``.`` and does not end in ``.lock``, with no ``..`` and no trailing
    ``.`` (``git check-ref-format``'s rules, within the strict charset).
    """
    parts = ref.split("/")
    if (not _REF_RE.match(ref) or ".." in ref or ref.endswith(".")
            or any(not part or part.startswith(".") or part.endswith(".lock")
                   for part in parts)):
        raise RegressionCheckError(
            "usage: %s ('%s' is not a usable --base ref: name a full ref, "
            "refs/remotes/<remote>/<branch> or refs/heads/<branch>)" % (USAGE, ref))
    return ref


def _git_stdout(repo_dir, args, what):
    """stdout of ``git -C <repo_dir> <args>``, or an error naming ``what``.

    git's stderr is never quoted: it can carry an absolute path.
    """
    proc = _git(repo_dir, args)
    if proc is None:
        raise RegressionCheckError("%s: git could not be run" % what)
    if proc.returncode != 0:
        raise RegressionCheckError("%s failed (git exit %d)" % (what, proc.returncode))
    return proc.stdout


def resolve_ref(root, ref):
    """The commit ``ref`` names, exactly that ref and nothing git's lookup rules
    would put in its place; an error when it names none.

    ``git show-ref --verify`` takes the full ref as it is written: a missing
    ``refs/remotes/origin/main`` is not then found as ``refs/tags/refs/remotes/
    origin/main``, which plain ``rev-parse`` falls through to. Its object is
    peeled to a commit by its full object id, which git never reads as a ref.
    """
    proc = _git(root, ["show-ref", "--verify", "--", ref])
    if proc is None:
        raise RegressionCheckError("resolving --base %s: git could not be run" % ref)
    fields = proc.stdout.decode("ascii", "replace").split()
    if (proc.returncode != 0 or len(fields) != 2 or fields[1] != ref
            or not _OID_RE.match(fields[0])):
        raise RegressionCheckError("--base %s does not resolve to a commit" % ref)
    proc = _git(root, ["rev-parse", "--verify", "--quiet", fields[0] + "^{commit}"])
    if proc is None:
        raise RegressionCheckError("resolving --base %s: git could not be run" % ref)
    oid = proc.stdout.decode("ascii", "replace").strip()
    if proc.returncode != 0 or not _OID_RE.match(oid):
        raise RegressionCheckError("--base %s does not resolve to a commit" % ref)
    return oid


def read_base_config(root, ref):
    """The bytes of the project's config committed at ``ref``, or ``None``.

    The path is the root's repo-relative prefix plus ``.adlc/config.yml``, so a
    project in a subdirectory reads its own config. ``ls-tree`` names the
    entry's mode first, so a symlink, directory or submodule in the config's
    place is refused rather than read (lane_check.read_base_config).
    """
    check_ref(ref)
    where = config_where(ref)
    proc = _git(root, ["rev-parse", "--show-prefix"])
    if proc is None:
        raise RegressionCheckError("reading %s: git could not be run" % where)
    if proc.returncode != 0:
        raise RegressionCheckError("--base needs a git repository, and --root is not "
                                   "inside a git work tree")
    prefix = os.fsdecode(proc.stdout)
    prefix = prefix[:-1] if prefix.endswith("\n") else prefix
    oid = resolve_ref(root, ref)
    path = prefix + CONFIG_RELPATH
    out = _git_stdout(root, ["ls-tree", "-l", "-z", "--full-tree", oid, "--", path],
                      "listing %s" % where)
    entries = [e for e in out.split(b"\0") if e]
    if not entries:
        # Absent, unless .adlc itself is not a plain directory at the ref: git
        # does not descend through a symlinked .adlc, so the config would
        # vanish and the setting would read as off.
        top = _git_stdout(root, ["ls-tree", "-z", "--full-tree", oid, "--", prefix + ".adlc"],
                          "listing .adlc at %s" % ref)
        for entry in (e for e in top.split(b"\0") if e):
            if not entry.startswith(_TREE_MODE + b" "):
                raise RegressionCheckError(".adlc is not a directory at %s; the check reads "
                                           "the config only from a real %s"
                                           % (ref, CONFIG_RELPATH))
        return None
    meta, sep, name = entries[0].partition(b"\t")
    fields = meta.split()
    if len(entries) != 1 or not sep or len(fields) != 4 or name != os.fsencode(path):
        raise RegressionCheckError("listing %s: unexpected git ls-tree output" % where)
    mode, otype, blob = fields[0], fields[1], fields[2]
    if mode == _SYMLINK_MODE:
        raise RegressionCheckError("%s is a symlink at %s; the check reads only a regular "
                                   "file" % (CONFIG_RELPATH, ref))
    if otype != b"blob" or mode not in _REGULAR_BLOB_MODES:
        raise RegressionCheckError("%s is not a regular file at %s" % (CONFIG_RELPATH, ref))
    return _git_stdout(root, ["cat-file", "blob", blob.decode("ascii", "replace")],
                       "reading %s" % where)


def read_setting(root, ref=None):
    """The project's :class:`Setting`. Raises :class:`RegressionCheckError`.

    From the working tree, or, with ``ref``, from the config committed there
    and never from the disk. Either way a missing config is ``off`` (BR-1), and
    the bytes go through the same prefilter, parse and validation.
    """
    data = read_disk_config(root) if ref is None else read_base_config(root, ref)
    if data is None:
        return Setting(MODE_OFF, SOURCE_NO_CONFIG, None, ref)
    if not may_carry_setting(data):
        return Setting(MODE_OFF, SOURCE_ABSENT, None, ref)
    document = _parse_config(data, ref)
    if document is None:
        return Setting(MODE_OFF, SOURCE_ABSENT, None, ref)
    mode, source = setting_from_document(document, config_where(ref))
    return Setting(mode, source, document, ref)


def setting_line(setting):
    """The second line of ``mode``: where the value came from (BR-8)."""
    where = config_where(setting.ref)
    if setting.source == SOURCE_SET:
        return "%s is %s in %s" % (SETTING_KEY, setting.mode, where)
    if setting.source == SOURCE_ABSENT:
        return ("%s is not set in %s, which means off; set it to required to turn "
                "regression tests on" % (SETTING_KEY, where))
    return ("%s does not exist%s, which means off; set %s: required in it to turn "
            "regression tests on" % (CONFIG_RELPATH,
                                     "" if setting.ref is None else " at %s" % setting.ref,
                                     SETTING_KEY))


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
#: that is not a canonical key line and is not inside an open block, it is a
#: misspelling: one reader would see the key and another would not
#: (``regression_tests:["x"]``, ``"id": x``, ``  status: x`` under nothing).
_MISSPELT_RE = dict((key, re.compile(r"""^[ \t]*["']?%s["']?[ \t]*:""" % key))
                    for key in READ_KEYS)
#: A key in any spelling at any indent, with what follows its colon (group 2).
_BLOCK_KEY_RE = re.compile(
    r"""^([ \t]*)["']?[A-Za-z_][A-Za-z0-9_-]*["']?[ \t]*:(?:[ \t]+(.*?))?[ \t]*$""")
_TRAILING_COMMENT_RE = re.compile(r"(^|[ \t])#.*$")
#: The kinds of block a line can open: a key's nested mapping or sequence, and
#: a ``|`` or ``>`` block scalar, whose every more-indented line is text.
_BLOCK_NESTED = "nested"
_BLOCK_SCALAR = "scalar"
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

    ``kind`` is ``null``, ``quoted`` (a quoted string), ``plain`` (an unquoted
    scalar, which YAML readers may each type differently), ``list`` or ``map``;
    ``error`` is set, and the other two are ``None``, when the value cannot be
    read on its line.
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
        return "quoted", value, None
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
    return "plain", value, None


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


def _opens_block(line):
    """``(indent, kind)`` of the block ``line`` opens, or ``None``.

    A key whose value is empty on its line (a comment aside) opens a nested
    block; one whose value starts with ``|`` or ``>`` opens a block scalar.
    """
    match = _BLOCK_KEY_RE.match(line)
    if not match:
        return None
    value = _TRAILING_COMMENT_RE.sub("", match.group(2) or "").strip()
    if not value:
        return len(match.group(1)), _BLOCK_NESTED
    if value[0] in "|>":
        return len(match.group(1)), _BLOCK_SCALAR
    return None


def _in_block(block, line):
    """True when ``line`` belongs to the open ``block``, an ``(indent, kind)``."""
    indent = len(line) - len(line.lstrip(" \t"))
    if indent > block[0]:
        return True
    # A sequence may sit at its parent key's indentation (`checks:` then `- x`);
    # a block scalar's text never does.
    stripped = line.lstrip(" \t")
    return (indent == block[0] and block[1] == _BLOCK_NESTED
            and (stripped == "-" or stripped.startswith(("- ", "-\t"))))


def read_fields(lines, report):
    """Read the four keys out of the frontmatter ``lines`` into ``report``."""
    counts = collections.Counter()
    first_at = {}
    misspelt = set()
    block = None
    for index, line in enumerate(lines):
        if not _significant(line):
            continue
        if block is not None:
            if _in_block(block, line):
                # Under another key, or text in a block scalar: a mention of a
                # read key here is not the key (LESSON-404).
                continue
            block = None
        match = _KEY_LINE_RE.match(line)
        if match:
            key = match.group(1)
            counts[key] += 1
            if key in READ_KEYS and key not in first_at:
                first_at[key] = (index, match.group(2) or "")
        else:
            for key in READ_KEYS:
                if _MISSPELT_RE[key].match(line):
                    misspelt.add(key)
        block = _opens_block(line)
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
        if kind not in ("quoted", "plain"):
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
                        "([\"tests/...\"]), not %s" % ("a mapping" if kind == "map"
                                                       else "a string"))
    if "regression_waiver" in values:
        kind, value = values["regression_waiver"]
        if kind == "quoted":
            report.waiver = value
        elif kind != "null":
            # LESSON-716: a plain `false`, `0` or `reason: x` is a boolean, an
            # integer or a mapping to some reader, and is cut at ` #` by others.
            report.fail("regression_waiver", "must be a quoted string, not %s"
                        % {"plain": "an unquoted value", "list": "a list"}.get(
                            kind, "a mapping"))


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
    """A :class:`Report` read from ``path``; a read failure is a failure.

    A symlink is refused without being followed, wherever it points: its target
    is not this project's report, and its contents are never read or echoed.
    """
    try:
        info = os.lstat(path)
    except OSError as exc:
        report = Report(name)
        report.fail("file", "cannot be read (%s)" % _reason(exc))
        return report
    if stat.S_ISLNK(info.st_mode):
        report = Report(name)
        report.fail("file", "is a symlink; a bug report must be a regular file in %s"
                    % BUGS_RELDIR)
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


#: The one ref the engine names itself: each repository's own ``HEAD``, read
#: only under ``--require-recorded`` (:func:`committed_reason`). It is local
#: state, like the index, never a remote branch (BR-12).
_COMMITTED_REV = "HEAD"


def committed_reason(repo_dir, rel, bug_id):
    """``None`` when ``rel`` is committed in ``repo_dir``'s ``HEAD`` and that
    copy cites ``bug_id``, else why not.

    ``/bugfix``'s Gate passes ``--require-recorded``: what merges is the
    commits, so a test that is only staged, or whose citation is only in the
    working tree, is not a recorded regression test. That matters most for a
    sibling repository, whose tree the Gate's clean-tree guard does not cover.
    ``<rev>:./<path>`` is relative to ``repo_dir``, so a project or sibling in
    a subdirectory of its repository names the same file.
    """
    spec = "%s:./%s" % (_COMMITTED_REV, posixpath.normpath(rel))
    proc = _git(repo_dir, ["cat-file", "-e", spec])
    if proc is None:
        return "cannot be checked: git could not be run"
    if proc.returncode != 0:
        return "is not committed (not in HEAD)"
    proc = _git(repo_dir, ["cat-file", "blob", spec])
    if proc is None:
        return "cannot be checked: git could not be run"
    if proc.returncode != 0:
        return "is not committed (not a file in HEAD)"
    if not cites(proc.stdout, bug_id):
        return "does not cite %s in its committed copy (HEAD)" % bug_id
    return None


# --- classification (BR-9) ------------------------------------------------------

#: ``<repo-id>:`` at the start of an entry (ADR-691-D).
_PREFIX_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*):(.*)$", re.DOTALL)


def sibling_base(root):
    """``(directory, None)`` a relative ``repos.<id>.path`` is relative to, or
    ``(None, why)``.

    That is the project's directory in its repository's main worktree, because
    ``/proceed`` resolves sibling paths from the primary checkout
    (``proceed/phase-0-setup.md``). From a linked worktree, such as the
    ``/bugfix`` fix worktree under ``.worktrees/``, the root itself would put
    ``../api`` inside the worktree container (BUG-210's trap). The main worktree
    is the parent of ``--git-common-dir``, as ``partials/id-alloc.sh``'s
    ``adlc_main_worktree`` finds it, plus the root's repo-relative prefix for a
    project in a subdirectory. Without ``--path-format`` (git 2.31), a relative
    answer is made absolute against the root, as that function's fallback does.
    A root that is the main checkout (its git dir is the common dir: a
    submodule or a ``--separate-git-dir`` layout included), or that is in no git
    work tree, is its own base.
    """
    proc = _git(root, ["rev-parse", "--git-dir", "--git-common-dir", "--show-prefix"])
    if proc is None:
        return None, "the primary checkout cannot be located: git could not be run"
    if proc.returncode != 0:
        return root, None
    lines = os.fsdecode(proc.stdout).split("\n")
    if len(lines) != 4 or lines[3] or not lines[0] or not lines[1]:
        return None, ("the primary checkout cannot be located (unexpected git "
                      "rev-parse output)")
    git_dir = os.path.realpath(os.path.join(root, lines[0]))
    common_dir = os.path.realpath(os.path.join(root, lines[1]))
    if git_dir == common_dir:
        return root, None
    return os.path.normpath(os.path.join(os.path.dirname(common_dir), lines[2])), None


class Checker(object):
    """The path rules, against one root and the config parse that set ``required``."""

    def __init__(self, root, document, where=CONFIG_RELPATH):
        self.root = root
        self.document = document if isinstance(document, dict) else {}
        self.where = where
        self._base = None

    def base(self):
        """:func:`sibling_base` for this root, located once per run."""
        if self._base is None:
            self._base = sibling_base(self.root)
        return self._base

    def repo_dir(self, repo_id):
        """``(directory, None)`` for a repo id (``None`` = the root), or ``(None, why)``."""
        if repo_id is None:
            return self.root, None
        repos = self.document.get("repos")
        if not isinstance(repos, dict) or repo_id not in repos:
            return None, ("repo '%s' is not declared under repos: in %s"
                          % (repo_id, self.where))
        entry = repos[repo_id]
        if not isinstance(entry, dict):
            return None, "repos.%s in %s is not a mapping" % (repo_id, self.where)
        if entry.get("primary") in ("true", True):
            return self.root, None
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            return None, "repos.%s in %s declares no path" % (repo_id, self.where)
        if os.path.isabs(path):
            target, shown = path, "its repos.%s.path" % repo_id
        else:
            base, why = self.base()
            if why:
                return None, "repo '%s' cannot be resolved: %s" % (repo_id, why)
            target, shown = os.path.normpath(os.path.join(base, path)), path
        if not os.path.isdir(target):
            return None, "repo '%s' is not cloned at %s" % (repo_id, shown)
        return target, None

    def entry_reason(self, entry, position, bug_id, require_committed=False):
        """``None`` when one ``regression_tests`` entry passes, else why it fails.

        ``require_committed`` (``--require-recorded``) also requires the file to
        be committed in its repository's ``HEAD``, that copy citing the id
        (:func:`committed_reason`).
        """
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
        if require_committed:
            why = committed_reason(repo_dir, rel, bug_id)
            if why:
                return "%s %s" % (shown, why)
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
                why = self.entry_reason(entry, position, report.bug_id, require_recorded)
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


def _duplicate_reason(count):
    return "%d reports in %s carry this id" % (count, BUGS_RELDIR)


def check(root, ids=(), require_recorded=False, ref=None):
    """Run the check. Returns ``(setting, results)``; ``results`` is ``None`` when off.

    ``ref`` is ``--base``: the setting and ``repos:`` come from the config
    committed there, the bug reports and tests from the working tree and index.
    Each result is ``(label, class, reasons)``. Raises :class:`RegressionCheckError`
    for anything that prevents a decision.
    """
    setting = read_setting(root, ref)
    if setting.mode == MODE_OFF:
        return setting, None  # BR-11: no bug report is opened
    checker = Checker(root, setting.document, config_where(ref))
    for rel in (".adlc", BUGS_RELDIR):
        # A link may stay inside the root; one that leaves it would judge
        # another tree's reports as this project's.
        full = os.path.join(root, *rel.split("/"))
        if os.path.lexists(full) and not inside_root(root, full):
            raise RegressionCheckError("%s resolves outside the project root" % rel)
    bugs_dir = os.path.join(root, *BUGS_RELDIR.split("/"))
    results = []
    names = list_reports(bugs_dir)
    by_id = collections.defaultdict(list)
    for name in names:
        match = _REPORT_NAME_RE.match(name)
        if match:
            by_id[match.group(1)].append(name)
    if ids:
        for bug_id in ids:
            found = by_id.get(bug_id, [])
            if not found:
                results.append((bug_id, FAILED, ["no bug report in %s" % BUGS_RELDIR]))
                continue
            if len(found) > 1:
                results.append((bug_id, FAILED, [_duplicate_reason(len(found))]))
                continue
            report = read_report(os.path.join(bugs_dir, found[0]), found[0])
            cls, reasons = checker.classify(report, require_recorded)
            results.append((report.label, cls, reasons))
        return setting, results
    for name in names:
        report = read_report(os.path.join(bugs_dir, name), name)
        if report.status_known() and report.status not in IN_SCOPE_STATUSES:
            continue
        carriers = len(by_id.get(report.bug_id, ())) if report.bug_id else 0
        if carriers > 1:
            # The named run's verdict for this id, so the two runs agree.
            results.append((report.label, FAILED, [_duplicate_reason(carriers)]))
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
    parser.add_argument("--base", default=None)
    if verb == "check":
        parser.add_argument("--require-recorded", action="store_true")
        parser.add_argument("ids", nargs="*")
    # Intermixed, so `check BUG-1 --require-recorded BUG-2` keeps both ids.
    args = parser.parse_intermixed_args(argv[1:])
    args.verb = verb
    if args.base is not None:
        check_ref(args.base)
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
            setting = read_setting(root, args.base)
            lines, rc = [MODE_LINE + setting.mode, setting_line(setting)], RC_PASS
        else:
            setting, results = check(root, args.ids, args.require_recorded, args.base)
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
