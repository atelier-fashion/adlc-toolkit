"""REQ-609 BR-10 / ADR-5 — the differential oracle.

The reader this REQ replaces was written tests-first and mutation-proven, and
still shipped nine fail-opens. Six of them were introduced by the pass that
hardened it. The discipline proved everything its author had thought of; what it
could not do was reach a shape he had not. Two reviewers found six such shapes
in an hour, which is the measurement that matters: the suite's coverage was
bounded by one imagination, and the fix for that is not more imagination.

So this file does not state expected outcomes. It computes them from **PyYAML
itself** — ``yaml.safe_load`` for the value, a walk over ``yaml.compose``'s
mapping nodes for repeated keys, ``yaml.parse``'s events and those same nodes
for aliases and merge keys — plus a second, independent copy of the schema
rules, and then asserts our implementation agrees on every document in both
corpora. A disagreement is a finding, not a test to update (LESSON-602: an
exclusion test needs a working subject; here the working subject is the parser
we are differentiating against).

Three things are restated here rather than imported, deliberately:

  * the allowed key set,
  * the ``enabled``-must-be-a-bool rule and the three-strings rule,
  * the 64 KiB cap.

Importing them would make the oracle agree with the implementation by
construction, which is the one thing an oracle must not do. The cost is that a
deliberate change to any of the three fails this file too — which for a schema
that decides whether a developer's source files leave the machine is the point,
not the friction.
"""
import inspect
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _common  # noqa: E402
import _machine_config  # noqa: E402

from config_corpus import (  # noqa: E402
    GENERATED_SEED, TEXT_CORPUS, generated_corpus)

# --- the oracle -------------------------------------------------------------


class _Malformed(object):
    """The expected result when ``parse_delegate_config`` must report
    ``_MALFORMED``. A sentinel object rather than ``None`` or a string, because
    both of those are values a YAML document can produce and the comparison
    below is an identity test."""

    def __repr__(self):
        return "MALFORMED"


MALFORMED = _Malformed()

#: REQ BR-7's key set, restated. Not imported from `_machine_config`: an oracle
#: that reads the schema off the subject cannot disagree with it.
_ALLOWED_KEYS = frozenset(("enabled", "model", "base_url", "api_key_env"))

#: REQ BR-3's cap, restated for the same reason. The loader reads `cap + 1`
#: bytes and refuses when it got more, so a file of exactly the cap is fine.
_CAP_BYTES = 65536


def oracle_repeats_a_key(text):
    """True if any mapping in ``text`` repeats a key. Raises ``yaml.YAMLError``
    if ``text`` does not compose.

    Independent of ``_machine_config._StrictLoader`` by construction: it never
    constructs a Python object at all. ``yaml.compose`` stops at the node graph,
    so this walks ``ScalarNode`` keys and compares ``(tag, value)`` — the text of
    the key and the type YAML resolved it to — while the loader compares the
    objects its constructors build. Two implementations of "the same key",
    written against different layers of the same library.

    Known and accepted limit of comparing at the node layer: two *spellings* of
    one constructed key (``yes:`` and ``true:``, ``16:`` and ``0x10:``) are
    unequal here and equal in the loader. No document in either corpus contains
    a pair like that, and the difference runs in the safe direction — the
    implementation refuses a document this oracle would allow, never the
    reverse.
    """
    return _node_repeats_a_key(yaml.compose(text, Loader=yaml.SafeLoader))


def _node_repeats_a_key(node):
    """Recurse a composed node graph. Sequences recurse too, because a mapping
    with a duplicate can sit inside one and BR-2's refusal is whole-document."""
    if isinstance(node, yaml.MappingNode):
        seen = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, yaml.ScalarNode):
                ident = (key_node.tag, key_node.value)
                if ident in seen:
                    return True
                seen.add(ident)
            if _node_repeats_a_key(key_node):
                return True
            if _node_repeats_a_key(value_node):
                return True
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            if _node_repeats_a_key(item):
                return True
    return False


#: The tag PyYAML's resolver gives a plain `<<` key.
_MERGE_TAG = "tag:yaml.org,2002:merge"


def oracle_uses_alias_or_merge(text):
    """True if ``text`` contains an alias reference or a merge key. Raises
    ``yaml.YAMLError`` if ``text`` does not parse.

    Independent of ``_machine_config._StrictLoader`` by construction, and at a
    layer BELOW the one the implementation refuses at: the loader raises inside
    ``compose_node`` and ``flatten_mapping``, while this reads the finished
    event stream and the composed node graph and never constructs anything.

    Two signals, because there are two constructs and only one of them is
    visible in each place:

      * an alias is an ``AliasEvent`` in ``yaml.parse``. Events are used rather
        than nodes on purpose — ``yaml.compose`` RESOLVES an alias into a shared
        reference to the anchored node, so by the time there is a graph the
        alias is gone and the only trace is that one node object appears twice.
        Detecting that would mean tracking ``id()`` of every node seen; reading
        the event that says "alias" is the same answer without the bookkeeping.
      * a merge key is a ``<<`` scalar in KEY position, and "in key position" is
        a structural fact the flat event stream does not carry. The resolver
        does carry it: in a composed graph that key node's tag is
        ``tag:yaml.org,2002:merge``. So merges are read off the graph and
        aliases off the events, each from the layer that states it plainly.

    A merge written with an inline mapping (``<<: {a: 1}``) has no alias at all,
    and an alias can appear with no merge anywhere, so neither signal implies
    the other.
    """
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        if isinstance(event, yaml.AliasEvent):
            return True
    return _node_has_a_merge_key(yaml.compose(text, Loader=yaml.SafeLoader))


def _node_has_a_merge_key(node, seen=None):
    """Recurse a composed node graph looking for a merge-tagged KEY.

    ``seen`` guards against the shared nodes an alias leaves behind: a document
    that references one anchor twice composes to a graph where the same object
    is reachable by two paths, and an unguarded recursion over a self-referential
    anchor would not terminate at all.
    """
    if seen is None:
        seen = set()
    if id(node) in seen:
        return False
    seen.add(id(node))
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            if key_node.tag == _MERGE_TAG:
                return True
            if _node_has_a_merge_key(key_node, seen):
                return True
            if _node_has_a_merge_key(value_node, seen):
                return True
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            if _node_has_a_merge_key(item, seen):
                return True
    return False


def oracle_expectation(data):
    """What ``parse_delegate_config`` must return for ``data``: a dict, or
    :data:`MALFORMED`.

    The second implementation, in full. Every step is the rule as the REQ writes
    it, applied to what PyYAML says the document is:

      * over the cap                          -> malformed (BR-3, unconditional)
      * not UTF-8                             -> malformed (BR-3)
      * does not parse, or repeats a key      -> malformed (BR-3, BR-2)
      * uses an alias or a merge key          -> malformed (BR-2, BR-7)
      * null document                         -> ``{}``     (BR-3)
      * top level is not a mapping            -> malformed (BR-3)
      * no ``delegate`` key                   -> ``{}``     (BR-6, unconfigured)
      * section is not a mapping              -> malformed (BR-7)
      * an unknown key, a non-bool ``enabled``,
        a non-string elsewhere                -> malformed (BR-7)
      * otherwise                             -> the section

    A repeated key is asserted as malformed rather than COMPARED, because
    ``safe_load`` silently takes the last of a duplicate — the exact silent
    override BR-2 exists to refuse. Where the subject and the oracle would
    disagree by design, the oracle states the rule instead of consulting the
    library.
    """
    if len(data) > _CAP_BYTES:
        return MALFORMED
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return MALFORMED
    # One leading BOM, exactly as a UTF-8 sig-stripping reader would. PyYAML
    # itself skips one more at index 0, which is why a DOUBLE BOM still parses.
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        document = yaml.safe_load(text)
        repeats = oracle_repeats_a_key(text)
        borrows = oracle_uses_alias_or_merge(text)
    except Exception:
        # `Exception`, not `yaml.YAMLError`. PyYAML's constructors raise plain
        # built-ins straight out of the standard library — `ValueError` from
        # `datetime` on `2026-09-31`, `KeyError` from a `!!bool` lookup table,
        # `AttributeError` from `!!timestamp` — and BR-3's "never raises" makes
        # every one of those a `malformed`. An oracle that caught only
        # `YAMLError` would raise here instead of stating an expectation, so the
        # row it was meant to check would ERROR rather than disagree.
        return MALFORMED
    if repeats:
        return MALFORMED
    if borrows:
        # An alias or a merge assembles the section's meaning from somewhere
        # else in the document; `safe_load` resolves it silently, which is the
        # override BR-2 refuses one construct further out. Stated as a rule
        # rather than compared, for the same reason a repeated key is.
        return MALFORMED
    if document is None:
        document = {}
    if not isinstance(document, dict):
        return MALFORMED
    if "delegate" not in document:
        return {}
    section = document["delegate"]
    if not isinstance(section, dict):
        return MALFORMED
    expected = {}
    for key in section:
        value = section[key]
        if not isinstance(key, str) or key not in _ALLOWED_KEYS:
            return MALFORMED
        if key == "enabled":
            # `bool`, never `int`: `True` is an int in Python and `1` is not a
            # YAML boolean. A quoted "false" arrives here as a str and refuses.
            if not isinstance(value, bool):
                return MALFORMED
        elif not isinstance(value, str):
            return MALFORMED
        expected[key] = value
    return expected


# --- fixtures ---------------------------------------------------------------

_VARS = (
    "MOONSHOT_API_KEY", "KIMI_API_KEY", "ADLC_DELEGATE_MODEL",
    "ADLC_DELEGATE_BASE_URL", "ADLC_DELEGATE_API_KEY_ENV",
    "ADLC_DELEGATE_ENABLED", "ADLC_CONFIG", "ADLC_DISABLE_DELEGATE",
    "MY_PROVIDER_KEY",
)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Every opt-in, veto, and key variable cleared, and ``HOME`` redirected.

    The same fixture the other suites here use: without it a developer's own
    exported key decides half these rows, and the corpus stops being the thing
    under test.
    """
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


#: Both corpora as ``(name, bytes)``. The seeded half is every shape a reviewer
#: found; the generated half is the product of the axes those findings ran along.
_SEEDED = [(e.name, e.data) for e in TEXT_CORPUS]
_GENERATED = [(g.name, g.data) for g in generated_corpus(GENERATED_SEED)]


def _write(tmp_path, data):
    path = tmp_path / "config.yml"
    path.write_bytes(data)
    return str(path)


def _agreement_failure(name, data, tmp_path):
    """Compare one document. Returns a description of the disagreement, or None.

    Returns rather than asserts so a corpus run can report EVERY disagreement in
    one go: with 864 generated documents, failing on the first one turns a
    systematic difference into a one-at-a-time hunt.
    """
    path = _write(tmp_path, data)
    expected = oracle_expectation(data)
    cfg = _common.parse_delegate_config(path)
    malformed = cfg.get(_common._MALFORMED) is True
    if expected is MALFORMED:
        if not malformed:
            return "%s: oracle says malformed, parse_delegate_config says %r" % (
                name, cfg)
        return None
    if malformed:
        return "%s: oracle says %r, parse_delegate_config says malformed (%s)" % (
            name, expected, cfg.get(_common._MALFORMED_REASON))
    if cfg != expected:
        return "%s: oracle says %r, parse_delegate_config says %r" % (
            name, expected, cfg)
    return None


# --- BR-10: the two corpora against safe_load -------------------------------

@pytest.mark.parametrize("name,data", _SEEDED, ids=[n for n, _ in _SEEDED])
def test_seeded_corpus_agrees_with_safe_load(name, data, clean_env):
    """Every shape REQ AC-1 enumerates that is a FILE, against PyYAML directly.

    Parametrised one-per-shape rather than looped, because each of these is a
    named finding from a review pass and a red row should say which one broke.
    """
    failure = _agreement_failure(name, data, clean_env)
    assert failure is None, failure


def test_generated_corpus_agrees_with_safe_load(clean_env):
    """REQ AC-2 — the same comparison over the generated product.

    Looped rather than parametrised: 864 ids would drown the seeded rows above,
    and a systematic disagreement is easier to read as a list than as 800 red
    lines. Every disagreement is collected before the assert.

    The three coverage assertions are not decoration. An oracle test over a
    corpus that turned out to be uniformly malformed — one bad axis value would
    do it — passes while proving nothing about the parsed path, which is the
    path that grants (LESSON-602).
    """
    assert len(_GENERATED) >= 300, len(_GENERATED)
    assert len(set(n for n, _ in _GENERATED)) == len(_GENERATED)

    failures = []
    buckets = {"malformed": 0, "enabled-true": 0, "enabled-false": 0,
               "unconfigured": 0}
    for name, data in _GENERATED:
        failure = _agreement_failure(name, data, clean_env)
        if failure is not None:
            failures.append(failure)
        expected = oracle_expectation(data)
        if expected is MALFORMED:
            buckets["malformed"] += 1
        elif expected.get("enabled") is True:
            buckets["enabled-true"] += 1
        elif expected.get("enabled") is False:
            buckets["enabled-false"] += 1
        else:
            buckets["unconfigured"] += 1
    assert failures == [], "\n".join(failures[:20])
    for bucket in ("malformed", "enabled-true", "enabled-false"):
        assert buckets[bucket] > 0, (bucket, buckets)


# --- BR-2: the duplicate detector, on its own -------------------------------

_REPEATS = [
    ("two delegate blocks",
     b"delegate:\n  enabled: false\ndelegate:\n  enabled: true\n"),
    ("two enabled keys",
     b"delegate:\n  enabled: false\n  enabled: true\n"),
    ("a repeat under another section",
     b"forge:\n  provider: github\n  provider: azure\ndelegate:\n  enabled: false\n"),
    ("a repeat inside a sequence item",
     b"items:\n  - name: a\n    name: b\n  - name: c\n"),
    ("a quoted key repeating a plain one",
     b'delegate:\n  enabled: false\n  "enabled": true\n'),
]

# The working subject (LESSON-602). An exclusion test that only ever asserts
# "no duplicate found" passes on a detector that has been commented out, so
# every shape here must come back False from the SAME function that returns True
# above — including the shapes that look like repeats and are not.
_NO_REPEAT = [
    ("the same key in two different mappings",
     b"delegate:\n  enabled: false\nforge:\n  enabled: true\n"),
    ("the same key in two sequence items",
     b"items:\n  - name: a\n  - name: b\n"),
    ("a key repeated as a VALUE",
     b"delegate:\n  model: enabled\n  enabled: false\n"),
    ("two keys that differ only by resolved type",
     b'delegate:\n  enabled: false\nlimits:\n  1: one\n  "1": also-one\n'),
    ("the well-formed opt-in",
     b'delegate:\n  enabled: true\n  model: "m"\n  api_key_env: "MY_PROVIDER_KEY"\n'),
]


def _code_of(function):
    """``function``'s source with its docstring removed.

    The independence check below is a claim about what the detector CALLS, and
    prose that explains what it does not call would satisfy a naive substring
    search either way. Strip the prose and search the code.
    """
    source = inspect.getsource(function)
    return source.replace(function.__doc__ or "", "")


def test_oracle_marks_duplicates_independently(clean_env):
    """BR-2, and AC-5: the detector walks composed nodes, not our loader.

    Asserted three ways, because "it agreed with the implementation" is the one
    thing that would NOT prove independence:

      1. structurally — the function's source reaches ``yaml.compose`` and
         mentions neither ``_machine_config`` nor ``_StrictLoader``;
      2. positively — it finds every repeat, including one inside a sequence
         item and one spelled with quotes;
      3. negatively — it finds none in five documents that repeat nothing, two
         of which are shaped like repeats (the same key in two mappings, two
         sequence items with one key each).

    Then the implementation is held to the same answers, with the reason class
    checked: a duplicate must refuse AS a duplicate (BR-13 names the key and the
    line), not incidentally as some other malformation.
    """
    source = _code_of(oracle_repeats_a_key) + _code_of(_node_repeats_a_key)
    assert "yaml.compose" in source
    assert "_machine_config" not in source
    assert "_StrictLoader" not in source
    assert "parse_delegate_config" not in source

    for label, data in _REPEATS:
        text = data.decode("utf-8")
        assert oracle_repeats_a_key(text) is True, label
        outcome = _machine_config.load_machine_config(_write(clean_env, data))
        assert outcome.kind == "malformed", (label, outcome)
        assert outcome.reason_class == "duplicate-key", (label, outcome)

    for label, data in _NO_REPEAT:
        text = data.decode("utf-8")
        assert oracle_repeats_a_key(text) is False, label
        outcome = _machine_config.load_machine_config(_write(clean_env, data))
        assert outcome.kind == "parsed", (label, outcome)


# --- BR-2 / BR-7: the alias detector, on its own ----------------------------

_BORROWS = [
    ("a merge of an anchored mapping",
     b"defaults: &d\n  enabled: true\ndelegate:\n  <<: *d\n"),
    ("the whole section as an alias",
     b"base: &x\n  enabled: true\ndelegate: *x\n"),
    ("an alias on a scalar field",
     b'delegate:\n  model: &m "m"\n  base_url: *m\n'),
    ("a merge with an inline mapping and no alias",
     b"delegate:\n  <<: {enabled: true}\n"),
    ("an alias inside a sequence",
     b"anchors:\n  - &a x\n  - *a\ndelegate:\n  enabled: false\n"),
    ("an alias in a section this consumer does not read",
     b"anchors: &a\n  x: 1\nforge:\n  provider: *a\ndelegate:\n  enabled: false\n"),
]

# The working subject again (LESSON-602). A detector that has been commented out
# passes every row above only if some row here would have come back True — so
# these are documents that LOOK like the ones above and borrow nothing.
_NO_BORROW = [
    ("an anchor nobody references",
     b"delegate: &d\n  enabled: false\n"),
    ("a quoted `<<` as a VALUE",
     b'delegate:\n  model: "<<"\n'),
    ("an ampersand inside a string",
     b'delegate:\n  model: "a & b"\n  base_url: "https://h/v1?a=1&b=2"\n'),
    ("an asterisk inside a quoted string",
     b'delegate:\n  model: "*not-an-alias"\n'),
    ("the well-formed opt-in",
     b'delegate:\n  enabled: true\n  model: "m"\n'),
]


def test_oracle_marks_aliases_independently(clean_env):
    """BR-2/BR-7: the detector reads events and composed nodes, not our loader.

    Asserted the same three ways the duplicate detector is, and for the same
    reason — agreeing with the implementation is the one thing that would not
    prove independence:

      1. structurally — the source reaches ``yaml.parse`` and ``yaml.compose``
         and mentions neither ``_machine_config`` nor the loader's overrides;
      2. positively — it finds every borrow, including a merge written with an
         inline mapping (no alias in the document at all) and an alias in a
         section this consumer does not read;
      3. negatively — it finds none in five documents that borrow nothing, four
         of which are shaped like borrows: a bare anchor, a quoted ``<<``, an
         ``&`` inside a URL, an ``*`` inside a quoted string.

    Then the implementation is held to the same answers WITH the reason class
    checked. A merge beside an explicit key used to refuse as ``duplicate-key``,
    which is a true refusal for a false reason — BR-13's line number then points
    at a key the operator wrote exactly once.
    """
    source = _code_of(oracle_uses_alias_or_merge) + _code_of(_node_has_a_merge_key)
    assert "yaml.parse" in source
    assert "yaml.compose" in source
    assert "_machine_config" not in source
    assert "_StrictLoader" not in source
    assert "compose_node" not in source
    assert "flatten_mapping" not in source
    assert "parse_delegate_config" not in source

    for label, data in _BORROWS:
        text = data.decode("utf-8")
        assert oracle_uses_alias_or_merge(text) is True, label
        outcome = _machine_config.load_machine_config(_write(clean_env, data))
        assert outcome.kind == "malformed", (label, outcome)
        assert outcome.reason_class == "alias-or-merge", (label, outcome)

    for label, data in _NO_BORROW:
        text = data.decode("utf-8")
        assert oracle_uses_alias_or_merge(text) is False, label
        outcome = _machine_config.load_machine_config(_write(clean_env, data))
        assert outcome.kind == "parsed", (label, outcome)


# --- BR-10: the three surfaces, on both corpora -----------------------------

def _expected_cascade(expected, legacy):
    """Re-derive ``delegation_enabled``'s answer and the gate's REASON from the
    ORACLE's expectation, never from the implementation.

    This is the cascade as REQ BR-11/BR-3 state it, with the kill switch and the
    env opt-in cleared by the fixture, so only two arms are live: what the file
    says, and legacy-key continuity beneath it.

      malformed          -> refuse, and SAY the config (BR-13)
      `enabled` written   -> decisive, either way
      `enabled` absent    -> continuity decides; a legacy key grants
    """
    if expected is MALFORMED:
        return False, "disabled-via-config"
    written = expected.get("enabled")
    if written is None:
        return (True, "ok") if legacy else (False, "not-opted-in")
    return (True, "ok") if written else (False, "disabled-via-config")


def test_three_surfaces_agree(clean_env, monkeypatch):
    """``parse_delegate_config``, ``delegation_enabled``, ``resolve_gate_verdict``
    and ``require_delegation_enabled`` on every document in both corpora.

    Run twice per document — with and without a legacy key — because that axis
    is exactly where *unconfigured* and *malformed* separate: both refuse when
    no key is exported, and only the first one grants when one is. A single-axis
    run would call the two states equal and miss BUG-205's whole shape.

    The first version of the unreadable-config fix reached only the probe: the
    gate refused while a direct CLI call still transmitted. So the backstop that
    actually guards transmission is asserted here beside the probe, and the
    expected values come from the oracle rather than from any of the four.
    """
    monkeypatch.setenv("ADLC_CONFIG", str(clean_env / "config.yml"))
    # A key the real resolver can find, under a name of our own, so that
    # legacy-key CONTINUITY is exercised only by the `legacy` axis below and not
    # smuggled in by the shipped default key var (the parity suite does the
    # same). Without it `resolve_gate_verdict` would refuse every granting row
    # for want of a key and look like it disagreed with the cascade.
    monkeypatch.setenv("ADLC_DELEGATE_API_KEY_ENV", "MY_PROVIDER_KEY")
    monkeypatch.setenv("MY_PROVIDER_KEY", "sk-resolvable")

    failures = []
    for legacy in (False, True):
        if legacy:
            monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
        else:
            monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        for name, data in _SEEDED + _GENERATED:
            _write(clean_env, data)
            expected = oracle_expectation(data)
            exp_enabled, exp_reason = _expected_cascade(expected, legacy)
            row = "%s (legacy=%s)" % (name, legacy)

            cfg = _common.parse_delegate_config()
            enabled = _common.delegation_enabled(cfg)
            verdict = _common.resolve_gate_verdict(cfg)
            try:
                _common.require_delegation_enabled("adlc-read", cfg)
                refused = False
            except SystemExit:
                refused = True

            if enabled is not exp_enabled:
                failures.append("%s: delegation_enabled=%r, oracle=%r"
                                % (row, enabled, exp_enabled))
            if verdict != (exp_enabled, exp_reason):
                failures.append("%s: resolve_gate_verdict=%r, oracle=%r"
                                % (row, verdict, (exp_enabled, exp_reason)))
            if refused is enabled:
                failures.append(
                    "%s: require_delegation_enabled %s while delegation_enabled=%r"
                    % (row, "refused" if refused else "allowed", enabled))
    assert failures == [], "\n".join(failures[:20])
