"""The one loader for the machine config at ``~/.claude/adlc/config.yml``.

REQ-609 ADR-1. Every consumer of that file — the delegation opt-in in
``_common.parse_delegate_config`` and (REQ-609 TASK-096) the forge section in
``tools/adlc/forge_config.py`` — reads it through :func:`load_machine_config`,
so a multi-section config cannot lock out one consumer by the other's rule and
a file defect gets exactly one verdict (REQ BR-8).

**Why a real parser.** The hand-written flat reader this replaces *skipped*
what it did not understand, and four adversarial passes found nine distinct
fail-opens in it: a comment on the section header discarded the block, a nested
mapping hoisted ``enabled: true`` over a written ``false``, a tab truncated a
block, a second ``delegate:`` block was unreachable. A recognizer does the
opposite of a skipper — anything it cannot make sense of is *malformed*, and
malformed fails closed (REQ-609 Description).

**The contract** (REQ BR-3): :func:`load_machine_config` returns a
:class:`ConfigOutcome` whose ``kind`` is exactly one of ``absent``, ``parsed``,
``malformed``, and it **never raises** — not for a ``yaml.YAMLError``, and not
for the plain ``ValueError``/``KeyError``/``AttributeError`` PyYAML's own
constructors raise straight out of the standard library, which is why the last
arm of the parse is an unbounded ``except Exception``. ``reason`` is a short
class token from :data:`REASON_CLASSES`, a colon, and a human detail that may
carry a line number but never carries a VALUE from the file.

Key NAMES are the exception, and they appear in **two** reasons, not one: the
duplicated key in a ``duplicate-key`` refusal, and the offending key in the
unknown-key ``SchemaError`` that ``_common.parse_delegate_config`` publishes as
a ``schema`` reason. Both are the operator's own key names, and naming them is
what lets the operator fix the file (REQ BR-13); both go through
:func:`_short`, whose ``repr`` escapes control characters so a key lifted out of
the file cannot rewrite the message it lands in.

A recognizer also refuses meaning **borrowed from elsewhere in the document**:
an alias or a ``<<`` merge makes ``delegate.enabled`` true with the word
``enabled`` appearing nowhere under ``delegate:``, and a governance file that
cannot be reviewed by reading it is not reviewable at all (see
:func:`_strict_loader_class`).

**Reading** (REQ BR-4, BR-5): :func:`_open_regular` opens with
``O_RDONLY | O_NONBLOCK`` and decides ``S_ISREG`` on ``fstat`` of the descriptor
it actually opened, so there is no stat-then-open window for a fifo to be
swapped into, and a fifo with no writer does not block. There is no carve-out
for any non-regular file: ``/dev/null`` used to read as ``{}``, which is
*absence*, which fell through to legacy-key continuity — so ``ADLC_CONFIG=/dev/null``
turned delegation on (BUG-205's shape).

**The import is lazy** (REQ BR-1, LESSON-022 / BUG-056): ``import yaml`` happens
inside :func:`load_machine_config`, after the file has been read, mirroring the
``import openai`` inside ``_common.get_client``. ``--help`` and a config-less
``--version`` never pay for it, and a machine without PyYAML fails closed with
one named stderr line rather than through to ``{}`` (REQ BR-9).
"""

import errno
import os
import stat
import sys

# --- constants --------------------------------------------------------------

#: Hard cap on the config read. A file with a handful of scalar fields has no
#: business being larger, and the cap is UNCONDITIONAL because a truncated YAML
#: document can still parse — reading "the first 64 KiB" would let a header
#: inside the cap and an `enabled: false` past it resolve as an opt-in (REQ BR-3).
CONFIG_CAP_BYTES = 65536

#: Bound on the rc-file key fallback's read. Unlike the config cap this one
#: TRUNCATES rather than refusing: a shell rc file is not a governance document
#: (REQ BR-5 mandates only the open pattern for it), and a key export past a
#: quarter-megabyte of rc is not a shape worth failing a real machine over.
RC_CAP_BYTES = 262144

#: The closed schema's allowed keys (REQ BR-7). One constant, pinned to the key
#: list in `tools/delegate/README.md` by a structural test — a closed schema
#: rots unless something ties it to the doc that describes it (LESSON-331).
DELEGATE_KEYS = frozenset({"enabled", "model", "base_url", "api_key_env"})

KIND_ABSENT = "absent"
KIND_PARSED = "parsed"
KIND_MALFORMED = "malformed"

#: Exactly three states, never a fourth (REQ BR-3).
KINDS = (KIND_ABSENT, KIND_PARSED, KIND_MALFORMED)

#: The closed reason vocabulary for `malformed` (REQ-609 architecture ADR-1).
REASON_CLASSES = frozenset({
    "not-regular-file",
    "dangling-symlink",
    "unreadable",
    "undecodable",
    "over-cap",
    "yaml-error",
    "duplicate-key",
    "alias-or-merge",
    "not-a-mapping",
    "dependency-missing",
    # Emitted one layer up, by `_common.parse_delegate_config`, when a document
    # that PARSED says something `validate_delegate_section` does not allow.
    # It belongs in the closed set even though this module never writes it: the
    # vocabulary is what consumers branch on (ADR-2's forge carve-out matches
    # `dependency-missing`), and a token invented outside the set is a token no
    # carve-out can be checked against.
    "schema",
})

_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)

# Reason details are written to stderr and into refusal messages. Cap the one
# operator-supplied fragment they may carry (a duplicated key name) so a
# pathological key cannot flood a message.
_MAX_DETAIL_CHARS = 120


# --- outcome ----------------------------------------------------------------

class ConfigOutcome(object):
    """One of the three states in REQ BR-3.

    ``document`` is the top-level mapping for ``parsed`` — ``{}`` for a null
    document (an empty file, or comments only), which BR-3 makes the same
    outcome as a mapping with no ``delegate`` key. ``reason`` is set only for
    ``malformed``; ``path`` is always the path that was read.
    """

    __slots__ = ("kind", "document", "reason", "path")

    def __init__(self, kind, document=None, reason=None, path=None):
        self.kind = kind
        self.document = document
        self.reason = reason
        self.path = path

    @property
    def reason_class(self):
        """The short class token of :attr:`reason`, or ``None``.

        The reason is ``"<class>: <detail>"``. Consumers that branch on the
        cause — ADR-2's forge carve-out for ``dependency-missing`` — match on
        this, never on the human detail.
        """
        if not self.reason:
            return None
        return self.reason.split(":", 1)[0]

    def __repr__(self):
        return "ConfigOutcome(kind=%r, reason=%r, path=%r)" % (
            self.kind, self.reason, self.path)


# --- errors -----------------------------------------------------------------

class NotRegularFileError(OSError):
    """The descriptor that was opened is not a regular file (REQ BR-4/BR-5)."""


class OverCapError(Exception):
    """The file is larger than the cap (REQ BR-3)."""


class SchemaError(Exception):
    """The ``delegate`` section violates the closed schema (REQ BR-7)."""


class DuplicateKey(Exception):
    """Marker base for the loader's duplicate-key refusal (REQ BR-2).

    Defined here, without yaml, so callers can catch it before
    ``yaml.YAMLError`` without importing PyYAML themselves. The concrete class
    raised by the loader also derives from ``yaml.constructor.ConstructorError``
    and is built lazily, when yaml is first imported.
    """


class AliasOrMerge(Exception):
    """Marker base for the loader's alias / merge-key refusal (REQ BR-2, BR-7).

    Same construction as :class:`DuplicateKey`, and for the same reason: the
    concrete class also derives from ``yaml.constructor.ConstructorError`` and
    is built lazily, so a caller can catch this specific case ahead of the
    general ``yaml.YAMLError`` without importing PyYAML.
    """


# --- paths ------------------------------------------------------------------

def default_config_path():
    """``$ADLC_CONFIG`` or ``~/.claude/adlc/config.yml``.

    The single spelling of the machine-config location; ``_common._config_path``
    defers to it so the delegate and forge consumers cannot drift apart about
    which file they are reading (REQ BR-8).
    """
    override = os.environ.get("ADLC_CONFIG")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "adlc", "config.yml")


# --- reading ----------------------------------------------------------------

def _open_regular(path):
    """Open ``path`` read-only and non-blocking; return a binary file object.

    REQ BR-5. The kind is decided by ``fstat`` on the descriptor that was
    actually opened, not by a ``stat`` of the name beforehand: a stat-then-open
    pair leaves a window a fifo can be swapped into, and the answer would then
    describe a file that is no longer there. ``O_NONBLOCK`` is what makes
    opening a writer-less fifo return immediately instead of hanging forever —
    a ``--version`` that never returns was the observed symptom.

    ``os.open`` on a *directory* succeeds on macOS and Linux; the ``S_ISREG``
    check is what rejects it. Raises :class:`NotRegularFileError` for anything
    that is not a regular file, and the usual ``OSError``/``ValueError`` for a
    path that cannot be opened at all.
    """
    fd = os.open(path, os.O_RDONLY | _O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise NotRegularFileError(errno.EINVAL, "not a regular file", path)
        fh = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    return fh


def _read_capped(fh, cap=CONFIG_CAP_BYTES):
    """Read at most ``cap`` bytes; raise :class:`OverCapError` if there is more.

    Reads ``cap + 1`` so "exactly at the cap" and "over the cap" are
    distinguishable without a second syscall or a trusted ``st_size``.
    """
    data = fh.read(cap + 1)
    if len(data) > cap:
        raise OverCapError("larger than %d bytes" % cap)
    return data


def _decode(data):
    """Strict UTF-8 decode, with one leading BOM stripped.

    Strict on purpose: ``errors="replace"`` turned an undecodable byte inside a
    key into U+FFFD, so ``enabl\\xe9d: false`` stopped matching ``enabled`` and
    the block silently lost the operator's opt-out. A byte we cannot read is a
    file we cannot read.
    """
    text = data.decode("utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


# --- the strict loader ------------------------------------------------------

_loader_cache = []


def _strict_loader_class(yaml):
    """Build (once) the ``yaml.SafeLoader`` subclass this module parses with.

    Two refusals, both whole-document, both because a governance file has to
    mean what it visibly says.

    **Repeated keys** (REQ BR-2). PyYAML's default construction takes the LAST
    of a repeated key. For a governance file that is a silent override: a second
    ``delegate:`` block, or a second ``enabled:`` under one, quietly outranks
    the first, and nothing in the file says so. A duplicate under ``forge:``
    makes the delegate section malformed too, because one loader gives one
    verdict.

    **Aliases and merge keys** (REQ BR-2, BR-7). An alias puts a key's *value*
    somewhere the key is not::

        defaults: &d
          enabled: true
        delegate:
          <<: *d

    Under stock PyYAML that document opts delegation IN, with the word
    ``enabled`` appearing nowhere under ``delegate:``. An operator reading their
    own file sees a section that says nothing, and so does the reviewer reading
    it over their shoulder — the file's meaning has been assembled from another
    part of the document. The same trick works one level up (``delegate: *x``)
    and on any single field. So both constructs are refused rather than
    resolved: :meth:`_StrictLoader.compose_node` rejects an alias node, and
    :meth:`_StrictLoader.flatten_mapping` rejects a ``<<`` key — two arms
    because a merge written with an inline mapping carries no alias, and an
    alias can appear with no merge.

    An *anchor* on its own is untouched: nothing is borrowed from elsewhere, so
    the file still says what it means.

    Built lazily because ``yaml`` itself is imported lazily; cached because the
    class only needs to exist once per process.
    """
    if _loader_cache:
        return _loader_cache[0]

    class _DuplicateKeyError(DuplicateKey, yaml.constructor.ConstructorError):
        """A repeated mapping key. Both a DuplicateKey and a YAMLError, so
        callers can catch the specific case ahead of the general one."""

    class _AliasOrMergeError(AliasOrMerge, yaml.constructor.ConstructorError):
        """An alias reference or a merge key. Both an AliasOrMerge and a
        YAMLError, for the same reason as the duplicate above."""

    #: The tag PyYAML's resolver gives a plain ``<<`` in key position.
    merge_tag = "tag:yaml.org,2002:merge"

    class _StrictLoader(yaml.SafeLoader):
        """SafeLoader plus three overrides. Derived from ``yaml.SafeLoader``, so
        no non-safe constructor is reachable from it (REQ BR-1)."""

        duplicate_key_error = _DuplicateKeyError
        alias_or_merge_error = _AliasOrMergeError

        def compose_node(self, parent, index):
            """Refuse an alias before it is resolved.

            The check is on the EVENT, ahead of the base implementation's
            ``self.anchors[event.anchor]`` lookup, so an alias to a missing
            anchor refuses here as an alias rather than as PyYAML's own
            composer error — the two are the same defect for an operator, and
            one message is easier to act on than two.
            """
            if self.check_event(yaml.AliasEvent):
                event = self.peek_event()
                raise _AliasOrMergeError(
                    "while composing a node", None,
                    "found an alias reference, which this file may not use",
                    event.start_mark)
            return yaml.SafeLoader.compose_node(self, parent, index)

        def flatten_mapping(self, node):
            """Refuse a ``<<`` key instead of merging what it points at.

            Reached for every mapping in the document, because
            ``construct_mapping`` below calls it on each. A merge whose value is
            an inline mapping never goes near an alias, so this arm is not
            redundant with :meth:`compose_node`.

            Delegating to the base implementation afterwards is deliberate: with
            no merge key left it does nothing but the ``=`` value-key rewrite,
            and dropping that would be a second behaviour change hidden inside
            this one.
            """
            for key_node, _value_node in node.value:
                if getattr(key_node, "tag", None) == merge_tag:
                    raise _AliasOrMergeError(
                        "while constructing a mapping", node.start_mark,
                        "found a merge key ('<<'), which this file may not use",
                        key_node.start_mark)
            return yaml.SafeLoader.flatten_mapping(self, node)

        def construct_mapping(self, node, deep=False):
            self.flatten_mapping(node)
            mapping = {}
            seen = set()
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=True)
                try:
                    repeated = key in seen
                except TypeError:
                    # An unhashable key (a list, a mapping) is not something
                    # this file may contain; SafeConstructor refuses it too.
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark,
                        "found unhashable key", key_node.start_mark)
                if repeated:
                    # The SECOND occurrence's mark: that is the line the
                    # operator has to delete (REQ BR-13).
                    raise _DuplicateKeyError(
                        "while constructing a mapping", node.start_mark,
                        "found duplicate key %s" % _short(key),
                        key_node.start_mark)
                seen.add(key)
                mapping[key] = self.construct_object(value_node, deep=deep)
            return mapping

    _loader_cache.append(_StrictLoader)
    return _StrictLoader


def _parse_strict(yaml, text):
    """Parse ``text`` through :func:`_strict_loader_class`.

    This is exactly what ``yaml.safe_load`` does — ``load(stream, SafeLoader)``,
    which is ``Loader(stream).get_single_data()`` under a ``dispose()`` —
    with the overrides BR-2 requires. ``safe_load`` itself takes no loader
    parameter, so the same machinery is driven directly rather than through
    ``yaml.load``, which is never called here with any loader (REQ BR-1; a
    structural test pins the SafeLoader ancestry).

    Unbounded alias expansion — the "billion laughs" shape, where a document
    inside the 64 KiB cap expands to far more than that in memory — was recorded
    here as known and accepted, on the grounds that bounding expansion means a
    different parser. It is no longer reachable: the loader refuses aliases
    outright (see :func:`_strict_loader_class`), for a governance reason rather
    than a resource one, and a document with no aliases has nothing to expand.
    Should that refusal ever be relaxed, this becomes a live consideration
    again, which is why the shape is still named here.
    """
    loader = _strict_loader_class(yaml)(text)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


# --- reason helpers ---------------------------------------------------------

def _short(value):
    """``repr`` of an operator-supplied fragment, bounded.

    ``repr`` escapes control characters and terminal escapes, so a key name
    lifted out of the file cannot rewrite the message it lands in.
    """
    text = repr(value)
    if len(text) > _MAX_DETAIL_CHARS:
        text = text[:_MAX_DETAIL_CHARS] + "..."
    return text


def _malformed(path, reason_class, detail):
    return ConfigOutcome(
        KIND_MALFORMED, None, "%s: %s" % (reason_class, detail), path)


def _yaml_detail(exc):
    """A location, never a quotation.

    ``str(exc)`` on a marked PyYAML error embeds the offending source line, and
    that line is file content — which reason strings do not carry.
    """
    mark = getattr(exc, "problem_mark", None)
    if mark is not None:
        return "not valid YAML (line %d, column %d)" % (
            mark.line + 1, mark.column + 1)
    return "not valid YAML"


def _marked_detail(exc, fallback):
    """``exc``'s own problem text and the line it marks (REQ BR-13).

    The problem strings these carry are written by this module, never lifted
    out of the file — apart from a duplicated key NAME, which is bounded by
    :func:`_short` and is the thing the operator has to go and delete.
    """
    problem = getattr(exc, "problem", None) or fallback
    mark = getattr(exc, "problem_mark", None)
    if mark is not None:
        return "%s at line %d, column %d" % (
            problem, mark.line + 1, mark.column + 1)
    return problem


def _duplicate_detail(exc):
    """The duplicated key and the line of its SECOND occurrence (REQ BR-13)."""
    return _marked_detail(exc, "found a duplicate key")


def _alias_or_merge_detail(exc):
    """The borrowed construct and the line it sits on (REQ BR-13)."""
    return _marked_detail(exc, "found an alias or a merge key")


def _construction_detail(exc):
    """A detail for an exception PyYAML did not promise, naming no content.

    ``str(exc)`` is not usable here: a ``KeyError`` from ``!!bool "maybe"``
    carries the offending VALUE out of the file, and reason strings do not carry
    file content. The exception's TYPE is a fact about the parser, not about the
    operator's data, and it is the one thing that makes a bug report from this
    message actionable.
    """
    return "the document could not be constructed (%s)" % type(exc).__name__


# --- the PyYAML dependency notice ------------------------------------------

_dependency_notice_emitted = False


def dependency_missing_line():
    """The one stderr line for a missing PyYAML (REQ BR-9).

    Names the interpreter, because the failure is per-interpreter: the delegate
    venv pins PyYAML and ``$PATH``'s ``python3`` may not have it (ADR-2).
    """
    return ("adlc: PyYAML is not importable in %s; "
            "run install.sh --with-delegation\n" % sys.executable)


def _emit_dependency_notice(stream=None):
    """Write :func:`dependency_missing_line` once per process.

    Once, not once per read: three surfaces parse the config on a single
    ``--print-gate``, and three identical lines read as three problems.
    """
    global _dependency_notice_emitted
    if _dependency_notice_emitted:
        return False
    _dependency_notice_emitted = True
    (sys.stderr if stream is None else stream).write(dependency_missing_line())
    return True


def _reset_dependency_notice():
    """Test hook: forget that the notice was emitted. Not for production use."""
    global _dependency_notice_emitted
    _dependency_notice_emitted = False


# --- the loader -------------------------------------------------------------

def load_machine_config(path=None):
    """Read and parse the machine config. Returns a :class:`ConfigOutcome`.

    Never raises (REQ BR-3). Every failure is ``malformed`` with a reason class
    from :data:`REASON_CLASSES`; the single ``absent`` case is "the path does
    not exist and is not a dangling symlink", which is a legitimate
    configuration (continuity may apply, REQ BR-6).
    """
    if path is None:
        path = default_config_path()

    try:
        fh = _open_regular(path)
    except NotRegularFileError:
        # No carve-out, not even /dev/null: "absent" is a statement about a
        # path nobody wrote, and a device node is not that (REQ BR-4).
        return _malformed(path, "not-regular-file",
                          "the path is not a regular file")
    except (FileNotFoundError, NotADirectoryError):
        # `lexists`, not `exists`: a symlink pointing at nothing is a config
        # the operator wrote and we cannot read, not a machine without one.
        # Discriminating on errno alone would call it absent (REQ BR-3).
        try:
            present = os.path.lexists(path)
        except (OSError, ValueError):
            present = False
        if present:
            return _malformed(path, "dangling-symlink",
                              "the path is a symlink that resolves to nothing")
        return ConfigOutcome(KIND_ABSENT, None, None, path)
    except OSError:
        # EACCES on the file or its parent, ELOOP, ENAMETOOLONG: a file we were
        # told to read and could not. `os.path.lexists` swallows PermissionError
        # and returns False, which is how an unreadable PARENT directory once
        # read as absence and fell through to legacy-key continuity.
        return _malformed(path, "unreadable", "the file could not be opened")
    except ValueError:
        # An embedded NUL in the path. Not openable, so not readable.
        return _malformed(path, "unreadable", "the path is not a usable filename")

    try:
        try:
            data = _read_capped(fh)
        finally:
            fh.close()
    except OverCapError:
        return _malformed(path, "over-cap",
                          "the file is larger than %d bytes" % CONFIG_CAP_BYTES)
    except OSError:
        return _malformed(path, "unreadable", "the file could not be read")

    try:
        text = _decode(data)
    except UnicodeDecodeError:
        return _malformed(path, "undecodable", "the file is not valid UTF-8")

    # Lazily, and only now: a `--help`, or a `--version` on a machine with no
    # config, must not pay for the import (REQ BR-1, LESSON-022 / BUG-056).
    try:
        import yaml
    except ImportError:
        _emit_dependency_notice()
        return _malformed(path, "dependency-missing",
                          "PyYAML is not installed in this interpreter")

    try:
        document = _parse_strict(yaml, text)
    # The arms below are ordered narrowest-first, and the order is load-bearing:
    # both refusals this module raises are ALSO `yaml.YAMLError`s, so a
    # `YAMLError` arm ahead of them would collapse `duplicate-key` and
    # `alias-or-merge` into the generic class and take BR-13's key name and line
    # with them.
    except DuplicateKey as exc:
        return _malformed(path, "duplicate-key", _duplicate_detail(exc))
    except AliasOrMerge as exc:
        return _malformed(path, "alias-or-merge", _alias_or_merge_detail(exc))
    except yaml.YAMLError as exc:
        return _malformed(path, "yaml-error", _yaml_detail(exc))
    except RecursionError:
        # A deeply nested document exhausts the stack inside the composer.
        # RecursionError is not a YAMLError, and "never raises" has no
        # exceptions (REQ BR-3).
        return _malformed(path, "yaml-error", "nested too deeply to parse")
    except Exception as exc:
        # And the rest of "no exceptions". `yaml.YAMLError` is the boundary
        # PyYAML documents, not the one it keeps: its constructors call into the
        # standard library and let what comes back through, so `2026-09-31` is a
        # `ValueError` from `datetime`, `!!bool "maybe"` a `KeyError` off a
        # lookup table, `!!timestamp "nope"` an `AttributeError` on a failed
        # regex match, and an expansion the machine cannot hold a `MemoryError`.
        # None of those is a YAMLError, and every one of them used to leave this
        # function as a traceback — where the contract promises one of three
        # kinds and the gate above promises a refusal.
        #
        # Deliberately last, and deliberately unbounded: a list of the built-ins
        # PyYAML happens to raise today is the same enumeration that let these
        # five through in the first place. `BaseException` is NOT caught —
        # a Ctrl-C or a SystemExit is the caller's, not the file's.
        return _malformed(path, "yaml-error", _construction_detail(exc))

    if document is None:
        # A null document — an empty file, or comments only. Parsed, with no
        # sections: the same outcome as a mapping without a `delegate` key
        # (REQ BR-3/BR-6). An operator who created the file and wrote nothing
        # has not opted out, and refusing a file that says nothing would lock
        # out that machine's continuity for no written reason.
        document = {}
    if not isinstance(document, dict):
        # A list or a bare scalar at the top level. Nothing can be read from it.
        return _malformed(path, "not-a-mapping",
                          "the top level of the document is not a mapping")
    return ConfigOutcome(KIND_PARSED, document, None, path)


# --- the schema -------------------------------------------------------------

def _type_name(value):
    """A human name for a YAML value's type, for schema messages."""
    if value is None:
        return "a null"
    return {
        bool: "a boolean",
        int: "a number",
        float: "a number",
        str: "a string",
        dict: "a mapping",
        list: "a sequence",
    }.get(type(value), type(value).__name__)


def validate_delegate_section(document):
    """Validate ``document['delegate']`` against the closed schema (REQ BR-7).

    Returns the section as a plain dict — ``{}`` when the document has no
    ``delegate`` key, which means *unconfigured*, not opted out (REQ BR-6): a
    shared config carrying only a ``forge:`` section must not lock delegation
    out. Raises :class:`SchemaError` for anything the System Model does not
    allow.

    Unknown keys refuse deliberately (LESSON-483). ``enbaled: false`` silently
    ignored costs an exfiltration; forward compatibility is a versioning
    problem, not a reason to accept keys nobody validates.

    ``enabled`` must be a YAML boolean. ``bool`` is checked, never ``int``, so a
    ``1`` is refused; a quoted ``"false"`` is the STRING ``"false"``, which
    Python treats as true, and it is refused as ambiguous rather than
    lowercased into an opt-out the operator never wrote. PyYAML's 1.1 booleans
    (``yes``/``no``/``on``/``off``) arrive as real bools and are accepted — the
    schema refuses strings, so the Norway problem cannot reach an opt-in.
    """
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise SchemaError("the top level of the config is not a mapping")
    if "delegate" not in document:
        return {}
    section = document["delegate"]
    if not isinstance(section, dict):
        raise SchemaError(
            "the 'delegate' section must be a mapping, not %s"
            % _type_name(section))
    allowed = ", ".join(sorted(DELEGATE_KEYS))
    out = {}
    for key in section:
        if not isinstance(key, str) or key not in DELEGATE_KEYS:
            raise SchemaError(
                "unknown key %s under 'delegate' — allowed keys are %s"
                % (_short(key), allowed))
        value = section[key]
        if key == "enabled":
            if not isinstance(value, bool):
                raise SchemaError(
                    "'delegate.enabled' must be a YAML boolean (true or "
                    "false), not %s" % _type_name(value))
        elif not isinstance(value, str):
            # Catches a nested mapping and a sequence as well as a number:
            # the three remaining fields are scalars, and a mapping under one
            # of them is how `enabled: true` was once hoisted over a written
            # `false`.
            raise SchemaError(
                "'delegate.%s' must be a string, not %s"
                % (key, _type_name(value)))
        out[key] = value
    return out
