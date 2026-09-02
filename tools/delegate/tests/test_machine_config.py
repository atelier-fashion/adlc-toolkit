"""REQ-609 TASK-094 — the one config loader, and the strict schema over it.

The reader this replaces was written under a tests-first, mutation-proven
discipline and still shipped nine fail-opens, six of them introduced by the pass
that hardened it. The discipline proved what its author had thought of; it could
not reach what he had not. So the tests here are built around two things the
author's imagination is not the source of:

  * the SEEDED CORPUS (``config_corpus.py``) — every shape two reviewers found,
    kept as data, asserted on all three surfaces in one parametrised test;
  * PROPERTIES rather than transcripts — "no separator can turn a written
    ``false`` into a grant" holds for separators nobody enumerated.

The differential oracle (TASK-095) is the third leg and lives in its own file:
it computes the expected answer from PyYAML directly, so a disagreement between
our schema and the parser is a finding rather than a test both sides pass.
"""
import os
import re
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _common  # noqa: E402
import _machine_config  # noqa: E402

import _child_env  # noqa: E402
from config_corpus import CORPUS  # noqa: E402

_DELEGATE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REQUIREMENTS = os.path.join(_DELEGATE, "requirements.txt")
_README = os.path.join(_DELEGATE, "README.md")

_VARS = (
    "MOONSHOT_API_KEY", "KIMI_API_KEY", "ADLC_DELEGATE_MODEL",
    "ADLC_DELEGATE_BASE_URL", "ADLC_DELEGATE_API_KEY_ENV",
    "ADLC_DELEGATE_ENABLED", "ADLC_CONFIG", "ADLC_DISABLE_DELEGATE",
    "MY_PROVIDER_KEY",
)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for v in _VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _write(tmp_path, body, name="config.yml"):
    path = tmp_path / name
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(body, encoding="utf-8")
    return str(path)


def _load(tmp_path, body):
    return _machine_config.load_machine_config(_write(tmp_path, body))


def _available(entry):
    """False when the platform cannot build this shape at all."""
    if entry.needs == "mkfifo" and not hasattr(os, "mkfifo"):
        return False
    if entry.needs == "dev-null" and not os.path.exists("/dev/null"):
        return False
    if entry.needs == "not-root" and hasattr(os, "geteuid") and os.geteuid() == 0:
        return False
    return True


def _skip_unless_available(entry):
    if not _available(entry):
        pytest.skip("this shape needs %r, which this platform lacks"
                    % (entry.needs,))


# --- AC-1: the seeded corpus, on all three surfaces -------------------------

@pytest.mark.parametrize("entry", CORPUS, ids=lambda e: e.name)
def test_seeded_corpus_three_surfaces(entry, clean_env, monkeypatch):
    """Every shape REQ-609 AC-1 enumerates, through the loader AND the three
    surfaces that consume it.

    Asserted on all three because the first version of the unreadable-config fix
    reached only the probe: the gate refused while a direct CLI call still
    transmitted. A verdict that is right in one place and wrong in another is
    the defect class this REQ exists to remove.

    The legacy-key continuity arm is LIVE on every row (``MOONSHOT_API_KEY`` is
    set), which is what makes the fail-open shapes visible: a shape that loses
    the operator's written ``false`` does not merely read as unconfigured, it
    reads as a GRANT.
    """
    _skip_unless_available(entry)
    path = entry.make(clean_env)
    try:
        outcome = _machine_config.load_machine_config(path)
        assert outcome.kind == entry.kind, (entry.name, outcome, entry.note)
        assert outcome.kind in _machine_config.KINDS
        if entry.reason is not None:
            assert outcome.reason_class == entry.reason, (entry.name, outcome)
            assert outcome.reason_class in _machine_config.REASON_CLASSES

        monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
        monkeypatch.setenv("MY_PROVIDER_KEY", "sk-resolvable")
        if "\x00" in path:
            # The NUL shape cannot go through the environment at all —
            # `setenv` refuses it — so the path is handed over directly.
            cfg = _common.parse_delegate_config(path)
        else:
            monkeypatch.setenv("ADLC_CONFIG", path)
            cfg = _common.parse_delegate_config()

        if entry.adapter_malformed:
            assert cfg.get(_common._MALFORMED) is True, (entry.name, cfg)
            assert _common.delegation_enabled(cfg) is False
            assert _common.resolve_gate_verdict(cfg) == (
                False, "disabled-via-config")
            with pytest.raises(SystemExit):
                _common.require_delegation_enabled("adlc-read", cfg)
        else:
            assert cfg == entry.section, (entry.name, entry.note)
            # An absent `enabled` defers to continuity, which is live here.
            expected = entry.section.get("enabled", True)
            assert _common.delegation_enabled(cfg) is expected
            assert _common.resolve_gate_verdict(cfg) == (
                expected, "ok" if expected else "disabled-via-config")
            if expected:
                assert _common.require_delegation_enabled("adlc-read", cfg) is None
            else:
                with pytest.raises(SystemExit):
                    _common.require_delegation_enabled("adlc-read", cfg)
    finally:
        entry.cleanup(clean_env)


#: The two classes no corpus FILE can make the LOADER emit.
#: `dependency-missing` is a statement about the interpreter, not the file, and
#: has its own test below. `schema` is emitted one layer up, by
#: `parse_delegate_config` when a document that PARSED says something the closed
#: schema does not allow — so it never appears as an `Entry.reason`, and the
#: test below reaches it through the adapter instead.
_NOT_FROM_A_FILE = frozenset({"dependency-missing"})
_NOT_FROM_THE_LOADER = _NOT_FROM_A_FILE | frozenset({"schema"})


def test_corpus_covers_every_reason_class():
    """The corpus is only a specification if it reaches every refusal class."""
    seen = set(e.reason for e in CORPUS if e.reason)
    expected = _machine_config.REASON_CLASSES - _NOT_FROM_THE_LOADER
    assert seen == expected, sorted(expected.symmetric_difference(seen))


def test_every_reason_the_corpus_emits_is_in_the_closed_set(clean_env):
    """The vocabulary is closed at the surface that PUBLISHES it, not just at
    the loader.

    `REASON_CLASSES` is the closed set, and `reason_class` splits on the first
    colon — but the adapter builds one reason of its own, `"schema: ..."`, from
    a `SchemaError` rather than from a `ConfigOutcome`, and for a while that
    token was not in the set at all. Nothing failed, because nothing checked the
    adapter's half: the loader-level tests only ever saw loader reasons. A
    consumer that branches on the class (ADR-2's forge carve-out matches
    `dependency-missing`) is reading a vocabulary one of its producers never
    joined, and the next token invented that way is the one that silently
    misses a carve-out.

    So this walks the whole corpus through `parse_delegate_config` — the
    function that writes the string an operator and a consumer both read — and
    holds every class it emits to the closed set, both ways: nothing outside it,
    and nothing in it that no file can reach.
    """
    seen = set()
    skipped = set()
    for index, entry in enumerate(CORPUS):
        if not _available(entry):
            # Not a hole in the vocabulary, a hole in the platform: discount it
            # below unless another shape reaches the same class anyway.
            if entry.reason:
                skipped.add(entry.reason)
            continue
        # One directory per shape: several of them build a `config.yml` of a
        # different KIND (a file, a directory, a symlink) under the name they
        # are given, and a shared directory would make the corpus order decide
        # what each entry ends up reading.
        home = clean_env / ("shape-%03d" % index)
        home.mkdir()
        path = entry.make(home)
        try:
            cfg = _common.parse_delegate_config(path)
        finally:
            entry.cleanup(home)
        reason = cfg.get(_common._MALFORMED_REASON)
        if reason is None:
            assert cfg.get(_common._MALFORMED) is not True, (entry.name, cfg)
            continue
        klass = reason.split(":", 1)[0]
        assert klass in _machine_config.REASON_CLASSES, (entry.name, reason)
        seen.add(klass)

    expected = (_machine_config.REASON_CLASSES - _NOT_FROM_A_FILE
                - (skipped - seen))
    assert seen == expected, sorted(expected.symmetric_difference(seen))
    # Named explicitly: this is the class the loader never produces, and the
    # reason this test exists as well as the one above.
    assert "schema" in seen


# --- BR-3: three states, and it never raises --------------------------------

def test_outcome_is_three_state_and_never_raises(clean_env):
    """The contract in one test: for every input, one of three kinds, no
    exception. Includes shapes no corpus entry names — a document that exhausts
    the parser's stack, raw entropy, an embedded NUL byte — because "never
    raises" with an enumerated exception list is not the same claim.
    """
    extras = [
        b"[" * 8000 + b"]" * 8000,          # RecursionError, not a YAMLError
        b"delegate:\n  enabled: \x00false\n",
        b"\x00" * 512,
        b"\xff\xfe\x00\x01binary garbage\x00not: yaml: at all\n\x80\x81\n",
        b"delegate: {enabled: false",       # unterminated flow mapping
        b"*missing-anchor\n",
        b"delegate:\n  enabled: !!python/object/apply:os.system ['id']\n",
        "delegate:\n  model: \u202e\u200b\n".encode("utf-8"),
    ]
    inputs = [e.data for e in CORPUS if e.data is not None] + extras
    for data in inputs:
        outcome = _machine_config.load_machine_config(_write(clean_env, data))
        assert outcome.kind in _machine_config.KINDS, data[:40]
        if outcome.kind == "malformed":
            assert outcome.reason_class in _machine_config.REASON_CLASSES
        # Whatever happened, the adapter above it stays a dict.
        assert isinstance(_common.parse_delegate_config(
            _write(clean_env, data)), dict)


def test_a_yaml_tag_cannot_construct_a_python_object(clean_env):
    """The loader derives from SafeLoader, so a `!!python/...` tag is refused
    rather than executed (REQ BR-1). Named separately from the sweep above
    because this is the reason `safe_load` is the rule in the first place."""
    outcome = _load(clean_env,
                    b"delegate:\n"
                    b"  model: !!python/object/apply:os.system ['echo pwned']\n")
    assert outcome.kind == "malformed"
    assert outcome.reason_class == "yaml-error"


_BUILTIN_RAISERS = [
    ("an out-of-range date", b"delegate:\n  enabled: false\nupdated: 2026-09-31\n",
     "ValueError", "2026"),
    ("an out-of-range time", b"delegate:\n  enabled: false\nx: 2020-01-01 25:00:00\n",
     "ValueError", "25:00"),
    ("an explicit !!bool the constructor does not know",
     b'delegate:\n  enabled: !!bool "maybe"\n', "KeyError", "maybe"),
    ("an explicit !!int over a non-number",
     b'delegate:\n  model: !!int "abc"\n', "ValueError", "abc"),
    ("an explicit !!timestamp over a non-date",
     b'delegate:\n  model: !!timestamp "nope"\n', "AttributeError", "nope"),
]


@pytest.mark.parametrize("label,body,exc_name,fragment", _BUILTIN_RAISERS,
                         ids=[r[0] for r in _BUILTIN_RAISERS])
def test_a_constructor_raising_a_builtin_is_malformed(clean_env, label, body,
                                                      exc_name, fragment):
    """BR-3: "never raises" has no exceptions, including PyYAML's own.

    `yaml.YAMLError` is the boundary PyYAML documents and not the one it keeps.
    Its constructors call into the standard library and let what comes back
    through: `datetime.date(2026, 9, 31)` is a `ValueError`, an unrecognised
    `!!bool` spelling is a `KeyError` off a lookup table, `!!timestamp` over a
    string the regex does not match is an `AttributeError` on `None`. None of
    those is a `YAMLError`, so a loader that catches only `YAMLError` hands the
    caller a traceback where the contract promises one of three kinds — and the
    caller here is a governance gate whose refusal path is the safe one.

    The reason must also stay content-free (the fragment assertion): a
    `KeyError` carries the offending VALUE out of the file, so the detail names
    the exception TYPE and never `str(exc)`.
    """
    outcome = _machine_config.load_machine_config(_write(clean_env, body))
    assert outcome.kind == "malformed", (label, outcome)
    assert outcome.reason_class == "yaml-error", (label, outcome)
    assert exc_name in outcome.reason, (label, outcome.reason)
    assert fragment not in outcome.reason, (label, outcome.reason)


def test_an_expansion_that_exhausts_memory_is_malformed(clean_env, monkeypatch):
    """The other escape route BR-3 has to close.

    PyYAML expands aliases eagerly, so a document inside the 64 KiB cap can ask
    for far more memory than the machine has — and `MemoryError` is neither a
    `YAMLError` nor a `RecursionError`. Injected rather than provoked: a test
    that really allocates until the machine gives up is a test that takes the
    machine down with it, and the arm under test is "an unexpected exception
    from the parse becomes a verdict", not "PyYAML expands aliases".
    """
    def _boom(yaml, text):
        raise MemoryError("expansion")

    monkeypatch.setattr(_machine_config, "_parse_strict", _boom)
    outcome = _machine_config.load_machine_config(
        _write(clean_env, b"delegate:\n  enabled: false\n"))
    assert outcome.kind == "malformed", outcome
    assert outcome.reason_class == "yaml-error", outcome


def test_a_constructor_crash_refuses_end_to_end(clean_env):
    """The same shape through the surfaces an operator actually meets.

    A traceback out of `load_machine_config` is not merely untidy: `--print-gate`
    is the probe every skill fence consults, and a non-zero exit with no verdict
    on stdout is a *different* answer from `0 disabled-via-config` — the fence
    reads it as "the probe is broken", which is not a refusal anyone wrote down.
    So the gate line and the exit code are both asserted, and the direct-call
    backstop is asserted beside them (the first version of the malformed-config
    fix reached only the probe while a direct call still transmitted).
    """
    body = b"delegate:\n  enabled: false\nupdated: 2026-09-31\n"
    path = _write(clean_env, body)

    cfg = _common.parse_delegate_config(path)
    assert cfg.get(_common._MALFORMED) is True, cfg
    with pytest.raises(SystemExit) as exc:
        _common.require_delegation_enabled("adlc-read", cfg)
    message = str(exc.value)
    assert path in message, message
    assert "yaml-error" in message, message

    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(clean_env),
           "ADLC_CONFIG": path, "MOONSHOT_API_KEY": "sk-legacy"}
    gate = _cli(["--print-gate"], _child_env.with_yaml(env))
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert gate.stdout.strip() == "0 disabled-via-config", (
        gate.stdout + gate.stderr)


def test_strict_loader_is_a_safe_loader_subclass():
    """BR-1 structurally: `safe_load` takes no loader parameter, so the loader
    drives the same machinery directly. What makes that equivalent to
    `safe_load` — and not to `load` — is the ancestry, so the ancestry is
    pinned rather than described in a comment."""
    yaml = pytest.importorskip("yaml")
    cls = _machine_config._strict_loader_class(yaml)
    assert issubclass(cls, yaml.SafeLoader)
    # `yaml.load` with a permissive loader appears nowhere in the module.
    with open(os.path.join(_DELEGATE, "_machine_config.py"), encoding="utf-8") as fh:
        source = fh.read()
    assert "yaml.load(" not in source
    assert "yaml.unsafe_load" not in source
    assert "yaml.FullLoader" not in source


def test_null_document_is_parsed_empty(clean_env):
    """BR-3: an empty or comments-only file is PARSED with no sections — the
    same outcome as a mapping without a `delegate` key.

    Not a fail-open: anyone who can truncate this file to empty can also write
    `enabled: true` into it. Refusing a file that says nothing would lock out
    that machine's continuity for no written reason.
    """
    for body in (b"", b"\n\n", b"   \n  \n", b"# nothing yet\n",
                 b"# a\n# b\n\n", b"---\n", b"--- # just a marker\n"):
        outcome = _machine_config.load_machine_config(_write(clean_env, body))
        assert outcome.kind == "parsed", body
        assert outcome.document == {}, body
        assert _machine_config.validate_delegate_section(outcome.document) == {}


def test_non_mapping_top_level_is_malformed(clean_env):
    for body in (b"- delegate\n", b"just a scalar\n", b"42\n", b"true\n",
                 b"[1, 2, 3]\n"):
        outcome = _machine_config.load_machine_config(_write(clean_env, body))
        assert outcome.kind == "malformed", body
        assert outcome.reason_class == "not-a-mapping", body


def test_absent_is_only_a_path_that_is_not_there(clean_env):
    """BR-3: `absent` needs BOTH an ENOENT-class errno AND `lexists` false.

    Discriminating on errno alone called a dangling symlink absent, and absence
    falls through to legacy-key continuity — so a config the operator wrote and
    we could not follow granted delegation.
    """
    missing = _machine_config.load_machine_config(
        str(clean_env / "nothing-here.yml"))
    assert missing.kind == "absent"
    assert missing.reason is None

    dangling = clean_env / "dangling.yml"
    os.symlink(str(clean_env / "no-such-target.yml"), str(dangling))
    outcome = _machine_config.load_machine_config(str(dangling))
    assert outcome.kind == "malformed"
    assert outcome.reason_class == "dangling-symlink"


# --- BR-2: duplicate keys ---------------------------------------------------

@pytest.mark.parametrize("body,key,line", [
    (b"delegate:\n  enabled: false\ndelegate:\n  enabled: true\n", "delegate", 3),
    (b"delegate:\n  enabled: false\n  enabled: true\n", "enabled", 3),
    (b"delegate:\n  model: a\n  enabled: false\n  model: b\n", "model", 4),
    (b"forge:\n  provider: github\n  provider: azure\n"
     b"delegate:\n  enabled: false\n", "provider", 3),
    (b'delegate:\n  enabled: false\n  "enabled": true\n', "enabled", 3),
])
def test_duplicate_key_is_malformed_with_line(clean_env, body, key, line):
    """A repeated key anywhere in the document is malformed, and the refusal
    names the key and the line of its SECOND occurrence (BR-2, BR-13).

    PyYAML's default construction silently takes the LAST duplicate. For a
    governance file that is an override nothing in the file announces — a second
    `delegate:` block was an unreachable fail-open, and a second `enabled:`
    under one block is the same defect one level down. The quoted-key row is
    there because `"enabled"` and `enabled` are the same key to YAML and two
    different strings to a text comparison.

    Whole-document by design: the `forge:` row proves a duplicate in a section
    this consumer does not read still refuses. One loader, one verdict — the
    operator fixes the file instead of guessing which consumer objected.
    """
    outcome = _machine_config.load_machine_config(_write(clean_env, body))
    assert outcome.kind == "malformed"
    assert outcome.reason_class == "duplicate-key"
    assert repr(key) in outcome.reason, outcome.reason
    assert ("line %d" % line) in outcome.reason, outcome.reason


def test_distinct_keys_still_parse(clean_env):
    """The other half: refusing repeats must not refuse a normal document."""
    outcome = _load(clean_env, b"forge:\n  provider: github\n"
                               b"delegate:\n  enabled: true\n  model: m\n"
                               b"agents:\n  classes:\n    fast: haiku\n")
    assert outcome.kind == "parsed"
    assert _machine_config.validate_delegate_section(outcome.document) == {
        "enabled": True, "model": "m"}


def test_a_merge_key_does_not_smuggle_a_duplicate(clean_env):
    """A merge beside an explicit key is refused AS a merge, not as a duplicate.

    Flattening first and scanning after did refuse this document — but it
    refused it by reporting `duplicate-key` on `enabled`, which is a statement
    about the file that is not true: `<<` and `enabled` are two different keys
    and the operator wrote each of them exactly once. BR-13 exists so the
    refusal tells the operator what to delete; a line number pointing at a key
    that is not duplicated sends them to the wrong line.
    """
    outcome = _load(
        clean_env,
        b"defaults: &d\n  enabled: true\n"
        b"delegate:\n  <<: *d\n  enabled: false\n")
    assert outcome.kind == "malformed"
    assert outcome.reason_class == "alias-or-merge"


# --- BR-2 / BR-7: aliases and merge keys are refused document-wide ---------

_ALIAS_SHAPES = [
    ("a merge of an anchored mapping",
     b"defaults: &d\n  enabled: true\ndelegate:\n  <<: *d\n"),
    ("the whole section as an alias",
     b"base: &x\n  enabled: true\ndelegate: *x\n"),
    ("an alias on a scalar field",
     b'delegate:\n  model: &m "m"\n  base_url: *m\n'),
    ("a merge key with an INLINE mapping and no alias at all",
     b"delegate:\n  <<: {enabled: true}\n"),
    ("a merge beside an explicitly written key",
     b"defaults: &d\n  enabled: true\n"
     b"delegate:\n  <<: *d\n  enabled: false\n"),
    ("an alias in a section this consumer does not read",
     b"anchors: &a\n  x: 1\nforge:\n  provider: *a\n"
     b"delegate:\n  enabled: false\n"),
    ("an alias with no anchor to resolve",
     b"delegate:\n  enabled: *nowhere\n"),
]


@pytest.mark.parametrize("label,body", _ALIAS_SHAPES,
                         ids=[r[0] for r in _ALIAS_SHAPES])
def test_an_alias_or_a_merge_key_is_refused(clean_env, label, body):
    """An alias puts a key's VALUE somewhere the key is not.

    That is the whole finding. `delegate:\\n  <<: *d` makes `enabled` true for
    the delegate section with the word `enabled` appearing nowhere under
    `delegate:` — an operator reading their own file, and a reviewer reading it
    over their shoulder, both see a section that opts into nothing. A governance
    file whose meaning is assembled from somewhere else in the document is a
    file nobody can review by reading it, so the loader refuses the construct
    rather than resolving it (REQ BR-2's whole-document posture, BR-7's "the
    section is what it says").

    Two arms, because there are two ways in: `compose_node` refuses an alias
    NODE, and `flatten_mapping` refuses a `<<` KEY — the inline-mapping row
    reaches the second with no alias anywhere in the document, so deleting
    either arm leaves a row red. The undefined-alias row is here because a
    reference to a missing anchor must refuse as an alias, not fall through to
    PyYAML's own composer error.
    """
    outcome = _load(clean_env, body)
    assert outcome.kind == "malformed", (label, outcome)
    assert outcome.reason_class == "alias-or-merge", (label, outcome)
    # BR-13: the operator is told which line to look at.
    assert re.search(r"line \d+", outcome.reason), (label, outcome.reason)


def test_an_alias_cannot_grant_delegation(clean_env, monkeypatch):
    """The security half, on the surface that decides transmission.

    Asserted separately from the loader rows above because "malformed" is only
    the right answer if the three surfaces above it treat it as a refusal: the
    document below resolves, under stock PyYAML, to `delegate.enabled == True`.
    """
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    path = _write(clean_env,
                  b"defaults: &d\n  enabled: true\ndelegate:\n  <<: *d\n")
    # The premise: stock PyYAML really does read this as an opt-in.
    yaml = pytest.importorskip("yaml")
    with open(path, encoding="utf-8") as fh:
        assert yaml.safe_load(fh)["delegate"]["enabled"] is True

    cfg = _common.parse_delegate_config(path)
    assert cfg.get(_common._MALFORMED) is True
    assert _common.delegation_enabled(cfg) is False
    assert _common.resolve_gate_verdict(cfg) == (False, "disabled-via-config")
    with pytest.raises(SystemExit):
        _common.require_delegation_enabled("adlc-read", cfg)


def test_an_anchor_nobody_references_still_parses(clean_env):
    """The working subject (LESSON-602).

    Every assertion above is an exclusion, and an exclusion test passes just as
    well against a loader that refuses every document. An anchor is not an
    alias: nothing is resolved from elsewhere, so nothing is smuggled, and the
    file still means what it says.
    """
    outcome = _load(clean_env, b"delegate: &d\n  enabled: false\n")
    assert outcome.kind == "parsed", outcome
    assert _machine_config.validate_delegate_section(outcome.document) == {
        "enabled": False}

    # And a `<<` that is a VALUE, or a quoted string, is not a merge key.
    quoted = _load(clean_env, b'delegate:\n  model: "<<"\n')
    assert quoted.kind == "parsed", quoted
    assert _machine_config.validate_delegate_section(quoted.document) == {
        "model": "<<"}


# --- BR-4 / BR-5: the file kind is decided on the opened descriptor ---------

def test_non_regular_file_is_malformed(clean_env):
    """No carve-out for any non-regular file (BR-4).

    `/dev/null` used to return `{}` — which is ABSENCE, which falls through to
    legacy-key continuity — so `ADLC_CONFIG=/dev/null` turned delegation ON.
    """
    d = clean_env / "as-a-directory.yml"
    d.mkdir()
    candidates = [str(d)]

    link_to_dir = clean_env / "link-to-dir.yml"
    os.symlink(str(d), str(link_to_dir))
    candidates.append(str(link_to_dir))

    if os.path.exists("/dev/null"):
        candidates.append("/dev/null")
    if hasattr(os, "mkfifo"):
        fifo = clean_env / "as-a-fifo.yml"
        try:
            os.mkfifo(str(fifo))
            candidates.append(str(fifo))
        except (OSError, NotImplementedError):
            pass

    for path in candidates:
        outcome = _machine_config.load_machine_config(path)
        assert outcome.kind == "malformed", path
        assert outcome.reason_class == "not-regular-file", path
        cfg = _common.parse_delegate_config(path)
        assert cfg.get(_common._MALFORMED) is True, path
        # The half that matters: with a legacy key exported, absence would have
        # GRANTED here.
        assert _common.delegation_enabled(cfg) is False, path


def test_kind_is_decided_on_the_opened_descriptor(clean_env, monkeypatch):
    """BR-5 structurally: `os.stat` is never consulted, so there is no
    stat-then-open window a fifo can be swapped into.

    A `stat` of the NAME answers a question about whatever was at that name a
    moment ago. `fstat` of the descriptor answers it about the thing that was
    actually opened, which is the thing that will be read.
    """
    regular = _write(clean_env, b"delegate:\n  enabled: false\n")
    d = clean_env / "d.yml"
    d.mkdir()

    def _forbidden(*a, **kw):
        raise AssertionError("the loader must not stat the path by name")

    monkeypatch.setattr(os, "stat", _forbidden)
    assert _machine_config.load_machine_config(regular).kind == "parsed"
    assert _machine_config.load_machine_config(str(d)).reason_class == \
        "not-regular-file"


def test_fifo_returns_malformed_within_one_second(clean_env):
    """AC-13 / BR-5. A fifo with no writer blocks `open()` forever without
    `O_NONBLOCK`, and the observed symptom was a `--version` that never
    returned.

    A thread and a flag, never `signal.alarm` and never a timeout exception:
    `TimeoutError` IS an `OSError`, so a loader that maps `OSError` to malformed
    would swallow the very alarm meant to catch it and the test would pass on a
    hang. The thread finishing is the assertion.
    """
    if not hasattr(os, "mkfifo"):
        pytest.skip("no os.mkfifo on this platform")
    fifo = clean_env / "config.yml"
    try:
        os.mkfifo(str(fifo))
    except (OSError, NotImplementedError) as exc:
        pytest.skip("mkfifo unavailable here: %s" % exc)

    box = {}

    def read_it():
        box["outcome"] = _machine_config.load_machine_config(str(fifo))
        box["cfg"] = _common.parse_delegate_config(str(fifo))

    t = threading.Thread(target=read_it)
    t.daemon = True
    t.start()
    t.join(1.0)
    assert not t.is_alive(), "the fifo read did not return within one second"
    assert box["outcome"].kind == "malformed"
    assert box["outcome"].reason_class == "not-regular-file"
    assert box["cfg"].get(_common._MALFORMED) is True


def test_unreadable_and_undecodable_and_over_cap_are_malformed(clean_env):
    """Three refusals that a `{}` return would have turned into continuity."""
    if not (hasattr(os, "geteuid") and os.geteuid() == 0):
        locked = clean_env / "locked.yml"
        locked.write_text("delegate:\n  enabled: false\n", encoding="utf-8")
        locked.chmod(0o000)
        try:
            outcome = _machine_config.load_machine_config(str(locked))
            assert outcome.reason_class == "unreadable"
        finally:
            locked.chmod(0o644)

    undecodable = _load(clean_env, b"delegate:\n  enabl\xe9d: false\n")
    assert undecodable.reason_class == "undecodable"

    at_cap = b"# " + b"c" * (_machine_config.CONFIG_CAP_BYTES - 3) + b"\n"
    assert len(at_cap) == _machine_config.CONFIG_CAP_BYTES
    assert _machine_config.load_machine_config(
        _write(clean_env, at_cap)).kind == "parsed"
    assert _machine_config.load_machine_config(
        _write(clean_env, at_cap + b"#\n")).reason_class == "over-cap"


def test_a_bom_and_crlf_do_not_hide_the_opt_out(clean_env):
    """Two encodings an editor produces on its own, either of which made the
    first key unmatchable for a text-comparing reader."""
    for body in (b"\xef\xbb\xbfdelegate:\n  enabled: false\n",
                 b"delegate:\r\n  enabled: false\r\n",
                 b"\xef\xbb\xbfdelegate:\r\n  enabled: false\r\n",
                 # PyYAML skips one BOM itself; the second is ours to strip,
                 # and a file that went through two BOM-adding tools has two.
                 # Left unstripped the first key is `\ufeffdelegate`, the
                 # section reads as ABSENT, and absence grants.
                 b"\xef\xbb\xbf\xef\xbb\xbfdelegate:\n  enabled: false\n"):
        cfg = _common.parse_delegate_config(_write(clean_env, body))
        assert cfg == {"enabled": False}, body


# --- the property the enumerations cannot reach ----------------------------

def test_no_line_separator_can_turn_a_written_false_into_a_grant(clean_env):
    """A property, over every separator `str.splitlines` honours.

    The old reader split the file with `splitlines` and YAML splits it with its
    own rules, so "what is a line" had two answers and the difference was a
    fail-open. Rather than enumerate the separators a reviewer thought of, this
    asserts the invariant across all of them: the operator wrote `false`, so no
    separator may produce a grant. Malformed is an acceptable outcome; enabled
    is not.
    """
    separators = ["\n", "\r\n", "\r", "\v", "\f",
                  "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]
    # Each one really is a break `str.splitlines` honours — derived, not
    # trusted, so a future Python that adds one surfaces here rather than in a
    # fail-open nobody enumerated.
    for sep in separators:
        assert len(("a" + sep + "b").splitlines()) == 2, repr(sep)
    for sep in separators:
        body = ("delegate:\n  enabled: false" + sep + "  model: x\n")
        cfg = _common.parse_delegate_config(
            _write(clean_env, body.encode("utf-8")))
        if cfg.get(_common._MALFORMED) is True:
            continue
        assert cfg.get("enabled") is False, (repr(sep), cfg)


def test_reason_strings_carry_no_file_content(clean_env):
    """Reasons reach stderr and refusal messages. A key NAME may appear (it is
    the operator's own, and naming it is what makes the file fixable); a VALUE
    may not, and neither may the source line PyYAML quotes back in `str(exc)`.
    """
    secret = "s3cr3t-value-do-not-echo"
    bodies = [
        ("delegate:\n  model: %s\n  model: %s\n" % (secret, secret)).encode(),
        ("delegate:\n\tmodel: %s\n" % secret).encode(),
        ("delegate: [%s\n" % secret).encode(),
        ("delegate:\n  model: %s\n  enbaled: false\n" % secret).encode(),
    ]
    for body in bodies:
        cfg = _common.parse_delegate_config(_write(clean_env, body))
        assert cfg.get(_common._MALFORMED) is True, body
        assert secret not in cfg.get(_common._MALFORMED_REASON, ""), body


# --- BR-6: an absent section is unconfigured, not locked out ---------------

def test_absent_section_is_unconfigured(clean_env, monkeypatch):
    """"No block found is malformed" was a workaround for a reader that could
    not tell absent from unrecognised, and it locked out every machine whose
    shared config carried only a `forge:` section. A real parser can tell the
    difference, so the rule gets simpler (BR-6).
    """
    assert _machine_config.validate_delegate_section({}) == {}
    assert _machine_config.validate_delegate_section(
        {"forge": {"provider": "github"}}) == {}
    assert _machine_config.validate_delegate_section(None) == {}

    path = _write(clean_env, b"forge:\n  provider: github\n")
    monkeypatch.setenv("ADLC_CONFIG", path)
    assert _common.parse_delegate_config() == {}
    # Unconfigured, so the continuity arm below it still applies...
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    assert _common.delegation_enabled() is True
    # ...and an absent FILE is the same answer, which is what makes this
    # different from a refusal.
    monkeypatch.setenv("ADLC_CONFIG", str(clean_env / "not-there.yml"))
    assert _common.parse_delegate_config() == {}
    assert _common.delegation_enabled() is True


# --- BR-7: the closed schema -----------------------------------------------

_ACCEPTS = [
    ({"delegate": {"enabled": True}}, {"enabled": True}),
    ({"delegate": {"enabled": False}}, {"enabled": False}),
    # PyYAML 1.1 booleans arrive as real bools; the REQ accepts them here.
    ({"delegate": {"enabled": True, "model": "m", "base_url": "https://h/v1",
                   "api_key_env": "MY_KEY"}},
     {"enabled": True, "model": "m", "base_url": "https://h/v1",
      "api_key_env": "MY_KEY"}),
    ({"delegate": {}}, {}),
    ({"delegate": {"model": ""}}, {"model": ""}),
    ({"forge": {"provider": "github"}}, {}),
]

_REFUSES = [
    ("section is a list", {"delegate": ["enabled"]}),
    ("section is a scalar", {"delegate": "enabled: true"}),
    ("section is null", {"delegate": None}),
    ("enabled is the string false", {"delegate": {"enabled": "false"}}),
    ("enabled is the string true", {"delegate": {"enabled": "true"}}),
    ("enabled is a number", {"delegate": {"enabled": 1}}),
    ("enabled is zero", {"delegate": {"enabled": 0}}),
    ("enabled is null", {"delegate": {"enabled": None}}),
    ("enabled is a mapping", {"delegate": {"enabled": {"x": True}}}),
    ("enabled is a sequence", {"delegate": {"enabled": [True]}}),
    ("model is a number", {"delegate": {"model": 3}}),
    ("model is a mapping", {"delegate": {"model": {"name": "m"}}}),
    ("model is a sequence", {"delegate": {"model": ["m"]}}),
    ("model is null", {"delegate": {"model": None}}),
    ("base_url is a mapping", {"delegate": {"base_url": {"host": "h"}}}),
    ("api_key_env is a sequence", {"delegate": {"api_key_env": ["K"]}}),
    ("unknown key", {"delegate": {"enbaled": False}}),
    ("unknown nested mapping", {"delegate": {"nested": {"enabled": True}}}),
    ("unknown key beside a good one",
     {"delegate": {"enabled": False, "version": 2}}),
    # The unknown-key arm's ONLY witness: an unknown key whose value is a
    # string slips past every per-field type check, so deleting that arm is
    # invisible without this row (found by mutation, not by review).
    ("unknown key with a string value",
     {"delegate": {"enabled": False, "note": "a reminder"}}),
    ("unknown key alone with a string value", {"delegate": {"note": "hi"}}),
    ("non-string key", {"delegate": {1: True}}),
    ("top level is a list", ["delegate"]),
    ("top level is a scalar", "delegate"),
]


@pytest.mark.parametrize("document,expected", _ACCEPTS,
                         ids=[str(i) for i in range(len(_ACCEPTS))])
def test_schema_accepts(document, expected):
    assert _machine_config.validate_delegate_section(document) == expected


@pytest.mark.parametrize("label,document", _REFUSES, ids=[r[0] for r in _REFUSES])
def test_schema_refuses(label, document):
    """BR-7. Unknown keys refuse deliberately: `enbaled: false` silently
    ignored costs an exfiltration, and forward compatibility can be versioned
    (LESSON-483 — a detected miss refuses, it never guesses).

    A quoted `"false"` is the YAML STRING `"false"`, which Python treats as
    true. Lowercasing it into an opt-out would be inventing an instruction the
    operator did not write; refusing it says so out loud.

    `bool` is checked, never `int`, even though `bool` is a subclass of `int` —
    so a `1` is refused rather than accepted as an opt-in.
    """
    with pytest.raises(_machine_config.SchemaError):
        _machine_config.validate_delegate_section(document)


def test_schema_refusal_reaches_the_adapter_as_malformed(clean_env):
    """A file that parses but says something unallowed is exactly as unusable
    as one that does not parse, and the adapter must say so — not return the
    keys it did understand."""
    cfg = _common.parse_delegate_config(
        _write(clean_env, b"delegate:\n  enabled: false\n  version: 2\n"))
    assert cfg.get(_common._MALFORMED) is True
    assert cfg.get(_common._MALFORMED_REASON, "").startswith("schema:")
    assert "version" in cfg[_common._MALFORMED_REASON]
    assert "enabled" not in cfg


def test_delegate_keys_match_the_documented_keys():
    """LESSON-331: a closed schema rots unless a structural test pins it to the
    doc that describes it. The README's config example IS the contract an
    operator reads, so the allowed-key constant is compared against it."""
    with open(_README, encoding="utf-8") as fh:
        readme = fh.read()
    block = re.search(r"### Config file.*?```yaml\n(.*?)```", readme, re.S)
    assert block, "the README no longer has a `### Config file` yaml example"
    documented = set(re.findall(r"^  ([a-z_]+):", block.group(1), re.M))
    assert documented == set(_machine_config.DELEGATE_KEYS), (
        sorted(documented), sorted(_machine_config.DELEGATE_KEYS))


# --- BR-1 / BR-9: PyYAML is pinned, imported lazily, and refused loudly -----

def test_requirements_pin_pyyaml():
    """BR-1: pinned in requirements.txt, at or above the 6.0 floor.

    `install.sh` installs from this file, so an unpinned parser means the thing
    that decides whether files leave the machine can change under a machine that
    changed nothing.
    """
    with open(_REQUIREMENTS, encoding="utf-8") as fh:
        lines = [ln.strip() for ln in fh if ln.strip()]
    pins = [ln for ln in lines if ln.lower().startswith("pyyaml")]
    assert len(pins) == 1, lines
    match = re.match(r"^pyyaml==([0-9]+)\.([0-9]+)", pins[0].lower())
    assert match, "pyyaml must be pinned with `==`: %r" % pins[0]
    assert (int(match.group(1)), int(match.group(2))) >= (6, 0), pins[0]


def _poison(tmp_path, statement):
    """A `yaml` package on PYTHONPATH that fails on import."""
    pkg = tmp_path / "poison" / "yaml"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(statement + "\n", encoding="utf-8")
    return str(tmp_path / "poison")


#: Both delegate CLIs. Every one of them parses the config on the path that
#: decides transmission, so a claim about "the CLI" is a claim about each.
_CLIS = ("adlc-read", "adlc-write")


def _cli(argv, env, name="adlc-read"):
    return subprocess.run([sys.executable, os.path.join(_DELEGATE, name)] + argv,
                          capture_output=True, text=True, env=env, timeout=30)


def test_help_does_not_import_yaml(clean_env, tmp_path):
    """AC-12 / BR-1: `--help` and a config-less `--version` never pay for the
    parser import (LESSON-022, BUG-056).

    The poison raises `RuntimeError`, not `ImportError`, so an accidental import
    fails LOUDLY instead of being absorbed by the BR-9 branch and reported as a
    missing dependency. The last block is the control: the same poison, on a
    path that MUST read a config, brings the process down — without it this test
    would pass just as well against a module nothing ever imports.
    """
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(clean_env),
           "PYTHONPATH": _poison(tmp_path, 'raise RuntimeError("imported yaml")')}

    helped = _cli(["--help"], env)
    assert helped.returncode == 0, helped.stdout + helped.stderr
    assert "usage:" in helped.stdout
    assert "RuntimeError" not in helped.stderr

    versioned = _cli(["--version"], env)
    assert versioned.returncode == 0, versioned.stdout + versioned.stderr
    assert "adlc-toolkit" in versioned.stdout
    assert "RuntimeError" not in versioned.stderr

    cfg = _write(clean_env, b"delegate:\n  enabled: true\n")
    control = _cli(["--print-gate"], dict(env, ADLC_CONFIG=cfg))
    assert control.returncode != 0, "the poisoned module was never imported"
    assert "RuntimeError" in control.stderr


@pytest.mark.parametrize("cli_name", _CLIS)
def test_missing_pyyaml_refuses_and_names_package(cli_name, clean_env, tmp_path,
                                                  monkeypatch, capsys):
    """AC-3 / BR-9: a partial install fails CLOSED, with one line naming the
    package — never through to `{}`, which is absence, which grants.

    Both surfaces: the loader in-process, and the real CLI with a poisoned
    module on PYTHONPATH.

    Parametrised over BOTH CLIs. `adlc-write` reaches the same gate through its
    own argv scan and its own `--print-gate` arm, and a claim proved on
    `adlc-read` alone is a claim about one of the two binaries that transmit —
    which is exactly the shape of defect this REQ keeps finding: a verdict that
    is right on one surface and absent on another.
    """
    path = _write(clean_env, b"delegate:\n  enabled: true\n")
    monkeypatch.setitem(sys.modules, "yaml", None)   # import raises ImportError
    _machine_config._reset_dependency_notice()
    try:
        outcome = _machine_config.load_machine_config(path)
        assert outcome.kind == "malformed"
        assert outcome.reason_class == "dependency-missing"
        first = capsys.readouterr().err
        assert "PyYAML" in first
        assert first.count("PyYAML") == 1
        # Three surfaces parse the config on one --print-gate; three identical
        # lines read as three problems.
        _machine_config.load_machine_config(path)
        assert capsys.readouterr().err == ""
        cfg = _common.parse_delegate_config(path)
        assert cfg.get(_common._MALFORMED) is True
        assert _common.delegation_enabled(cfg) is False
    finally:
        _machine_config._reset_dependency_notice()

    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(clean_env),
           "ADLC_CONFIG": path, "MOONSHOT_API_KEY": "sk-legacy",
           "PYTHONPATH": _poison(tmp_path, 'raise ImportError("poisoned")')}
    gate = _cli(["--print-gate"], env, name=cli_name)
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert gate.stdout.strip() == "0 disabled-via-config", gate.stdout
    assert "PyYAML" in gate.stderr
    assert gate.stderr.count("PyYAML") == 1, gate.stderr


# --- BR-13 / AC-9: the refusal names the path and the condition ------------

def test_refusal_names_path_and_condition(clean_env, monkeypatch):
    """The generic refusal tells a locked-out operator to edit the file that is
    unreadable, and to set an env var that CANNOT lift this arm — `_MALFORMED`
    outranks `ADLC_DELEGATE_ENABLED` in the cascade. Advice that does not work
    reads as the control having been ignored.

    So the malformed branch names the file and the condition — for a duplicate
    key, the key and its line — and mentions no env var at all.
    """
    path = _write(clean_env, b"delegate:\n  enabled: false\n  enabled: true\n")
    cfg = _common.parse_delegate_config(path)
    with pytest.raises(SystemExit) as exc:
        _common.require_delegation_enabled("adlc-read", cfg)
    message = str(exc.value)
    assert path in message
    assert "duplicate-key" in message
    assert "'enabled'" in message
    assert "line 3" in message
    assert "ADLC_DELEGATE_ENABLED" not in message

    # Not vacuous: the ordinary not-opted-in refusal still gives that advice.
    with pytest.raises(SystemExit) as plain:
        _common.require_delegation_enabled("adlc-read", {})
    assert "ADLC_DELEGATE_ENABLED" in str(plain.value)

    # And the real surface says the same thing.
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(clean_env),
           "ADLC_CONFIG": path, "MOONSHOT_API_KEY": "sk-legacy"}
    env = _child_env.with_yaml(env)
    src = clean_env / "f.md"
    src.write_text("secret contents", encoding="utf-8")
    r = _cli(["--paths", str(src), "--question", "q"], env)
    assert r.returncode != 0
    assert path in r.stderr, r.stderr
    assert "duplicate-key" in r.stderr, r.stderr
    assert "ADLC_DELEGATE_ENABLED" not in r.stderr, r.stderr
    assert "secret contents" not in r.stdout + r.stderr


def test_refusal_reason_is_one_line(clean_env):
    """The refusal is read out of a terminal and quoted into bug reports; a
    reason carrying a newline or an escape would let a config file forge extra
    lines in it."""
    path = _write(clean_env,
                  "delegate:\n  \"a\\nb\\u001b[31m\": false\n".encode("utf-8"))
    cfg = _common.parse_delegate_config(path)
    with pytest.raises(SystemExit) as exc:
        _common.require_delegation_enabled("adlc-read", cfg)
    reason_line = str(exc.value).split("\n")[0]
    assert "\x1b" not in str(exc.value)
    assert "cannot be used" in reason_line
