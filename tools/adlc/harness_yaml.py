#!/usr/bin/env python3
"""harness_yaml — the closed YAML subset the harness adapter files use (REQ-657 ADR-1).

The adapter loader runs inside ``adlc doctor`` and every ``adlc harness`` verb, on
a machine that may never have created the delegate venv, and system ``python3``
ships no PyYAML (ASSUME-003). So the adapter files, ``templates/permissions.yml``
and ``templates/hooks.yml`` are read by this parser, which is pure standard
library (LESSON-395).

The subset, and nothing else (a file outside it is a loud :class:`YamlError`
naming the line; LESSON-716 — a reader that skips what it does not understand
fails open):

* block mappings ``key: value`` and block sequences ``- item``, nested by
  indentation (spaces only); a sequence may sit at its parent key's indentation;
* a ``- key: value`` item opens a mapping whose further keys align with the first;
* flow sequences ``[a, "b", [c, d]]`` and flow mappings ``{k: v, k2: [x]}`` on
  one line, holding scalars and nested flow collections;
* scalars: plain, ``'single'`` (``''`` escapes a quote), ``"double"`` (escapes
  ``\\"`` ``\\\\`` ``\\n`` ``\\t`` ``\\/``), integers (``-?[0-9]+`` become ``int``);
  every other plain scalar, ``yes``/``no``/``true``/``false`` included, stays a
  string, and the schema decides what it means;
* ``|`` and ``|-`` literal block scalars;
* ``#`` comments on their own line or after a value (a space before the ``#``).

Refused: tabs, anchors (``&``), aliases (``*``), tags (``!``), ``>`` folding,
directives and document markers, ``?`` complex keys, an empty value with no
nested block, a quoted scalar left open, a plain scalar holding ``: `` or starting
with an indicator, anything after a value but a comment, and a key given twice —
whether spelled the same or differently (``binary:`` and ``"binary":`` are one key
to every reader, so the second is refused rather than silently winning).
"""

import re

__all__ = ["YamlError", "loads", "load_file"]

_INT_RE = re.compile(r"^-?[0-9]+$")
_PLAIN_KEY_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-/]*$")
_BAD_PLAIN_START = set("&*!|>%@`{}[]'\",?#")


class YamlError(ValueError):
    """A file outside the subset. ``line`` is 1-based (0 when not line-bound)."""

    def __init__(self, message, line=0, source="<string>"):
        self.line = line
        self.source = source
        where = "%s:%d" % (source, line) if line else source
        super().__init__("%s: %s" % (where, message))


class _Line(object):
    __slots__ = ("no", "indent", "text", "raw")

    def __init__(self, no, indent, text, raw):
        self.no = no
        self.indent = indent
        self.text = text
        self.raw = raw


def _strip_comment(text):
    """Remove a trailing `` #`` comment outside quotes. Returns the stripped text."""
    quote = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                if quote == "'" and i + 1 < len(text) and text[i + 1] == "'":
                    i += 2
                    continue
                quote = None
            elif ch == "\\" and quote == '"':
                i += 2
                continue
        else:
            if ch in ("'", '"') and (i == 0 or text[i - 1] in " [{,:"):
                quote = ch
            elif ch == "#" and (i == 0 or text[i - 1] == " "):
                return text[:i].rstrip()
        i += 1
    return text.rstrip()


class _Parser(object):
    def __init__(self, text, source):
        self.source = source
        self.raw_lines = text.split("\n")
        self.lines = []
        for no, raw in enumerate(self.raw_lines, start=1):
            if "\t" in raw:
                self.fail("a tab character (indent with spaces only)", no)
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if raw.startswith("%") or stripped in ("---", "...") or stripped.startswith("--- "):
                self.fail("directives and document markers are outside the subset", no)
            indent = len(raw) - len(raw.lstrip(" "))
            self.lines.append(_Line(no, indent, raw[indent:].rstrip(), raw))

    def fail(self, message, line=0):
        raise YamlError(message, line, self.source)

    # ---------------------------------------------------------------- blocks
    def parse(self):
        if not self.lines:
            self.fail("empty document")
        value, i = self.block(0, self.lines[0].indent)
        if i != len(self.lines):
            ln = self.lines[i]
            self.fail("unexpected indentation or content", ln.no)
        return value

    def block(self, i, indent):
        ln = self.lines[i]
        if ln.indent != indent:
            self.fail("unexpected indentation", ln.no)
        if self._is_item(ln.text):
            return self.sequence(i, indent)
        return self.mapping(i, indent)

    @staticmethod
    def _is_item(text):
        return text == "-" or text.startswith("- ")

    def sequence(self, i, indent):
        out = []
        while i < len(self.lines):
            ln = self.lines[i]
            if ln.indent < indent:
                break
            if ln.indent > indent:
                self.fail("unexpected indentation inside a sequence", ln.no)
            if not self._is_item(ln.text):
                break
            rest = ln.text[1:].lstrip(" ")
            if not rest:
                if i + 1 >= len(self.lines) or self.lines[i + 1].indent <= indent:
                    self.fail("empty sequence item", ln.no)
                value, i = self.block(i + 1, self.lines[i + 1].indent)
                out.append(value)
                continue
            col = indent + (len(ln.text) - len(rest))
            if self._looks_like_key(rest):
                # A mapping opened on the item line: its keys align at `col`.
                synthetic = _Line(ln.no, col, rest, ln.raw)
                self.lines[i] = synthetic
                value, i = self.mapping(i, col)
                out.append(value)
                continue
            value, i = self.inline_value(rest, ln, i, indent)
            out.append(value)
        return out, i

    def _looks_like_key(self, text):
        if text[:1] in ("[", "{"):
            return False
        if text[:1] in ("'", '"'):
            end = self._quoted_end(text, 0)
            return end is not None and text[end:end + 1] == ":" and (
                end + 1 == len(text) or text[end + 1] == " ")
        idx = text.find(":")
        while idx != -1:
            if idx + 1 == len(text) or text[idx + 1] == " ":
                key = text[:idx]
                return bool(_PLAIN_KEY_RE.match(key))
            idx = text.find(":", idx + 1)
        return False

    def _quoted_end(self, text, start):
        q = text[start]
        i = start + 1
        while i < len(text):
            if text[i] == q:
                if q == "'" and i + 1 < len(text) and text[i + 1] == "'":
                    i += 2
                    continue
                return i + 1
            if q == '"' and text[i] == "\\":
                i += 2
                continue
            i += 1
        return None

    def split_key(self, ln):
        text = ln.text
        if text[:1] in ("'", '"'):
            end = self._quoted_end(text, 0)
            if end is None:
                self.fail("a quoted key is never closed", ln.no)
            key = self.quoted(text[:end], ln.no)
            rest = text[end:]
            if not rest.startswith(":"):
                self.fail("a quoted key must be followed by ':'", ln.no)
            return key, rest[1:]
        idx = text.find(":")
        while idx != -1 and not (idx + 1 == len(text) or text[idx + 1] == " "):
            idx = text.find(":", idx + 1)
        if idx == -1:
            self.fail("expected 'key: value' (or a '- ' item)", ln.no)
        key = text[:idx]
        if text.startswith("? "):
            self.fail("complex keys are outside the subset", ln.no)
        if not _PLAIN_KEY_RE.match(key):
            self.fail("key %r is not a plain key (quote it)" % key, ln.no)
        return key, text[idx + 1:]

    def mapping(self, i, indent):
        out = {}
        seen = {}
        while i < len(self.lines):
            ln = self.lines[i]
            if ln.indent < indent:
                break
            if ln.indent > indent:
                self.fail("unexpected indentation inside a mapping", ln.no)
            if self._is_item(ln.text):
                break
            key, rest = self.split_key(ln)
            if key in seen:
                self.fail("key %r given twice (first on line %d) — every reader resolves a "
                          "repeated key differently, so it is refused" % (key, seen[key]), ln.no)
            seen[key] = ln.no
            rest = _strip_comment(rest).strip()
            if rest == "":
                nxt = self.lines[i + 1] if i + 1 < len(self.lines) else None
                if nxt is not None and (nxt.indent > indent or (
                        nxt.indent == indent and self._is_item(nxt.text))):
                    value, i = self.block(i + 1, nxt.indent)
                else:
                    self.fail("key %r has no value" % key, ln.no)
            else:
                value, i = self.inline_value(rest, ln, i, indent)
            out[key] = value
        return out, i

    def inline_value(self, rest, ln, i, indent):
        rest = _strip_comment(rest).strip()
        if rest in ("|", "|-"):
            return self.block_scalar(i, indent, chomp=rest)
        if rest[:1] in ("[", "{"):
            value, end = self.flow(rest, 0, ln.no)
            tail = rest[end:].strip()
            if tail:
                self.fail("unexpected text after a flow collection: %r" % tail, ln.no)
            return value, i + 1
        return self.scalar(rest, ln.no), i + 1

    def block_scalar(self, i, indent, chomp):
        ln = self.lines[i]
        start = ln.no  # 1-based line of the indicator; content follows
        raw = self.raw_lines
        j = start  # index into raw_lines of the first content line (0-based == start)
        body = []
        content_indent = None
        while j < len(raw):
            line = raw[j]
            if line.strip() == "":
                body.append("")
                j += 1
                continue
            this_indent = len(line) - len(line.lstrip(" "))
            if this_indent <= indent:
                break
            if content_indent is None:
                content_indent = this_indent
            if this_indent < content_indent:
                self.fail("block scalar line is less indented than its first line", j + 1)
            body.append(line[content_indent:].rstrip("\n"))
            j += 1
        while body and body[-1] == "":
            body.pop()
        if not body:
            self.fail("empty block scalar", ln.no)
        text = "\n".join(body)
        if chomp == "|":
            text += "\n"
        # Skip the parsed logical lines that fall inside the block.
        k = i + 1
        while k < len(self.lines) and self.lines[k].no <= j:
            k += 1
        return text, k

    # ---------------------------------------------------------------- scalars
    def quoted(self, token, lineno):
        q = token[0]
        inner = token[1:-1]
        if q == "'":
            return inner.replace("''", "'")
        out = []
        k = 0
        escapes = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "/": "/"}
        while k < len(inner):
            ch = inner[k]
            if ch == "\\":
                if k + 1 >= len(inner) or inner[k + 1] not in escapes:
                    self.fail("unsupported escape in a double-quoted scalar", lineno)
                out.append(escapes[inner[k + 1]])
                k += 2
                continue
            out.append(ch)
            k += 1
        return "".join(out)

    def scalar(self, text, lineno):
        if text[:1] in ("'", '"'):
            end = self._quoted_end(text, 0)
            if end is None:
                self.fail("a quoted scalar is never closed", lineno)
            if text[end:].strip():
                self.fail("unexpected text after a quoted scalar", lineno)
            return self.quoted(text[:end], lineno)
        if text[:1] in _BAD_PLAIN_START or text.startswith("- ") or text == "-":
            self.fail("plain scalar %r starts with an indicator (anchors, aliases, tags, "
                      "folding and flow are outside the subset; quote it)" % text, lineno)
        if ": " in text or text.endswith(":"):
            self.fail("plain scalar %r holds ': ' (quote it)" % text, lineno)
        if _INT_RE.match(text):
            return int(text)
        return text

    def flow(self, text, pos, lineno):
        opener = text[pos]
        closer = "]" if opener == "[" else "}"
        pos += 1
        items = [] if opener == "[" else {}
        seen = set()
        expect_item = True
        while True:
            while pos < len(text) and text[pos] == " ":
                pos += 1
            if pos >= len(text):
                self.fail("flow collection is never closed on its line", lineno)
            ch = text[pos]
            if ch == closer:
                return items, pos + 1
            if not expect_item:
                if ch != ",":
                    self.fail("expected ',' or %r in a flow collection" % closer, lineno)
                pos += 1
                expect_item = True
                continue
            if opener == "{":
                key, pos = self.flow_scalar(text, pos, lineno, in_map_key=True)
                while pos < len(text) and text[pos] == " ":
                    pos += 1
                if pos >= len(text) or text[pos] != ":":
                    self.fail("expected ':' after a flow mapping key", lineno)
                pos += 1
                if not isinstance(key, str):
                    key = str(key)
                if key in seen:
                    self.fail("key %r given twice in a flow mapping" % key, lineno)
                seen.add(key)
                while pos < len(text) and text[pos] == " ":
                    pos += 1
                value, pos = self.flow_value(text, pos, lineno)
                items[key] = value
            else:
                value, pos = self.flow_value(text, pos, lineno)
                items.append(value)
            expect_item = False

    def flow_value(self, text, pos, lineno):
        if pos < len(text) and text[pos] in ("[", "{"):
            return self.flow(text, pos, lineno)
        return self.flow_scalar(text, pos, lineno)

    def flow_scalar(self, text, pos, lineno, in_map_key=False):
        if pos < len(text) and text[pos] in ("'", '"'):
            end = self._quoted_end(text, pos)
            if end is None:
                self.fail("a quoted scalar is never closed", lineno)
            return self.quoted(text[pos:end], lineno), end
        start = pos
        stops = ",]}" + (":" if in_map_key else "")
        while pos < len(text) and text[pos] not in stops:
            if not in_map_key and text[pos] == ":" and pos + 1 < len(text) and text[pos + 1] == " ":
                self.fail("plain flow scalar holds ': ' (quote it)", lineno)
            pos += 1
        token = text[start:pos].strip()
        if not token:
            self.fail("empty item in a flow collection", lineno)
        if token[:1] in _BAD_PLAIN_START:
            self.fail("flow scalar %r starts with an indicator (quote it)" % token, lineno)
        if _INT_RE.match(token):
            return int(token), pos
        return token, pos


def loads(text, source="<string>"):
    """Parse ``text`` in the subset. Raises :class:`YamlError` on anything else."""
    return _Parser(text, source).parse()


def load_file(path):
    """Parse the file at ``path``; a read error is a :class:`YamlError` too."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise YamlError("cannot read: %s" % (getattr(exc, "strerror", None) or exc), 0, path)
    return loads(text, path)
