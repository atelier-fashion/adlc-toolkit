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
