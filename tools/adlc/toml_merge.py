#!/usr/bin/env python3
"""toml_merge — own a few keys in a TOML file someone else owns (REQ-655 BR-5).

Not a TOML parser. A line scanner that knows quotes and bracket depth, classifies
top-level keys and table headers, and fails closed on any construct it cannot
classify unambiguously: a reader that skips what it does not understand fails open,
and this one decides whether a sandbox posture took effect (LESSON-716). So every
refusal names the construct and writes nothing, and every merge re-classifies its
own output before returning it.

`[projects."<path>"]` is a quoted header the trust step itself writes, so a quoted
header naming another table is classified. Only a spelling of the owned table is
refused, because a literal search would miss it.

Pure standard library, on Python 3.9: no ``tomllib`` (LESSON-395).
"""

import json
import re
from collections import OrderedDict

_BARE_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")
_MULTI_QUOTES = ('"""', "'''")


class TomlConstructError(ValueError):
    """A construct the scanner will not classify; ``construct`` names it."""

    def __init__(self, construct, line=None):
        self.construct = construct
        self.line = line
        where = " at line %d" % line if line else ""
        super().__init__("%s%s" % (construct, where))


class PostureRefused(ValueError):
    """An owned key already holds a value the adapter refuses."""

    def __init__(self, key, value):
        self.key = key
        self.value = value
        super().__init__("%s = %s" % (key, value))


class Scan(object):
    """What :func:`scan` saw: top-level keys, headers, and each table's keys."""

    def __init__(self):
        self.top = OrderedDict()        # key -> raw value text
        self.headers = []               # names, in order
        self.first_header_offset = None
        self.table_keys = {}            # table -> {key: (raw value, line start, line end)}
        self.table_end = {}             # table -> offset just past its header line


def _value_end(line, start, lineno):
    """The offset where a value ends in ``line``, past quotes and brackets."""
    if line.startswith(_MULTI_QUOTES, start):
        raise TomlConstructError("multi-line string", lineno)
    depth = 0
    quote = None
    i = start
    while i < len(line):
        ch = line[i]
        if quote:
            if quote == '"' and ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif line.startswith(_MULTI_QUOTES, i):
            raise TomlConstructError("multi-line string", lineno)
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth < 0:
                raise TomlConstructError("unbalanced bracket", lineno)
        elif ch == "#" and depth == 0:
            return i
        i += 1
    if quote:
        raise TomlConstructError("unterminated string", lineno)
    if depth:
        raise TomlConstructError("multi-line array", lineno)
    return len(line)


def _quoted_end(text, start, lineno):
    quote = text[start]
    i = start + 1
    while i < len(text):
        if text[i] == "\\" and quote == '"':
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    raise TomlConstructError("unterminated string", lineno)


def _key_parts(text, lineno):
    """``(parts, quoted, offset past the key)`` of the key opening ``text``."""
    parts = []
    quoted = False
    i = 0
    while True:
        while i < len(text) and text[i] in " \t":
            i += 1
        if i >= len(text):
            raise TomlConstructError("unclassifiable line", lineno)
        if text[i] in "\"'":
            end = _quoted_end(text, i, lineno)
            if "\\" in text[i:end]:
                raise TomlConstructError("escaped key", lineno)
            parts.append(text[i + 1:end - 1])
            quoted = True
            i = end
        else:
            match = _BARE_KEY_RE.match(text, i)
            if not match:
                raise TomlConstructError("unclassifiable line", lineno)
            parts.append(match.group(0))
            i = match.end()
        while i < len(text) and text[i] in " \t":
            i += 1
        if i < len(text) and text[i] == ".":
            i += 1
            continue
        return parts, quoted, i


def _header(stripped, lineno, owned_table):
    """The table name of a ``[header]`` line."""
    inner_end = None
    i = 1
    while i < len(stripped):
        ch = stripped[i]
        if ch in "\"'":
            i = _quoted_end(stripped, i, lineno)
            continue
        if ch == "]":
            inner_end = i
            break
        i += 1
    if inner_end is None:
        raise TomlConstructError("unterminated table header", lineno)
    tail = stripped[inner_end + 1:].strip()
    if tail and not tail.startswith("#"):
        raise TomlConstructError("unclassifiable line", lineno)
    inner = stripped[1:inner_end]
    parts, quoted, end = _key_parts(inner, lineno)
    if end != len(inner):
        raise TomlConstructError("unclassifiable line", lineno)
    name = ".".join(parts)
    if owned_table and name == owned_table:
        if quoted:
            raise TomlConstructError("quoted [%s] header" % owned_table, lineno)
        if inner != owned_table:
            raise TomlConstructError("spaced [%s] header" % owned_table, lineno)
    return name


def scan(text, owned_keys=(), owned_table=None, refuse_keys=()):
    """Classify ``text``; :class:`TomlConstructError` on anything ambiguous."""
    if text.startswith("﻿"):
        raise TomlConstructError("BOM")
    if "\r" in text:
        raise TomlConstructError("CRLF line endings")
    if text and not text.endswith("\n"):
        raise TomlConstructError("missing trailing newline")
    result = Scan()
    table = None
    offset = 0
    for lineno, line in enumerate(text.splitlines(True), 1):
        begin, offset = offset, offset + len(line)
        body = line.rstrip("\n")
        stripped = body.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[["):
            raise TomlConstructError("[[array-of-tables]]", lineno)
        if stripped.startswith("["):
            name = _header(stripped, lineno, owned_table)
            if name in result.headers:
                raise TomlConstructError("duplicate [%s] header" % name, lineno)
            result.headers.append(name)
            if result.first_header_offset is None:
                result.first_header_offset = begin
            result.table_keys[name] = OrderedDict()
            result.table_end[name] = offset
            table = name
            continue
        parts, quoted, end = _key_parts(body, lineno)
        if end >= len(body) or body[end] != "=":
            raise TomlConstructError("unclassifiable line", lineno)
        value_at = end + 1
        while value_at < len(body) and body[value_at] in " \t":
            value_at += 1
        value_end = _value_end(body, value_at, lineno)
        raw = body[value_at:value_end].rstrip()
        if not raw:
            raise TomlConstructError("key with no value", lineno)
        key = ".".join(parts)
        if table is None:
            if len(parts) > 1:
                raise TomlConstructError("dotted key", lineno)
            if quoted and key in owned_keys:
                raise TomlConstructError("quoted key spelling of %s" % key, lineno)
            if key in refuse_keys:
                raise TomlConstructError("top-level %s" % key, lineno)
            if raw.startswith("{"):
                raise TomlConstructError("top-level inline table", lineno)
            if key in result.top:
                raise TomlConstructError("duplicate key %s" % key, lineno)
            result.top[key] = raw
            continue
        if len(parts) == 1 and parts[0] in owned_keys:
            raise TomlConstructError("owned key %s inside a table" % parts[0], lineno)
        if table == owned_table and len(parts) > 1:
            raise TomlConstructError("dotted key", lineno)
        if key in result.table_keys[table]:
            raise TomlConstructError("duplicate key %s" % key, lineno)
        result.table_keys[table][key] = (raw, begin, begin + len(body))
    return result


def plain_string(raw):
    """The string a raw value spells, or ``None`` when it is not a plain string."""
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'" and "\\" not in raw:
        return raw[1:-1]
    return None


class Merge(object):
    __slots__ = ("text", "added", "kept", "conflicts")

    def __init__(self, text, added, kept, conflicts):
        self.text = text
        self.added = added
        self.kept = kept
        self.conflicts = conflicts


def render_values(values):
    return "".join("%s = %s\n" % (k, json.dumps(v)) for k, v in values.items())


def merge_owned(text, values, refuse=None, refuse_keys=(), owned_table=None):
    """Add or keep the owned ``values``; every other byte stays where it is.

    An owned key holding another value is left and reported; one holding a value in
    ``refuse`` raises :class:`PostureRefused`, because a merge then cannot say the
    posture is set.
    """
    owned = tuple(values)
    found = scan(text, owned, owned_table, refuse_keys)
    refuse = refuse or {}
    added, kept, conflicts = [], [], []
    for key, want in values.items():
        if key not in found.top:
            added.append(key)
            continue
        have = plain_string(found.top[key])
        if have is None:
            # An escape can spell a refused value, so it cannot be left as a conflict.
            raise TomlConstructError("%s is not a plain string" % key)
        if have in refuse.get(key, ()):
            raise PostureRefused(key, have)
        if have == want:
            kept.append(key)
        else:
            conflicts.append("%s = %s (the render says %s)"
                             % (key, found.top[key], json.dumps(want)))
    if not added:
        return Merge(text, added, kept, conflicts)
    block = render_values(OrderedDict((k, values[k]) for k in added))
    at = found.first_header_offset
    if at is None:
        at = len(text)
    else:
        block += "\n"
    out = text[:at] + block + text[at:]
    again = scan(out, owned, owned_table, refuse_keys)
    if any(k not in again.top for k in owned) or out[:at] + out[at + len(block):] != text:
        raise TomlConstructError("re-classification failed")
    return Merge(out, added, kept, conflicts)


def _array_items(raw):
    """The strings of a one-line array of strings, or ``None`` for anything else."""
    if not (raw.startswith("[") and raw.endswith("]")):
        return None
    inner = raw[1:-1].strip()
    items = []
    i = 0
    while i < len(inner):
        if inner[i] not in "\"'":
            return None
        end = _quoted_end(inner, i, None)
        items.append(inner[i + 1:end - 1])
        i = end
        while i < len(inner) and inner[i] in " \t":
            i += 1
        if i < len(inner):
            if inner[i] != ",":
                return None
            i += 1
            while i < len(inner) and inner[i] in " \t":
                i += 1
    return items


def union_list(text, table, key, item):
    """``text`` with ``item`` in the ``key`` array of ``[table]``; nothing is removed."""
    found = scan(text, owned_table=table)
    spelled = json.dumps(item)
    if table not in found.table_keys:
        block = "[%s]\n%s = [%s]\n" % (table, key, spelled)
        out = text + ("\n" if text else "") + block
    elif key not in found.table_keys[table]:
        at = found.table_end[table]
        out = text[:at] + "%s = [%s]\n" % (key, spelled) + text[at:]
    else:
        raw, begin, end = found.table_keys[table][key]
        items = _array_items(raw)
        if items is None:
            raise TomlConstructError("%s is not a one-line array of strings" % key)
        if item in items:
            return text
        close = text.index(raw, begin, end) + len(raw) - 1
        body = raw[1:-1].strip()
        out = text[:close].rstrip(" \t") + (", " if body else "") + spelled + text[close:]
    again = scan(out, owned_table=table)
    after = _array_items(again.table_keys[table][key][0])
    before = []
    if table in found.table_keys and key in found.table_keys[table]:
        before = _array_items(found.table_keys[table][key][0])
    if after is None or item not in after or any(old not in after for old in before):
        raise TomlConstructError("re-classification failed")
    return out
