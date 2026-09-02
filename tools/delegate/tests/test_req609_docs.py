"""REQ-609 TASK-099 — the documentation contract, pinned so it cannot drift back.

Every claim this REQ writes into a document is a claim about behaviour that four
adversarial passes had to find the hard way, and prose has no compiler. The
failure mode is specific and has already happened once in this area: REQ-603
corrected the resolver and left `partials/delegate-gate.md` describing the
resolver it had just replaced, so the doc a call-site author reads told them to
do the thing the code now refuses.

So the doc claims are held to the code the way a schema is held to its
documentation (LESSON-331):

  * the README's schema table is compared against `_machine_config.DELEGATE_KEYS`
    — the constant, not a transcription of it;
  * the documented caps are compared against `CONFIG_CAP_BYTES` / `RC_CAP_BYTES`;
  * the "bare name" phrase is allowed to survive only in sentences that say it is
    rejected, checked with fixed strings (no `\\b` — LESSON-013 — and no regex at
    all on that path);
  * the two amendments (REQ-515 ADR-3, REQ-603 BR-14) are required to *append*:
    each test asserts the original text is still present and that the new block
    comes after it, so "amend" cannot quietly become "rewrite".

Where an assertion is an absence, it carries a positive control that plants the
shape it excludes and proves the checker still sees it (LESSON-602: an exclusion
test needs a working subject).
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _machine_config  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_DELEGATE = os.path.dirname(_HERE)
_REPO = os.path.dirname(os.path.dirname(_DELEGATE))

README = os.path.join(_DELEGATE, "README.md")
TEST_VERSION = os.path.join(_HERE, "test_version.py")
GATE_MD = os.path.join(_REPO, "partials", "delegate-gate.md")
GATE_SH = os.path.join(_REPO, "partials", "delegate-gate.sh")
_SPECS = os.path.join(_REPO, ".adlc", "specs")
REQ_515 = os.path.join(
    _SPECS, "REQ-515-provider-agnostic-delegation", "architecture.md")
REQ_603 = os.path.join(
    _SPECS, "REQ-603-single-source-delegation-opt-in-predicate", "requirement.md")
REQ_609 = os.path.join(
    _SPECS, "REQ-609-real-config-parser-and-resolver-hardening", "requirement.md")


def _read(path):
    assert os.path.isfile(path), "document moved or was deleted: %s" % path
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --- BR-14 / AC-10: the two amendments append, they do not rewrite ---------

def test_req515_adr3_amended():
    """REQ-515 ADR-3 said "NOT PyYAML ... for three scalar fields". REQ-609
    reverses that half, and the amendment has to carry the reasoning, because a
    reversal without one reads as drift to whoever meets it next.

    The original decision text must SURVIVE and the amendment must come after
    it: a spec that quietly rewrites its own history destroys the only record of
    why the first answer was reasonable when it was given.
    """
    text = _read(REQ_515)
    start = text.index("### ADR-3")
    adr3 = text[start:text.index("### ADR-4", start)]

    # The original decision, still on the page (the control for "append").
    original = "minimal hand-rolled flat-`key: value` parser"
    assert original in adr3, "ADR-3's original decision text was rewritten"
    assert "dependency for three scalar fields" in adr3

    marker = "**Amendment (2026-09-02, REQ-609)**"
    assert marker in adr3, "no dated REQ-609 amendment block in ADR-3"
    assert adr3.index(marker) > adr3.index(original), (
        "the amendment must come after the decision it amends")

    # The four reasons from the REQ's Description, each identifiable.
    amendment = adr3[adr3.index(marker):]
    assert "sole authority" in amendment          # the scalars gate exfiltration
    assert "`openai`" in amendment                # the venv already pins one
    assert "nine" in amendment                    # nine fail-opens
    assert "differential oracle" in amendment     # how PyYAML is constrained
    assert "safe_load" in amendment


def test_req603_br14_discharged():
    """REQ-603 BR-14 is the known-limitation note that points here. It must now
    say who discharged it, with the PR, and name BOTH halves — a note that says
    "fixed" without saying which fix is not a pointer anyone can follow.

    As above, the limitation text itself stays: it is the record of what was
    broken, and the parity suite's D6-D11 rows are its measurements.
    """
    text = _read(REQ_603)
    br14 = [ln for ln in text.splitlines() if ln.lstrip().startswith("- [ ] BR-14")]
    assert len(br14) == 1, br14
    line = br14[0]

    assert "fails open on ordinary YAML shapes" in line, (
        "BR-14's record of the limitation was rewritten rather than appended to")
    assert "discharged by req-609" in line.lower()
    assert "PR #149" in line
    assert "ADR-1" in line and "ADR-3" in line, (
        "the discharge note must name both halves: parser (ADR-1), resolver (ADR-3)")

    out_of_scope = text[text.index("## Out of Scope"):]
    parser_line = [
        ln for ln in out_of_scope.splitlines()
        if "shell-state-free binary resolution" in ln
    ]
    assert len(parser_line) == 1, parser_line
    assert "REQ-609" in parser_line[0] and "PR #149" in parser_line[0]


# --- BR-15 / AC-11: "bare name" survives only where it is refused ----------

_BARE_NAME = "bare name"
_ALLOWED = ("reject", "never")


def _bare_name_offenders(text):
    """Lines mentioning the bare name without saying it is rejected.

    Fixed-string containment only. BSD `grep -E` has no `\\b` (LESSON-013) and
    the habit is worth keeping even in Python: a regex here would be re-read as
    one by the next editor and the word boundaries would start mattering.
    """
    offenders = []
    for number, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        if _BARE_NAME in low and not any(word in low for word in _ALLOWED):
            offenders.append((number, line))
    return offenders


def test_bare_name_only_rejected():
    """AC-11: `grep -rn "bare name"` over the gate and its protocol doc matches
    only text saying the bare name is rejected.

    The doc used to *prescribe* it — "`adlc-read` — the bare name, when it is on
    PATH" — beside a call-site contract telling authors to fall back to it. Both
    are retired; the phrase may still appear, but only in the sentences that
    explain why it is refused.
    """
    subjects = {}
    for path in (GATE_SH, GATE_MD):
        subjects[path] = _read(path)

    for path, text in subjects.items():
        offenders = _bare_name_offenders(text)
        assert not offenders, (
            "%s: `bare name` mentioned without saying it is rejected:\n%s"
            % (os.path.basename(path), "\n".join("  %d: %s" % o for o in offenders))
        )

    # Not vacuous: the phrase is still there to be checked. A future edit that
    # deletes it entirely is fine on the merits, but this test would then be
    # asserting nothing and should be revisited rather than silently kept.
    assert any(_BARE_NAME in t.lower() for t in subjects.values()), (
        "no line mentions the bare name any more — this check has no subject")

    # The sibling half of the same contract: the retired call-site spelling is
    # gone from the protocol doc (the linter covers `SKILL.md`, not this file).
    assert "ADLC_READ_BIN:-adlc-read" not in subjects[GATE_MD]


def test_bare_name_checker_flags_the_retired_sentence():
    """Positive control for the exclusion above (LESSON-602).

    The subject is the exact sentence the doc used to carry. If the checker
    stopped seeing it, `test_bare_name_only_rejected` would pass against a doc
    that had drifted all the way back.
    """
    retired = (
        "- `adlc-read` — the bare name, when it is on PATH (PATH wins);\n"
        "- empty — neither.\n"
    )
    offenders = _bare_name_offenders(retired)
    assert [n for n, _ in offenders] == [1], offenders

    # And the shapes that must NOT be flagged, so the checker is not merely
    # matching the phrase.
    for benign in (
        "a bare name is never exported by the resolver\n",
        "REQ-603 closed that by rejecting an answer that came back as a bare name\n",
    ):
        assert _bare_name_offenders(benign) == [], benign


# --- BR-15: the README names the caps, the resolver rule, and the rc read ---

def test_readme_names_cap_relative_path_and_version_rc_read():
    """The three facts BR-15 names, each pinned to the constant behind it where
    there is one — a documented "64 KiB" that no longer matches
    `CONFIG_CAP_BYTES` is worse than no number at all, because an operator sizes
    their config against it.
    """
    readme = _read(README)

    assert _machine_config.CONFIG_CAP_BYTES == 64 * 1024
    assert _machine_config.RC_CAP_BYTES == 256 * 1024
    assert "64 KiB" in readme, "the config cap is not documented"
    assert "256 KiB" in readme, "the rc-file read cap is not documented"

    # The cap is unconditional, and the README has to say why.
    assert "truncated YAML document can still parse" in readme

    # BR-11: a relative $PATH entry is not a property of the machine's install.
    assert "does not begin with `/` is rejected" in readme
    assert "`command -v`" in readme and "never" in readme

    # The rc-file read, its files, and which surface reaches it.
    for rc in ("~/.zshrc", "~/.bash_profile", "~/.bashrc"):
        assert rc in readme, rc
    assert "--print-gate" in readme
    assert "never sources or evaluates" in readme.lower()

    # BR-1 / BR-9: the floor, and what a machine without the parser does.
    assert ">=6.0" in readme
    assert "dependency-missing" in readme


# --- BR-15: the shipped-defaults test loses its fail-SOFT framing ----------

def _unparseable_test_region():
    """The header comment plus the body of the shipped-defaults test."""
    text = _read(TEST_VERSION)
    name = "def test_unparseable_config_reports_shipped_defaults"
    idx = text.find(name)
    assert idx != -1, (
        "test_unparseable_config_reports_shipped_defaults is gone — BR-15 says "
        "the header changes, not the test")
    start = text.rfind("\n# ---", 0, idx)
    assert start != -1
    end = text.find("\n# ---", idx)
    return text[start:end if end != -1 else len(text)]


def test_shipped_defaults_header_no_longer_says_fail_soft():
    """"fail-SOFT is deliberate" described a reader that could not tell an
    unreadable config from an absent one, so falling through to the defaults was
    all it could honestly do. Since REQ-609 the file IS refused — the opt-in
    fails closed — and only the *provider block* still reports the defaults,
    because `config_error:` marks a refused written value and nothing here was
    written. Keeping the old header would document the fail-open the REQ closed.
    """
    region = _unparseable_test_region()
    assert "fail-soft" not in region.lower(), region

    # The replacement says what is true now, and the test asserts it.
    assert "disabled-via-config" in region
    assert 'cfg["enabled"]' in region, (
        "the fail-closed half is documented but not asserted")


# --- BR-1 / AC-12: the probe's cost is measured, before and after ----------

_MS = r"([0-9]+(?:\.[0-9]+)?)\s*(?:\*\*)?\s*ms"


def _assumptions_section(text):
    start = text.index("## Assumptions")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def _probe_medians(section):
    """The before/after medians, in ms, as floats.

    Each is required on ONE line with its label, so the two cannot be matched
    across a paragraph break and reported as a pair that was never written.
    """
    out = {}
    for label in ("before", "after"):
        match = re.search(label + r"[^\n]*?" + _MS, section, re.I)
        out[label] = float(match.group(1)) if match else None
    return out


def test_assumptions_record_probe_cost():
    """AC-12: the REQ assumed "roughly thirty milliseconds. Unmeasured." and
    said the AC records the measurement either way. This is that record.

    Both halves are required — a lone "after" number is not a cost, and a cost
    with no comparison to the step it sits inside is not a decision.
    """
    section = _assumptions_section(_read(REQ_609))

    assert "Unmeasured" not in section, (
        "the unmeasured assumption is still in Assumptions")
    assert "median" in section.lower()

    medians = _probe_medians(section)
    assert medians["before"] is not None, "no `before` median in ms"
    assert medians["after"] is not None, "no `after` median in ms"
    assert medians["before"] > 0 and medians["after"] > 0

    # The command, so the number can be re-taken rather than believed.
    assert "--print-gate" in section
    assert "delegate-venv/bin/python3" in section

    # And the comparison that makes the number a decision: REQ-603 measured a
    # 104-second median delegated step.
    assert "104" in section


def test_probe_cost_parser_needs_both_numbers():
    """Positive control for the two assertions above: a bullet that records only
    one side, or neither, must not satisfy them.
    """
    assert _probe_medians("before: median 21.2 ms\nafter: median 25.5 ms") == {
        "before": 21.2, "after": 25.5}
    only_one = _probe_medians("before: median 21.2 ms\nafter: not taken yet\n")
    assert only_one["before"] == 21.2 and only_one["after"] is None
    neither = _probe_medians("roughly thirty milliseconds. Unmeasured.\n")
    assert neither == {"before": None, "after": None}


# --- BR-7: the README's schema table IS the closed schema -----------------

_SCHEMA_START = "<!-- delegate-schema:start -->"
_SCHEMA_END = "<!-- delegate-schema:end -->"


def _schema_table_keys(text):
    """The keys named in the first column of the anchored schema table."""
    start = text.index(_SCHEMA_START) + len(_SCHEMA_START)
    table = text[start:text.index(_SCHEMA_END, start)]
    keys = set()
    for line in table.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        first = line.strip("|").split("|")[0].strip()
        match = re.fullmatch(r"`([a-z_]+)`", first)
        if match:
            keys.add(match.group(1))
    return keys


def test_readme_keys_match_schema_constant():
    """LESSON-331: a closed schema rots unless a structural test pins it to the
    document that describes it — and the pin has to read the CONSTANT, not a
    second transcription of it.

    This matters more than usual here because the schema refuses unknown keys.
    A key documented but not allowed locks an operator out of a file they wrote
    from the docs; a key allowed but not documented is an unreviewed field on
    the object that decides whether source files leave the machine.
    """
    keys = _schema_table_keys(_read(README))
    assert keys == set(_machine_config.DELEGATE_KEYS), (
        sorted(keys), sorted(_machine_config.DELEGATE_KEYS))


def test_schema_table_parser_notices_a_missing_key():
    """Positive control: the parser must actually be reading rows, not returning
    something that happens to compare equal.
    """
    planted = (
        "%s\n\n"
        "| key | type | meaning |\n"
        "|-----|------|---------|\n"
        "| `enabled` | boolean | opt in |\n"
        "| `model` | string | the model |\n"
        "\n%s\n" % (_SCHEMA_START, _SCHEMA_END)
    )
    assert _schema_table_keys(planted) == {"enabled", "model"}
    assert _schema_table_keys(planted) != set(_machine_config.DELEGATE_KEYS)

    with pytest.raises(ValueError):
        _schema_table_keys("a README with no anchored schema table\n")
