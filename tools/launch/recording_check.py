#!/usr/bin/env python3
"""The checks a demo recording passes before it is committed (REQ-672 BR-4, architecture ADR-6).

    python3 tools/launch/recording_check.py CAST [--gif GIF] [--forbid STR ...] [--denylist PATH]

CAST is an asciicast v2 or v3 file, read strictly: a line of any other shape is a
``malformed`` failure that names the line, never a skipped line. The format facts relied on,
from the asciicast documentation: v2 is a JSON header (``version`` 2, ``width``, ``height``)
then one ``[time, code, data]`` event per line, ``time`` in seconds from the start, codes
``o``, ``i``, ``m``, ``r``. v3's header has ``version`` 3 and ``term: {cols, rows, type,
theme}``; its times are intervals since the event before, its codes add ``x`` (the exit
status), and a line after the header that starts with ``#`` is a comment. A v3 cast is read
as v2: times summed (to the microsecond), ``term`` as ``width``, ``height``, ``env.TERM``
and ``theme``, comments and ``x`` events dropped. No real asciinema has run against this
code: the tests' fakes write both shapes. The checks:

- ``length``: the last event's time is over 60 seconds (the header's ``duration`` is not
  trusted);
- ``gif-size``: the GIF is over 5 MB;
- ``empty``: the cast has no output event;
- ``home-path``: a ``/Users/<name>/`` (in any case) or ``/home/<name>`` path, except a
  URL's own (:func:`_first_home_path`); or a Windows users directory;
- ``credential``: a credential shape, by ``tools/adlc/credential_redact.py``'s chains, over
  each line in overlapping windows (one chain is quadratic on a long line);
- ``oversize``: the output drawn passes :data:`MAX_RENDER` characters: no content check runs;
- ``denylist``: a name ``tools/dataset/denylist.json`` lists: each private repository and
  its aliases and each person, as whole words in any case with ``-``, ``_``, a space or
  nothing between their parts (``tools/dataset/detectors.py``'s ``name_pattern``), the
  organization's name used as a repository, and ``<organization>/<name>`` or a GitHub URL
  for a name the list does not call public;
- ``forbidden``: a ``--forbid`` string as a whole word in any case (:func:`word_pattern`).

The content checks read three views of the data of all the output events joined, so text
split across two events is still found: as recorded; with escape sequences and control
characters removed, so a path with colour codes inside it is still found; and as a
terminal draws it (:func:`render`), so a backspace, a cursor move or an :func:`invisible`
character inside a word does not hide it. They read the header and the other events the
same way. A failure names its check and where it was found (``event N (cast line L)``,
events numbered from 1), never the text it matched.

Output: ``recording-check: duration=<s>s events=<n> gif=<bytes|none>``, then ``PASS`` or
one ``FAIL <check>: <reason>`` line per failed check. Exit 0 on a pass, 1 on a failure, 2
when an input cannot be read or the arguments are refused. Python 3.9, stdlib only.
"""

import argparse
import bisect
import collections
import json
import math
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.realpath(__file__))
TOOLKIT = os.path.dirname(os.path.dirname(HERE))
for _folder in ("adlc", "dataset"):
    _path = os.path.join(TOOLKIT, "tools", _folder)
    if _path not in sys.path:
        sys.path.append(_path)

import credential_redact  # noqa: E402
import denylist as denylist_mod  # noqa: E402
import detectors  # noqa: E402

DEFAULT_DENYLIST = os.path.join(TOOLKIT, *denylist_mod.REPO_PATH.split("/"))
MAX_SECONDS = 60.0
MAX_BYTES = 5 * 1024 * 1024
OUTPUT = "o"
#: asciicast v2's event codes: output, input, marker, resize.
EVENT_CODES = (OUTPUT, "i", "m", "r")
#: v3's: v2's and ``x``, the exit status, dropped on read.
V3_CODES = EVENT_CODES + ("x",)
CAST_NAME, GIF_NAME = "demo.cast", "demo.gif"

#: :func:`render`'s widest line, whatever the header says, and the most text it builds.
MAX_WIDTH, MAX_RENDER = 1000, 4 * 1024 * 1024
#: The credential chains read a line in windows this long, each overlapping the last by this.
CREDENTIAL_WINDOW, CREDENTIAL_OVERLAP = 2000, 256

LENGTH, GIF_SIZE, EMPTY, MALFORMED = "length", "gif-size", "empty", "malformed"
HOME_PATH, CREDENTIAL, DENYLIST, FORBIDDEN = "home-path", "credential", "denylist", "forbidden"
OVERSIZE = "oversize"
#: ``docs/demo.cast`` and ``docs/demo.gif`` are committed together or not at all.
PAIR = "pair"
EXIT_PASS, EXIT_FAIL, EXIT_UNREADABLE = 0, 1, 2

Failure = collections.namedtuple("Failure", "check reason")

#: ``/Users/`` in any case, ``/home/<name>`` and ``C:\Users\``.
HOME_PATH_RE = re.compile(r"/[Uu][Ss][Ee][Rr][Ss]/|/home/[^/\s]"
                          r"|[A-Za-z]:\\[Uu][Ss][Ee][Rr][Ss]\\")
#: What ends, leftwards, the token a path sits in: whitespace, a quote, a bracket, ``=``.
TOKEN_EDGE_RE = re.compile(r"[\s\"'`(<\[{=]")
#: A URL scheme, ending where its ``://`` starts.
SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*\Z")

#: What a terminal draws but a reader does not see: escape sequences, and every control
#: character but tab and newline.
ESCAPE_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"              # CSI: colour, cursor movement
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"     # OSC: title, hyperlink
    r"|\x1b[PX^_][^\x1b]*\x1b\\"              # DCS, SOS, PM, APC
    r"|\x1b[ -/]*[0-~]"                       # any other escape
    r"|\x9b[0-?]*[ -/]*[@-~]"                 # 8-bit CSI
    r"|[\x00-\x08\x0b-\x1f\x7f]")
#: The line edits :func:`render` applies: cursor right, cursor left, cursor to a column
#: (``G``, and HPA's backtick), erase to the line's end.
LINE_EDIT_RE = re.compile(r"\x1b\[([0-9]*)([CDGK`])")
#: A run of printable ASCII, which :func:`render` writes in one step.
PLAIN_RE = re.compile(r"[ -~]{1,4096}")
#: A GitHub login's characters: a whole word is not next to one.
LOGIN_CHAR = "[A-Za-z0-9-]"

#: Each content check and how a failure names what it found, never the text itself.
CONTENT_CHECKS = ((HOME_PATH, "a home-directory path"), (CREDENTIAL, "a credential shape"),
                  (DENYLIST, "a DenyList name"), (FORBIDDEN, "a forbidden string"))


class CastError(Exception):
    """The cast is not a well-formed asciicast v2 or v3 file; ``line`` counts from 1."""

    def __init__(self, line, reason):
        Exception.__init__(self, "line %d: %s" % (line, reason))
        self.line, self.reason = line, reason


def _refuse_constant(name):
    raise ValueError("%s is not a JSON number" % name)


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _size(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _header(value):
    """``(header in v2's shape, version)``: a v3 header's ``term`` mapped, every key kept."""
    if not isinstance(value, dict):
        raise CastError(1, "the header is not a JSON object")
    version = value.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version not in (2, 3):
        raise CastError(1, "the header's version is not 2 or 3: only asciicast v2 and v3 are read")
    names = {"width": "width", "height": "height"}
    if version == 3:
        term = value.get("term")
        if not isinstance(term, dict):
            raise CastError(1, "the header's term is not a JSON object")
        value = dict(value, version=2, width=term.get("cols"), height=term.get("rows"))
        names, env = {"width": "term.cols", "height": "term.rows"}, value.get("env", {})
        if isinstance(env, dict) and isinstance(term.get("type"), str):
            value["env"] = dict({"TERM": term["type"]}, **env)
        if "theme" in term:
            value["theme"] = term["theme"]
    for key in ("width", "height"):
        if not _size(value.get(key)):
            raise CastError(1, "the header's %s is not a positive integer" % names[key])
    if "duration" in value and not _number(value["duration"]):
        raise CastError(1, "the header's duration is not a number")
    return value, version


def _event(value, line, codes):
    if not isinstance(value, list) or len(value) != 3:
        raise CastError(line, "the event is not a [time, code, data] list")
    time, code, data = value
    if not _number(time) or time < 0:
        raise CastError(line, "the event time is not a non-negative number")
    if not isinstance(code, str) or code not in codes:
        raise CastError(line, "the event code is not one of %s" % ", ".join(codes))
    if not isinstance(data, str):
        raise CastError(line, "the event data is not a string")
    return float(time), code, data


def read_cast(path):
    """``(header, events, lines)`` of the cast at ``path``, v3 read as v2; each event is
    ``(time, code, data)``, ``lines[i]`` the file line of event ``i``. Raises
    :class:`CastError` on a line of another shape, ``OSError`` when it cannot be read."""
    with open(path, "rb") as handle:
        raws = handle.read().split(b"\n")
    if raws[-1] == b"":
        raws.pop()
    if not raws:
        raise CastError(1, "the file is empty: there is no header")
    header, version, events, lines, clock = None, 2, [], [], 0.0
    for number, raw in enumerate(raws, 1):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise CastError(number, "not UTF-8")
        if version == 3 and text.startswith("#"):
            continue
        if not text.strip():
            raise CastError(number, "a blank line")
        try:
            value = json.loads(text, parse_constant=_refuse_constant)
        except ValueError as exc:
            raise CastError(number, "not JSON (%s)" % exc)
        if number == 1:
            header, version = _header(value)
            continue
        time, code, data = _event(value, number, V3_CODES if version == 3 else EVENT_CODES)
        if version == 3:
            time = clock = round(clock + time, 6)
            if code == "x":
                continue
        elif events and time < events[-1][0]:
            raise CastError(number, "the event time is earlier than the event before it")
        events.append((time, code, data))
        lines.append(number)
    return header, events, lines


def load_cast(path):
    """``(header, events)`` of the cast at ``path``: :func:`read_cast` without the lines."""
    return read_cast(path)[:2]


def duration(events):
    """The cast's length: the last event's time, never the header's ``duration``."""
    return events[-1][0] if events else 0.0


def strip_escapes(text):
    """``(stripped, segments)``: ``text`` without :data:`ESCAPE_RE` matches, and for each
    kept run ``(offset in stripped, offset in text)``."""
    kept, segments, last, size = [], [], 0, 0
    for match in ESCAPE_RE.finditer(text):
        if match.start() > last:
            segments.append((size, last))
            kept.append(text[last:match.start()])
            size += match.start() - last
        last = match.end()
    if last < len(text):
        segments.append((size, last))
        kept.append(text[last:])
    return "".join(kept), segments


def invisible(char):
    """True for what a terminal draws as nothing: a format character (category ``Cf``),
    the combining grapheme joiner, a variation selector."""
    return (unicodedata.category(char) == "Cf" or char == "\u034f"
            or "\ufe00" <= char <= "\ufe0f")


class Oversize(Exception):
    """:func:`render` would build more than :data:`MAX_RENDER` characters."""


def _count(digits, width):
    """An escape's number: 1 when absent or 0, at most ``width``, however many digits."""
    digits = digits.lstrip("0")
    return width if len(digits) > 9 else min(int(digits or "1"), width)


def render(text, width=80):
    """``(rendered, origins)``: ``text`` as a terminal ``width`` (at most :data:`MAX_WIDTH`)
    wide draws it, line by line; ``origins[i]`` is the offset in ``text`` of the character
    drawn at ``i``. A character is written over the one under the cursor; backspace and ``ESC
    [ n D`` move it left, ``ESC [ n C`` right (to the line's end or last column), ``ESC [ n
    G`` and HPA (``ESC [ n`` and a backtick) to column ``n``, carriage return to the start;
    ``ESC [ K`` erases to the end. Other escapes and controls, and :func:`invisible`
    characters, draw nothing. Raises :class:`Oversize` past :data:`MAX_RENDER` characters."""
    width = max(1, min(width, MAX_WIDTH))
    drawn, origins, line, source, col, at = [], [], [], [], 0, 0
    while at < len(text):
        char, end = text[at], at + 1
        plain = PLAIN_RE.match(text, at)
        edit = LINE_EDIT_RE.match(text, at) if char == "\x1b" else None
        control = (char < " " or char in "\x7f\x9b") and char not in "\r\n\b"
        other = ESCAPE_RE.match(text, at) if control and not edit else None
        if edit:
            end, count, kind = edit.end(), _count(edit.group(1), width), edit.group(2)
            if kind == "C":
                col = min(col + count, max(len(line), width - 1))
            elif kind == "D":
                col = max(col - count, 0)
            elif kind in "G`":
                col = count - 1
            elif edit.group(1) in ("", "0"):
                del line[col:], source[col:]
        elif char == "\n":
            drawn += line + ["\n"]
            origins += source + [at]
            line, source, col = [], [], 0
        elif char in "\r\b":
            col = 0 if char == "\r" else max(col - 1, 0)
        elif other:
            end = other.end()
        elif plain or not invisible(char):
            end = plain.end() if plain else end
            if col > len(line):
                line += [" "] * (col - len(line))
                source += [at] * (col - len(source))
            line[col:col + end - at] = text[at:end]
            source[col:col + end - at] = range(at, end)
            col += end - at
        if len(drawn) + len(line) > MAX_RENDER:
            raise Oversize()
        at = end
    return "".join(drawn + line), origins + source


class View(object):
    """A text the content checks read, and how to say where an offset in it came from."""

    def __init__(self, text, where):
        self.text, self.where = text, where


def _views(text, where, width):
    """``text`` as recorded, with escapes removed, and as a terminal draws it: each view
    that differs from those before it."""
    views = [View(text, where)]
    stripped, segments = strip_escapes(text)
    if stripped != text:
        runs = [segment[0] for segment in segments]

        def where_stripped(at):
            run, origin = segments[bisect.bisect_right(runs, at) - 1]
            return where(origin + at - run) + ", once escape sequences are removed"

        views.append(View(stripped, where_stripped))
    rendered, origins = render(text, width)
    if rendered not in (text, stripped):
        views.append(View(rendered, lambda at: where(origins[at]) + ", as a terminal draws it"))
    return views


def _event_views(events, wanted, lines, width):
    """The :func:`_views` of the joined data of the events whose code ``wanted`` accepts."""
    starts, numbers, pieces, offset = [], [], [], 0
    for number, (_, code, data) in enumerate(events):
        if wanted(code) and data:
            starts.append(offset)
            numbers.append(number)
            pieces.append(data)
            offset += len(data)
    if not pieces:
        return []

    def where(at):
        number = numbers[bisect.bisect_right(starts, at) - 1]
        return "at event %d (cast line %d)" % (number + 1, lines[number])

    return _views("".join(pieces), where, width)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            for text in _strings(item):
                yield text
    elif isinstance(value, list):
        for item in value:
            for text in _strings(item):
                yield text


def _url_schemes(text):
    """The offset of each ``://`` in ``text`` that follows a URL scheme."""
    found, at = [], text.find("://")
    while at >= 0:
        if SCHEME_RE.search(text, max(0, at - 32), at):
            found.append(at)
        at = text.find("://", at + 1)
    return found


def _first_home_path(text):
    """Where a home path first appears in ``text``. A POSIX one is skipped only as a URL's:
    its token (back to whitespace, a quote, a bracket or ``=``) holds a scheme's ``://`` and
    a host before it, or that ``://`` ends on its first slash. ``file:///`` (no host) is a hit."""
    edges = schemes = None
    for match in HOME_PATH_RE.finditer(text):
        at = match.start()
        if text[at] != "/":
            return at
        if edges is None:
            edges = [edge.start() for edge in TOKEN_EDGE_RE.finditer(text)]
            schemes = _url_schemes(text)
        index = bisect.bisect_left(edges, at)
        token = edges[index - 1] + 1 if index else 0
        lo, hi = bisect.bisect_left(schemes, token), bisect.bisect_right(schemes, at - 2)
        if not (hi - lo > 1 or (hi - lo == 1 and schemes[lo] != at - 3)):
            return at
    return None


def _windows(text):
    """``(offset, piece)`` for each line of ``text``, one longer than :data:`CREDENTIAL_WINDOW`
    in windows that long, each overlapping the last by :data:`CREDENTIAL_OVERLAP`: a shape
    no longer than that is whole in one of them."""
    step, offset = CREDENTIAL_WINDOW - CREDENTIAL_OVERLAP, 0
    for line in text.split("\n"):
        for start in range(0, max(len(line) - CREDENTIAL_OVERLAP, 1), step):
            yield offset + start, line[start:start + CREDENTIAL_WINDOW]
        offset += len(line) + 1


def _first_credential(text):
    """Where a credential shape first appears in ``text``, window by window
    (:func:`_windows`): a ``credential_redact`` chain is quadratic on a long line."""
    patterns = credential_redact.ALL_PATTERNS
    for offset, piece in _windows(text):
        if credential_redact.find(piece, patterns):
            return offset + min(m.start() for m in (p.search(piece) for p in patterns) if m)
    return None


class DenyListMatcher(object):
    """Where a DenyList name first appears in a text, by ``tools/dataset/detectors.py``;
    stricter than the dataset scrub, as a recording is published as it is: a
    ``repo-context`` entry is a hit in prose too, like a ``token`` entry."""

    def __init__(self, dl):
        names = [name for repo in dl.repos for name in (repo.name,) + tuple(repo.aliases)]
        names += [person.name for person in dl.people]
        self.names = detectors.name_pattern(names) if names else None
        self.detectors = detectors.Detectors(dl)
        #: The organization's name used as a repository: not followed by ``/<name>``.
        self.org = (detectors.name_pattern([dl.organization], detectors.SEPARATOR_NO_SPACE)
                    if dl.organization_repo else None)

    def first(self, text):
        found = []
        match = self.names.search(text) if self.names else None
        if match:
            found.append(match.start())
        det = self.detectors
        for hits in (det.private_url_hits(text), det.org_ns_hits(text, det.public)):
            if hits:
                found.append(hits[0].start())
        for match in self.org.finditer(text) if self.org else ():
            if not re.match(r"/[A-Za-z0-9]", text[match.end():match.end() + 2]):
                found.append(match.start())
                break
        return min(found) if found else None


def word_pattern(text):
    """``text`` as a whole word, in any case (GitHub logins ignore case): not preceded or
    followed by :data:`LOGIN_CHAR` where its own end is one. The one matcher for a login:
    ``record_demo.py`` replaces the repo's owner with it, and ``forbidden`` finds it."""
    head = "(?<!%s)" % LOGIN_CHAR if re.match(LOGIN_CHAR, text[:1]) else ""
    tail = "(?!%s)" % LOGIN_CHAR if re.match(LOGIN_CHAR, text[-1:]) else ""
    return re.compile(head + re.escape(text) + tail, re.IGNORECASE)


def _forbidden(forbid):
    patterns = [word_pattern(text) for text in forbid]

    def first(text):
        found = [m.start() for m in (p.search(text) for p in patterns) if m]
        return min(found) if found else None

    return first


def forbid_list(forbid):
    """``forbid`` as a list; ``ValueError`` for an empty string, which every text holds."""
    forbid = list(forbid)
    if any(not isinstance(text, str) or not text.strip() for text in forbid):
        raise ValueError("a --forbid string is empty")
    return forbid


def load_denylist(path=None):
    """The DenyList at ``path``, default the repository's; ``DenyListError`` when unreadable."""
    return denylist_mod.load(path or DEFAULT_DENYLIST)


def check_events(header, events, forbid=(), denylist=None, max_seconds=MAX_SECONDS,
                 lines=None):
    """The length, ``empty``, ``oversize`` and content failures of a loaded cast; [] passes.
    ``lines`` are the events' file lines (:func:`read_cast`), default a v2 file's."""
    forbid = forbid_list(forbid)
    lines = lines or [number + 2 for number in range(len(events))]
    width = min(header.get("width") or 80, MAX_WIDTH)
    dl = denylist if denylist is not None else load_denylist()
    failures = []
    total = duration(events)
    if total > max_seconds:
        failures.append(Failure(LENGTH, "the cast runs %.2fs, over the %gs limit"
                                % (total, max_seconds)))
    if not any(code == OUTPUT and data for _, code, data in events):
        failures.append(Failure(EMPTY, "the cast has no output events"))
    try:
        views = (_event_views(events, lambda code: code == OUTPUT, lines, width)
                 + _event_views(events, lambda code: code != OUTPUT, lines, width)
                 + _views("\n".join(_strings(header)), lambda _at: "in the cast header", width))
    except Oversize:
        return failures + [Failure(OVERSIZE, "the recording's output is too large to check")]
    finders = {HOME_PATH: _first_home_path, CREDENTIAL: _first_credential,
               DENYLIST: DenyListMatcher(dl).first, FORBIDDEN: _forbidden(forbid)}
    for name, what in CONTENT_CHECKS:
        for view in views:
            at = finders[name](view.text)
            if at is not None:
                failures.append(Failure(name, "%s %s" % (what, view.where(at))))
                break
    return failures


def gif_size(path):
    """The size in bytes of the GIF at ``path``; ``OSError`` when it is not a file."""
    if not os.path.isfile(path):
        raise OSError("%s is not a file" % path)
    return os.path.getsize(path)


def _gif_failures(size, max_bytes):
    if size is None or size <= max_bytes:
        return []
    return [Failure(GIF_SIZE, "the GIF is %d bytes, over the %d-byte limit" % (size, max_bytes))]


def check(cast_path, gif_path=None, *, forbid=(), denylist=None, max_seconds=MAX_SECONDS,
          max_bytes=MAX_BYTES):
    """Every failure of the cast at ``cast_path`` and the GIF at ``gif_path``; [] is a pass.
    ``denylist`` is a parsed DenyList (``tools/dataset/denylist.py``), default the
    repository's. Raises ``OSError`` when a file cannot be read, ``DenyListError`` when the
    DenyList cannot, and ``ValueError`` for an empty ``forbid`` string."""
    forbid = forbid_list(forbid)
    dl = denylist if denylist is not None else load_denylist()
    size = gif_size(gif_path) if gif_path is not None else None
    try:
        header, events, lines = read_cast(cast_path)
    except CastError as exc:
        failures = [Failure(MALFORMED, str(exc))]
    else:
        failures = check_events(header, events, forbid, dl, max_seconds, lines)
    return failures + _gif_failures(size, max_bytes)


def check_committed(root=TOOLKIT, **options):
    """``(failures, notice)`` for the recording committed under ``<root>/docs``. Neither
    file: no failure, and a notice that says so. One without the other: a ``pair``
    failure. Both: :func:`check` over them, with ``options``."""
    names = ["docs/" + CAST_NAME, "docs/" + GIF_NAME]
    paths = [os.path.join(root, *name.split("/")) for name in names]
    present = [os.path.lexists(path) for path in paths]
    if not any(present):
        return [], "no recording is committed: neither %s nor %s exists" % tuple(names)
    if not all(present):
        have, lack = names if present[0] else names[::-1]
        return [Failure(PAIR, "%s exists without %s: the two are committed together or not "
                              "at all" % (have, lack))], None
    return check(paths[0], paths[1], **options), None


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="recording_check.py", description=(
        "Check a demo recording's length, size and content before it is committed."))
    parser.add_argument("cast", metavar="CAST", help="an asciinema v2 or v3 cast")
    parser.add_argument("--gif", metavar="GIF", help="the GIF rendered from it")
    parser.add_argument("--forbid", metavar="STR", nargs="+", action="extend", default=[],
                        help="a string the recording must not hold, as a whole word in any case")
    parser.add_argument("--denylist", metavar="PATH",
                        help="default %s" % denylist_mod.REPO_PATH)
    return parser.parse_args(argv)


def main(argv=None, stdout=None, stderr=None):
    out, err = stdout or sys.stdout, stderr or sys.stderr
    opts = parse_args(argv)
    try:
        forbid = forbid_list(opts.forbid)
        dl = load_denylist(opts.denylist)
        size = gif_size(opts.gif) if opts.gif is not None else None
        try:
            header, events, lines = read_cast(opts.cast)
        except CastError as exc:
            failures, summary = [Failure(MALFORMED, str(exc))], "duration=unknown events=unknown"
        else:
            failures = check_events(header, events, forbid, dl, lines=lines)
            summary = "duration=%.2fs events=%d" % (duration(events), len(events))
    except ValueError as exc:
        err.write("recording-check: refused: %s\n" % exc)
        return EXIT_UNREADABLE
    except (OSError, denylist_mod.DenyListError) as exc:
        err.write("recording-check: cannot read an input: %s\n" % exc)
        return EXIT_UNREADABLE
    failures += _gif_failures(size, MAX_BYTES)
    out.write("recording-check: %s gif=%s\n" % (summary, "none" if size is None else size))
    for failure in failures:
        out.write("FAIL %s: %s\n" % failure)
    if not failures:
        out.write("PASS\n")
    return EXIT_FAIL if failures else EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
