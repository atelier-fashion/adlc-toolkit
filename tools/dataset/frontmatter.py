"""A strict recognizer for the corpus's frontmatter (REQ-671 BR-5).

The corpus writes one-line ``key: value`` frontmatter throughout. This module
accepts exactly that and nothing looser: a line it cannot read is a finding,
never a skipped line (LESSON-716 point 2). The caller scrubs the raw text
first, so a credential behind a misspelt key has already been replaced by the
time a line reaches this module (LESSON-716 point 3).

The block opens at the first line that is neither blank nor inside a leading
HTML comment, which must be exactly ``---``, and closes at the next ``---``
(the ``partials/lesson-check.sh`` rule).
"""
import re
from collections import namedtuple

Finding = namedtuple("Finding", "line reason")
Split = namedtuple("Split", "lines first_line body")

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*?))?[ \t]*$")
_TRAILING_COMMENT_RE = re.compile(r"[ \t]+#.*$")


def split(text):
    """Split ``text`` into frontmatter lines and body.

    Returns ``(split, finding)``. ``split`` is ``None`` when there is no
    frontmatter block. ``finding`` is set when a block opens and never closes.
    ``split.first_line`` is the 1-based line number of the first frontmatter
    line, so findings point at the source.
    """
    lines = text.split("\n")
    i = 0
    in_comment = False
    while i < len(lines):
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
    if i >= len(lines) or lines[i] != "---":
        return None, None
    for j in range(i + 1, len(lines)):
        if lines[j] == "---":
            return Split(lines[i + 1:j], i + 2, "\n".join(lines[j + 1:])), None
    return None, Finding(i + 1, "frontmatter opens with --- and never closes")


def _quoted(value, quote):
    """Parse a quoted scalar at the start of ``value``; return (str, rest) or None."""
    out = []
    k = 1
    while k < len(value):
        ch = value[k]
        if quote == '"' and ch == "\\" and k + 1 < len(value):
            out.append(value[k + 1])
            k += 2
            continue
        if ch == quote:
            if quote == "'" and value[k + 1:k + 2] == "'":
                out.append("'")
                k += 2
                continue
            return "".join(out), value[k + 1:]
        out.append(ch)
        k += 1
    return None


def _rest_is_comment(rest):
    return not rest.strip() or re.match(r"^[ \t]+#", rest) is not None


def _flow_list(value):
    """Parse ``[a, "b", 'c']`` closed on this line; return (list, rest) or None."""
    items = []
    k = 1
    while True:
        while k < len(value) and value[k] in " \t":
            k += 1
        if k >= len(value):
            return None
        if value[k] == "]" and not items:
            return items, value[k + 1:]
        if value[k] in "\"'":
            parsed = _quoted(value[k:], value[k])
            if parsed is None:
                return None
            item, tail = parsed
            k = len(value) - len(tail)
        else:
            m = re.match(r"[^,\]\[{}\"']*", value[k:])
            item = m.group(0).strip()
            k += m.end()
            if not item:
                return None
        items.append(item)
        while k < len(value) and value[k] in " \t":
            k += 1
        if k >= len(value):
            return None
        if value[k] == ",":
            k += 1
            continue
        if value[k] == "]":
            return items, value[k + 1:]
        return None


def parse_value(raw):
    """Return the parsed value, or ``None`` when the line cannot be read."""
    if raw is None or raw == "":
        return ""
    if raw[0] in "\"'":
        parsed = _quoted(raw, raw[0])
        if parsed is None or not _rest_is_comment(parsed[1]):
            return None
        return parsed[0]
    if raw[0] == "[":
        parsed = _flow_list(raw)
        if parsed is None or not _rest_is_comment(parsed[1]):
            return None
        return parsed[0]
    if raw[0] in "{|>&*!":
        return None
    return _TRAILING_COMMENT_RE.sub("", raw).strip()


def parse(split_):
    """Parse a :class:`Split`; return ``(fields, findings)``."""
    fields = {}
    findings = []
    for offset, line in enumerate(split_.lines):
        lineno = split_.first_line + offset
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _KEY_RE.match(line)
        if not m:
            findings.append(Finding(lineno, "not a 'key: value' line"))
            continue
        key, raw = m.group(1), m.group(2)
        if key in fields:
            findings.append(Finding(lineno, "repeated key %r" % key))
            continue
        value = parse_value(raw)
        if value is None:
            findings.append(Finding(lineno, "value of %r cannot be read on one line" % key))
            continue
        fields[key] = value
    return fields, findings
