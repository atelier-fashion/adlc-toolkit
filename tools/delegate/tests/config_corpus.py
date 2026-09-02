"""The seeded config corpus — one entry per shape REQ-609 AC-1 enumerates.

Every shape here is one a reviewer found, or a class a reviewer found: REQ-603's
pass-3 and pass-4 reviewers broke the hand-written flat reader with a comment on
the section header, a nested mapping, a tab, a second ``delegate:`` block, a
quoted ``"false"``, a byte past a size cap. The list is kept as *data* so the
tests over it are a specification rather than a transcript, and so the
differential oracle (TASK-095) and the shell-side tests can walk the same shapes
the Python tests do without re-typing them.

Each :class:`Entry` states what the System Model says the outcome must be:

``kind``       the ``ConfigOutcome.kind`` from ``load_machine_config``
``reason``     the expected reason CLASS for ``malformed``, else ``None``
``section``    the dict ``_common.parse_delegate_config`` must return, or
               ``None`` when the adapter must report the config malformed —
               either because the loader did, or because the strict schema
               refused a document that parsed

``data`` is the file's bytes for the shapes that are files; the shapes that are
not files (a directory, a fifo, ``/dev/null``, a dangling symlink, an unreadable
parent, a NUL in the path) carry ``data=None`` and build themselves through
``make``. ``needs`` names a platform capability the entry requires, so a runner
can skip rather than fail where the capability is missing.
"""

import os
import random

# --- entry ------------------------------------------------------------------


class Entry(object):
    """One corpus shape and the outcome the System Model specifies for it."""

    __slots__ = ("name", "kind", "reason", "section", "data", "note",
                 "needs", "_make", "_cleanup")

    def __init__(self, name, kind, reason=None, section=None, data=None,
                 note="", needs=None, make=None, cleanup=None):
        self.name = name
        self.kind = kind
        self.reason = reason
        self.section = section
        self.data = data
        self.note = note
        self.needs = needs
        self._make = make
        self._cleanup = cleanup

    @property
    def adapter_malformed(self):
        """True when ``parse_delegate_config`` must report ``_MALFORMED``.

        Either the loader refused the file, or it parsed and the strict schema
        refused the section. Both are refusals; the operator sees which one
        from the reason.
        """
        return self.kind == "malformed" or self.section is None

    def make(self, tmpdir):
        """Materialise the shape under ``tmpdir``; return the config path."""
        if self._make is not None:
            return self._make(str(tmpdir))
        path = os.path.join(str(tmpdir), "config.yml")
        with open(path, "wb") as fh:
            fh.write(self.data)
        return path

    def cleanup(self, tmpdir):
        """Undo anything that would defeat the runner's own teardown."""
        if self._cleanup is not None:
            self._cleanup(str(tmpdir))

    def __repr__(self):
        return "Entry(%r, %r)" % (self.name, self.kind)


# --- makers for the shapes that are not plain files -------------------------

def _make_dir(tmpdir):
    path = os.path.join(tmpdir, "config.yml")
    if not os.path.isdir(path):
        os.mkdir(path)
    return path


def _make_fifo(tmpdir):
    path = os.path.join(tmpdir, "fifo.yml")
    if not os.path.exists(path):
        os.mkfifo(path)
    return path


def _make_dev_null(tmpdir):
    return "/dev/null"


def _make_dangling(tmpdir):
    path = os.path.join(tmpdir, "dangling.yml")
    if not os.path.lexists(path):
        os.symlink(os.path.join(tmpdir, "no-such-target.yml"), path)
    return path


def _make_locked_parent(tmpdir):
    parent = os.path.join(tmpdir, "locked")
    if not os.path.isdir(parent):
        os.mkdir(parent)
    os.chmod(parent, 0o755)
    path = os.path.join(parent, "config.yml")
    with open(path, "wb") as fh:
        fh.write(b"delegate:\n  enabled: false\n")
    os.chmod(parent, 0o000)
    return path


def _unlock_parent(tmpdir):
    parent = os.path.join(tmpdir, "locked")
    if os.path.isdir(parent):
        os.chmod(parent, 0o755)


def _make_nul_path(tmpdir):
    return os.path.join(tmpdir, "con\x00fig.yml")


def _make_absent(tmpdir):
    return os.path.join(tmpdir, "no-config-here.yml")


# --- the over-cap shapes ----------------------------------------------------

_PAD = b"# pad pad pad pad pad pad pad pad pad pad pad pad pad pad pad\n"
_OVER = (65536 // len(_PAD)) + 2

#: The whole block is inside the file, but the file is over the cap. The cap is
#: unconditional because a truncated YAML document can still parse.
_OVER_CAP_BLOCK = b"delegate:\n  enabled: false\n" + _PAD * _OVER

#: The header is inside the first 64 KiB and the operator's `enabled: false` is
#: past it. A bounded read that PARSED what it got would see the header, miss
#: the opt-out, and resolve the file as unconfigured — continuity then grants.
_HEADER_IN_CAP_FALSE_PAST_IT = b"delegate:\n" + _PAD * _OVER + b"  enabled: false\n"


def _sep_entry(name, sep, kind, reason=None, section=None):
    """A shape where a non-newline separator `str.splitlines` honours splits
    two keys. The old reader split on `splitlines`, so what it called "a line"
    and what YAML calls one were different questions with different answers."""
    data = ("delegate:\n  enabled: false" + sep + "  model: x\n").encode("utf-8")
    return Entry(name, kind, reason=reason, section=section, data=data)


# --- the corpus -------------------------------------------------------------

CORPUS = [
    # -- shapes that PARSE, and must not lose the operator's `false` ---------
    Entry("well-formed-opt-out", "parsed", section={"enabled": False},
          data=b"delegate:\n  enabled: false\n"),
    Entry("well-formed-opt-in", "parsed",
          section={"enabled": True, "model": "m", "base_url": "https://h/v1",
                   "api_key_env": "MY_PROVIDER_KEY"},
          data=b'delegate:\n  enabled: true\n  model: "m"\n'
               b'  base_url: "https://h/v1"\n  api_key_env: "MY_PROVIDER_KEY"\n'),
    Entry("header-comment", "parsed", section={"enabled": False},
          data=b"delegate:  # settings\n  enabled: false\n",
          note="a comment on the header discarded the whole block for the "
               "flat reader, which then granted through continuity"),
    Entry("bom", "parsed", section={"enabled": False},
          data=b"\xef\xbb\xbfdelegate:\n  enabled: false\n",
          note="a BOM made the first key `\ufeffdelegate`, which matched nothing"),
    Entry("double-bom", "parsed", section={"enabled": False},
          data=b"\xef\xbb\xbf\xef\xbb\xbfdelegate:\n  enabled: false\n",
          note="PyYAML skips ONE leading BOM of its own accord; a file that "
               "passed through two tools that each add one keeps a second, "
               "which makes the first key `\ufeffdelegate` — the section then "
               "reads as ABSENT, and absence grants through continuity"),
    Entry("quoted-key", "parsed", section={"enabled": False},
          data=b'"delegate":\n  enabled: false\n',
          note="a quoted key is the same key; the flat reader compared text"),
    Entry("block-scalar-containing-enabled", "parsed",
          section={"model": "enabled: true\n", "enabled": False},
          data=b"delegate:\n  model: |\n    enabled: true\n  enabled: false\n",
          note="`enabled: true` inside a block scalar is a STRING, and must "
               "not become an opt-in"),
    Entry("crlf-endings", "parsed", section={"enabled": False},
          data=b"delegate:\r\n  enabled: false\r\n"),
    Entry("yaml-1-1-boolean-yes", "parsed", section={"enabled": True},
          data=b"delegate:\n  enabled: yes\n",
          note="PyYAML 1.1 booleans are real bools; accepted for this one "
               "field per the REQ's assumption"),
    Entry("empty-file", "parsed", section={},
          data=b"",
          note="a null document is PARSED with no sections (BR-3): whoever "
               "can truncate the file to empty can also write `enabled: true`"),
    Entry("comments-only", "parsed", section={},
          data=b"# nothing written here yet\n#\n"),
    Entry("forge-section-only", "parsed", section={},
          data=b"forge:\n  provider: github\n",
          note="BR-6: a section that is ABSENT is unconfigured, not locked out"),

    # -- shapes that parse but the strict schema refuses (BR-7) --------------
    Entry("nested-mapping-hoists-enabled", "parsed", section=None,
          data=b"delegate:\n  nested:\n    enabled: true\n  enabled: false\n",
          note="the flat reader hoisted the nested `true` over the written "
               "`false`; the schema refuses the unknown key outright"),
    Entry("enabled-quoted-false", "parsed", section=None,
          data=b'delegate:\n  enabled: "false"\n',
          note="the YAML STRING 'false', which Python treats as true; refused "
               "as ambiguous rather than lowercased into an opt-out"),
    Entry("enabled-typo-ture", "parsed", section=None,
          data=b"delegate:\n  enabled: ture\n"),
    Entry("unknown-key-typo", "parsed", section=None,
          data=b"delegate:\n  enbaled: false\n",
          note="LESSON-483: `enbaled: false` silently ignored costs an "
               "exfiltration, so an unknown key refuses"),
    Entry("bare-delegate-header", "parsed", section=None,
          data=b"delegate:\n",
          note="a section that is PRESENT must be a mapping (BR-7); a null "
               "section is a half-written file, and is refused by name"),
    Entry("unknown-key-with-a-string-value", "parsed", section=None,
          data=b'delegate:\n  enabled: false\n  note: "a reminder"\n',
          note="the unknown-key arm carries this one alone: an unknown key "
               "holding a MAPPING or a number is also caught by the per-field "
               "type checks, so only a string-valued one proves the arm works"),
    Entry("bom-inside-the-block", "parsed", section=None,
          data=b"delegate:\n\xef\xbb\xbf  enabled: false\n",
          note="a BOM below the header ends the block and makes `delegate` "
               "null, which the schema refuses rather than reading as absent"),
    Entry("enabled-is-a-number", "parsed", section=None,
          data=b"delegate:\n  enabled: 1\n",
          note="bool is a subclass of int; the check is `isinstance(v, bool)` "
               "so a 1 is refused"),
    Entry("model-is-a-mapping", "parsed", section=None,
          data=b"delegate:\n  model:\n    name: m\n"),
    Entry("model-is-a-sequence", "parsed", section=None,
          data=b"delegate:\n  model:\n    - m\n"),

    # -- duplicate keys (BR-2) ----------------------------------------------
    Entry("duplicate-delegate-block", "malformed", reason="duplicate-key",
          data=b"delegate:\n  enabled: false\ndelegate:\n  enabled: true\n",
          note="the second block was unreachable for the flat reader, so the "
               "operator's first `false` was silently overridden"),
    Entry("duplicate-enabled-key", "malformed", reason="duplicate-key",
          data=b"delegate:\n  enabled: false\n  enabled: true\n"),
    Entry("duplicate-under-forge", "malformed", reason="duplicate-key",
          data=b"forge:\n  provider: github\n  provider: azure\n"
               b"delegate:\n  enabled: false\n",
          note="whole-document by design (BR-2): one loader, one verdict"),

    # -- aliases and merge keys (BR-2, BR-7) --------------------------------
    #
    # An alias is the one construct that puts a key's VALUE somewhere the key
    # is not. `enabled` can then be true for the delegate section without the
    # word appearing anywhere under `delegate:` — an operator reading the file,
    # and every reviewer who has read this one, would see no opt-in. The loader
    # refuses aliases and merge keys document-wide rather than resolving them.
    Entry("merge-only", "malformed", reason="alias-or-merge",
          data=b"defaults: &d\n  enabled: true\ndelegate:\n  <<: *d\n",
          note="the section says only `<<: *d`; resolving it grants, and "
               "nothing under `delegate:` says `enabled` at all"),
    Entry("whole-section-alias", "malformed", reason="alias-or-merge",
          data=b"base: &x\n  enabled: true\ndelegate: *x\n",
          note="the same smuggle one level up: the whole section is an alias"),
    Entry("anchor-with-alias", "malformed", reason="alias-or-merge",
          data=b'delegate:\n  model: &m "m"\n  base_url: *m\n',
          note="an alias inside the section, on a field that is not `enabled`: "
               "the refusal is about the construct, not about which key it "
               "happens to reach"),
    Entry("merge-plus-explicit", "malformed", reason="alias-or-merge",
          data=b"defaults: &d\n  enabled: true\n"
               b"delegate:\n  <<: *d\n  enabled: false\n",
          note="merge-BEFORE-scan used to report this as `duplicate-key`, "
               "which is a lie about the file: `<<` and `enabled` are two "
               "different keys and the operator wrote each of them once"),
    Entry("anchor-without-alias", "parsed", section={"enabled": False},
          data=b"delegate: &d\n  enabled: false\n",
          note="the working subject (LESSON-602): an anchor NOBODY references "
               "is not an alias, and must still parse — otherwise the four "
               "rows above pass against a loader that refuses everything"),

    # -- constructors that raise plain built-ins, not YAMLError (BR-3) ------
    #
    # `load_machine_config` never raises. PyYAML's own constructors do not
    # honour that boundary: they raise `ValueError`, `KeyError`, and
    # `AttributeError` straight out of the standard library, none of which is a
    # `yaml.YAMLError`. A caller that catches only YAMLError gets a traceback
    # where the contract promises a verdict.
    Entry("bad-timestamp", "malformed", reason="yaml-error",
          data=b"delegate:\n  enabled: false\nupdated: 2026-09-31\n",
          note="September has 30 days; `datetime.date` raises ValueError from "
               "inside the timestamp constructor, and the operator's written "
               "`false` never gets a verdict at all"),
    Entry("explicit-tag-bool-maybe", "malformed", reason="yaml-error",
          data=b'delegate:\n  enabled: !!bool "maybe"\n',
          note="`construct_yaml_bool` indexes a dict of the spellings it "
               "knows; an unknown one is a bare KeyError"),
    Entry("explicit-tag-int", "malformed", reason="yaml-error",
          data=b'delegate:\n  model: !!int "abc"\n',
          note="`int('abc')` — a ValueError from the standard library"),

    # -- YAML that does not parse -------------------------------------------
    Entry("tab-indented-header", "malformed", reason="yaml-error",
          data=b"\tdelegate:\n\t  enabled: false\n"),
    Entry("tab-inside-space-block", "malformed", reason="yaml-error",
          data=b"delegate:\n  enabled: false\n\tmodel: x\n",
          note="a tab truncated the block for the flat reader; YAML refuses it"),
    Entry("multiple-documents", "malformed", reason="yaml-error",
          data=b"delegate:\n  enabled: false\n---\ndelegate:\n  enabled: true\n"),
    Entry("list-at-top-level", "malformed", reason="not-a-mapping",
          data=b"- delegate\n- enabled\n"),
    Entry("scalar-at-top-level", "malformed", reason="not-a-mapping",
          data=b"just a string\n"),

    # -- separators `str.splitlines` honours that YAML does not -------------
    _sep_entry("separator-vertical-tab", "\x0b", "malformed", reason="yaml-error"),
    _sep_entry("separator-form-feed", "\x0c", "malformed", reason="yaml-error"),
    _sep_entry("separator-file-sep", "\x1c", "malformed", reason="yaml-error"),
    _sep_entry("separator-group-sep", "\x1d", "malformed", reason="yaml-error"),
    _sep_entry("separator-record-sep", "\x1e", "malformed", reason="yaml-error"),
    _sep_entry("separator-next-line", "\x85", "parsed",
               section={"enabled": False, "model": "x"}),
    _sep_entry("separator-line-sep", "\u2028", "parsed",
               section={"enabled": False, "model": "x"}),
    _sep_entry("separator-paragraph-sep", "\u2029", "parsed",
               section={"enabled": False, "model": "x"}),
    _sep_entry("separator-carriage-return", "\r", "parsed",
               section={"enabled": False, "model": "x"}),

    # -- bytes and size ------------------------------------------------------
    Entry("undecodable-byte-in-key", "malformed", reason="undecodable",
          data=b"delegate:\n  enabl\xe9d: false\n",
          note="errors='replace' turned the byte into U+FFFD, the key stopped "
               "matching, and the opt-out was lost"),
    Entry("over-cap-block", "malformed", reason="over-cap",
          data=_OVER_CAP_BLOCK),
    Entry("header-in-cap-false-past-it", "malformed", reason="over-cap",
          data=_HEADER_IN_CAP_FALSE_PAST_IT,
          note="the cap is unconditional: a truncated YAML document parses"),

    # -- the path is not a readable regular file (BR-4, BR-5) ---------------
    Entry("directory-at-the-path", "malformed", reason="not-regular-file",
          make=_make_dir),
    Entry("fifo-at-the-path", "malformed", reason="not-regular-file",
          make=_make_fifo, needs="mkfifo"),
    Entry("dev-null", "malformed", reason="not-regular-file",
          make=_make_dev_null, needs="dev-null",
          note="the /dev/null carve-out returned {}, which is absence, which "
               "fell through to continuity: ADLC_CONFIG=/dev/null turned "
               "delegation ON"),
    Entry("dangling-symlink", "malformed", reason="dangling-symlink",
          make=_make_dangling,
          note="ENOENT, but `lexists` is true: a config the operator wrote "
               "and we cannot read is not a machine without one"),
    Entry("unreadable-parent-directory", "malformed", reason="unreadable",
          make=_make_locked_parent, cleanup=_unlock_parent, needs="not-root"),
    Entry("nul-in-the-path", "malformed", reason="unreadable",
          make=_make_nul_path,
          note="os.open raises ValueError, not OSError"),

    # -- the one shape that is legitimately ABSENT (BR-3) --------------------
    Entry("absent-path", "absent", section={},
          make=_make_absent,
          note="the benign path. Fail-closed must not swallow the no-config "
               "case, or every fresh install with a legacy key stops working"),
]

#: Only the shapes whose bytes are a file — what a text-level oracle can load
#: directly with `yaml.safe_load` (TASK-095).
TEXT_CORPUS = [e for e in CORPUS if e.data is not None]

BY_NAME = dict((e.name, e) for e in CORPUS)

assert len(BY_NAME) == len(CORPUS), "corpus entry names must be unique"


# --- the generated corpus (TASK-095, ADR-5) ---------------------------------
#
# The seeded corpus above is a transcript of what two reviewers thought of. It
# is the better half of this file — every entry is a shape that actually broke
# something — but it is still bounded by an imagination, and that boundedness is
# exactly what REQ-609 exists to fix (BR-10). The generated corpus is the other
# half: a full product of the axes those reviewers' findings ran along, so the
# combinations nobody wrote down get tested too. It carries NO expected
# outcomes, because the differential oracle computes them from PyYAML — a
# generated corpus with hand-written expectations would just be a longer
# transcript.

#: Every spelling REQ-609 names for `enabled`, as it appears in the file. The
#: three that are NOT YAML booleans (`"false"`, `1`, `ture`) must each refuse:
#: `"false"` is the string Python calls true, `1` is an int, `ture` is a typo
#: that a reader taking the last thing it recognised would have skipped.
_ENABLED_SPELLINGS = ("true", "false", '"false"', "yes", "no", "on", "off",
                      "1", "ture")

#: none | a comment line above the header | a comment ON the header. The third
#: is the shape that discarded the whole block for the flat reader.
_COMMENT_STYLES = ("none", "leading", "header")

#: Two indentation widths. A reader that pattern-matches a fixed indent reads
#: one of these and not the other.
_INDENT_WIDTHS = (2, 4)

#: `enabled` before or after another key. A reader that stops at its first hit
#: and one that keeps the last hit differ only on this axis.
_KEY_ORDERS = ("enabled-first", "enabled-last")

_LINE_ENDINGS = (("lf", "\n"), ("crlf", "\r\n"))

#: Drawn per document from the seeded rng. `model` is deliberately in this list
#: and is NOT an unknown key: with `model` already written above it, picking it
#: here REPEATS a key, so the generated corpus reaches the duplicate-key arm
#: (BR-2) organically rather than by a hand-written case.
_EXTRA_KEY_NAMES = ("enbaled", "note", "verbose", "timeout_s", "model")

#: Scalar strings only. Anything non-string here would refuse for a reason that
#: has nothing to do with the axis under test.
_MODEL_VALUES = ('"m"', '"provider/model-1"', "plain-model")

_COMMENT_TEXTS = ("# machine config", "# written by install.sh",
                  "# keep the key OUT of this file")


class Generated(object):
    """One generated document: a name and its bytes, and nothing else.

    Exposes the same two attributes a text-level reader uses on :class:`Entry`
    (``name``, ``data``) so the oracle can walk both corpora with one loop, and
    deliberately carries no expected ``kind``/``section``: the expectation comes
    from PyYAML (REQ-609 ADR-5).

    ``data`` is bytes, not str, because the CRLF axis is a byte-level property
    and the tests write corpus entries with ``write_bytes``.
    """

    __slots__ = ("name", "data", "axes")

    def __init__(self, name, data, axes):
        self.name = name
        self.data = data
        self.axes = axes

    def __repr__(self):
        return "Generated(%r)" % (self.name,)


_SPELLING_TAGS = {'"false"': "q-false"}


def _axis_tag(comment, indent, order, spelling, extra, nested, eol_name):
    return "-".join((
        {"none": "c0", "leading": "cl", "header": "ch"}[comment],
        "i%d" % indent,
        "oe" if order == "enabled-first" else "om",
        _SPELLING_TAGS.get(spelling, spelling),
        "x1" if extra else "x0",
        "n1" if nested else "n0",
        eol_name,
    ))


def _build_document(comment, indent, order, spelling, extra, nested, eol, rng):
    """Render one document. Every axis is applied to the SAME base block, so a
    disagreement between two documents is attributable to the axes that differ.
    """
    pad = " " * indent
    lines = []
    if comment == "leading":
        lines.append(rng.choice(_COMMENT_TEXTS))
    header = "delegate:"
    if comment == "header":
        header += "  " + rng.choice(_COMMENT_TEXTS)
    lines.append(header)

    body = [pad + "enabled: " + spelling,
            pad + "model: " + rng.choice(_MODEL_VALUES)]
    if order == "enabled-last":
        body.reverse()
    if extra:
        body.append(pad + rng.choice(_EXTRA_KEY_NAMES) + ': "x"')
    if nested:
        body.append(pad + "nested:")
        body.append(pad * 2 + "enabled: true")
    lines.extend(body)
    return eol.join(lines) + eol


def generated_corpus(seed, n=None):
    """The seeded product of the axes above, as a list of :class:`Generated`.

    Deterministic: the same ``seed`` yields the same documents, in the same
    order, with the same per-document filler (comment text, model value, extra
    key name), so a failure names a document a later run can reproduce. ``n``
    caps the number returned — ``None`` means the whole product, which is what
    the oracle runs over; a cap exists so a caller that wants a smoke-sized
    slice does not have to invent one.

    The rng is used only for filler DRAWS, never to decide which axis
    combinations appear: every combination is always present (subject to ``n``),
    because a sampled product is a corpus whose coverage depends on a seed
    nobody audits.
    """
    rng = random.Random(seed)
    docs = []
    for comment in _COMMENT_STYLES:
        for indent in _INDENT_WIDTHS:
            for order in _KEY_ORDERS:
                for spelling in _ENABLED_SPELLINGS:
                    for extra in (False, True):
                        for nested in (False, True):
                            for eol_name, eol in _LINE_ENDINGS:
                                text = _build_document(
                                    comment, indent, order, spelling, extra,
                                    nested, eol, rng)
                                axes = (comment, indent, order, spelling,
                                        extra, nested, eol_name)
                                docs.append(Generated(
                                    "gen-" + _axis_tag(comment, indent, order,
                                                       spelling, extra, nested,
                                                       eol_name),
                                    text.encode("utf-8"), axes))
    rng.shuffle(docs)
    return docs if n is None else docs[:n]


#: The seed the oracle runs at. Fixed so a failure is reproducible from the test
#: name alone, and named here rather than in the test so the shell-side tests
#: can walk the same documents.
GENERATED_SEED = 609
