"""Test the lane-vocabulary check (REQ-652 BR-17, ADR-13).

`check_lane_vocabulary` reads the closed sets — lane, trigger, actor,
lane_check — from the `<!-- lane-vocabulary -->` block in
`partials/lane-check.md`, then scans every declared writer and reader of a lane
value (`LANE_SITES`) for a value outside them. Tests run the parser and the
check against synthetic tmp roots, plus a clean assertion against the REAL
toolkit tree.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_DIR = REPO_ROOT / "tools" / "lint-skills"

sys.path.insert(0, str(LINT_DIR))
import check  # noqa: E402

VOCAB_BLOCK = """<!-- lane-vocabulary -->
- lane: `lite`, `full`
- trigger: `blocked-path`, `dependency`, `deploy-units`, `max-files`, `check-error`, `implementer`, `reversal`, `operator`
- actor: `solo`, `sprint-runner`, `operator`
- lane_check: `pass`, `escalate`, `error`
<!-- /lane-vocabulary -->
"""


def _build_root(tmp_path: Path, vocab: str | None = VOCAB_BLOCK, sites: dict | None = None,
                omit: tuple = ()) -> Path:
    """tmp root with the vocabulary file and every LANE_SITES file.

    ``vocab``: the vocabulary file's text, or ``None`` to omit the file.
    ``sites``: relative path -> text override for that site (default: clean text).
    ``omit``: sites not to create at all.
    """
    if vocab is not None:
        p = tmp_path / check.LANE_VOCAB_SITE
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# lane check\n\n" + vocab, encoding="utf-8")
    sites = sites or {}
    for rel in check.LANE_SITES:
        if rel in omit:
            continue
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(sites.get(rel, 'Writes `lane: "lite"` or `lane: "full"`.\n'), encoding="utf-8")
    return tmp_path


def _checks(findings):
    return [f for f in findings if f.check == "lane-vocabulary"]


# --- parser -----------------------------------------------------------------

def test_parse_returns_every_set():
    vocab = check.parse_lane_vocab_block(VOCAB_BLOCK)
    assert vocab["lane"] == {"lite", "full"}
    assert vocab["actor"] == {"solo", "sprint-runner", "operator"}
    assert vocab["lane_check"] == {"pass", "escalate", "error"}
    assert "reversal" in vocab["trigger"] and len(vocab["trigger"]) == 8


def test_parse_distinguishes_absent_from_empty():
    assert check.parse_lane_vocab_block("no block here\n") is None
    assert check.parse_lane_vocab_block("<!-- lane-vocabulary -->\n<!-- /lane-vocabulary -->\n") == {}


def test_parse_ignores_marker_not_at_line_start():
    """LESSON-404 decoy: a prose mention of the marker is not the definition."""
    text = "The block is `<!-- lane-vocabulary -->` in lane-check.md.\n- lane: `medium`\n"
    assert check.parse_lane_vocab_block(text) is None


# --- check ------------------------------------------------------------------

def test_inert_outside_toolkit(tmp_path):
    """No vocabulary file and no lite companion: a root this check does not apply to."""
    assert check.check_lane_vocabulary(tmp_path) == []


def test_clean_root_has_no_findings(tmp_path):
    assert _checks(check.check_lane_vocabulary(_build_root(tmp_path))) == []


def test_unknown_lane_value_fails(tmp_path):
    root = _build_root(tmp_path, sites={"spec/SKILL.md": 'lane: "medium"\n'})
    findings = _checks(check.check_lane_vocabulary(root))
    assert len(findings) == 1
    assert findings[0].file == "spec/SKILL.md" and findings[0].line == 1
    assert "`medium`" in findings[0].message


def test_unknown_lane_value_in_json_and_bare_forms_fails(tmp_path):
    root = _build_root(tmp_path, sites={
        "proceed/SKILL.md": '"lane": "mini"\n',
        "templates/requirement-template.md": "# lane: tiny\n",
    })
    files = sorted(f.file for f in _checks(check.check_lane_vocabulary(root)))
    assert files == ["proceed/SKILL.md", "templates/requirement-template.md"]


def test_unknown_trigger_fails_in_every_form(tmp_path):
    root = _build_root(tmp_path, sites={
        "proceed/phases-lite.md": "trigger=too-big\n",
        "agents/pipeline-runner.md": '"trigger": "hunch"\n',
        "wrapup/SKILL.md": "escalate with trigger `vibes`\n",
    })
    values = sorted(f.message.split("`")[3] for f in _checks(check.check_lane_vocabulary(root)))
    assert values == ["hunch", "too-big", "vibes"]


def test_unknown_actor_and_lane_check_fail(tmp_path):
    root = _build_root(tmp_path, sites={
        "status/SKILL.md": "actor: robot\n",
        "sprint/SKILL.md": "lane_check=maybe\n",
    })
    assert len(_checks(check.check_lane_vocabulary(root))) == 2


def test_known_values_and_placeholders_pass(tmp_path):
    """Benign path: every in-vocabulary form, and placeholders that are not values."""
    text = "\n".join([
        'lane: "lite"', "lane: 'full'", '"lane": "full"', "lane: full",
        "trigger=max-files", "trigger: reversal", '"trigger": "check-error"',
        "with trigger `implementer`", "actor: operator", '"actor": "sprint-runner"',
        "lane_check=escalate",
        # placeholders and structures — not values
        "trigger=<t>", "lane: { type: 'string' }", "`lane_check=` comes first",
        "lane.current: x", "swimlane: wide", "**Lane**: full | lite",
    ]) + "\n"
    root = _build_root(tmp_path, sites={"proceed/phases-lite.md": text})
    assert _checks(check.check_lane_vocabulary(root)) == []


def test_missing_vocabulary_block_is_a_finding(tmp_path):
    root = _build_root(tmp_path, vocab="no block here\n")
    findings = _checks(check.check_lane_vocabulary(root))
    assert len(findings) == 1 and findings[0].file == check.LANE_VOCAB_SITE


def test_empty_vocabulary_block_is_a_finding(tmp_path):
    root = _build_root(tmp_path, vocab="<!-- lane-vocabulary -->\n<!-- /lane-vocabulary -->\n")
    findings = _checks(check.check_lane_vocabulary(root))
    assert len(findings) == 1 and "empty" in findings[0].message


def test_vocabulary_missing_a_set_is_a_finding(tmp_path):
    vocab = VOCAB_BLOCK.replace("- actor: `solo`, `sprint-runner`, `operator`\n", "")
    findings = _checks(check.check_lane_vocabulary(_build_root(tmp_path, vocab=vocab)))
    assert any("`actor` set" in f.message for f in findings)


def test_deleted_vocabulary_file_is_a_finding_while_lite_companion_exists(tmp_path):
    """Deleting lane-check.md alone must not disarm the check."""
    root = _build_root(tmp_path, vocab=None)
    findings = _checks(check.check_lane_vocabulary(root))
    assert any(f.file == check.LANE_VOCAB_SITE and "missing" in f.message for f in findings)


def test_deleted_site_is_a_finding(tmp_path):
    root = _build_root(tmp_path, omit=("status/SKILL.md",))
    findings = _checks(check.check_lane_vocabulary(root))
    assert [f.file for f in findings] == ["status/SKILL.md"]


def test_extra_proceed_companion_is_scanned(tmp_path):
    root = _build_root(tmp_path)
    (root / "proceed" / "phases-9-extra.md").write_text('lane: "huge"\n', encoding="utf-8")
    findings = _checks(check.check_lane_vocabulary(root))
    assert [f.file for f in findings] == ["proceed/phases-9-extra.md"]


def test_registered_in_run(tmp_path):
    root = _build_root(tmp_path, sites={"spec/SKILL.md": 'lane: "medium"\n'})
    findings, _ = check.run(root)
    assert any(f.check == "lane-vocabulary" for f in findings)


# --- the real tree ----------------------------------------------------------

def test_shipped_tree_is_clean():
    assert check.check_lane_vocabulary(REPO_ROOT) == []


def test_shipped_vocabulary_matches_architecture():
    """The block lists exactly the four sets architecture.md defines."""
    text = (REPO_ROOT / check.LANE_VOCAB_SITE).read_text(encoding="utf-8")
    assert check.parse_lane_vocab_block(text) == check.parse_lane_vocab_block(VOCAB_BLOCK)


def test_shipped_sites_actually_carry_lane_values():
    """Not vacuous: the scan finds lane values at the sites, not zero matches."""
    hits = 0
    for rel in check.LANE_SITES:
        for line in (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines():
            for _, pattern in check.LANE_VALUE_PATTERNS:
                hits += len(pattern.findall(line))
    assert hits >= 10


# --- forms added after Phase-5 review ---------------------------------------

def test_uppercase_and_backticked_values_are_read(tmp_path):
    """`lane: Lite` and lane: `medium` are values, not prose to skip."""
    root = _build_root(tmp_path, sites={
        "spec/SKILL.md": "lane: Lite\n",
        "status/SKILL.md": "lane: `medium`\n",
        "sprint/SKILL.md": "actor: `robot`\n",
    })
    values = sorted(f.message.split("`")[3] for f in _checks(check.check_lane_vocabulary(root)))
    assert values == ["Lite", "medium", "robot"]


def test_workflow_comparisons_and_enum_are_read(tmp_path):
    js = "\n".join([
        "if (r.lane === 'lit') {}",
        "lane: { type: 'string', enum: ['lite', 'ful'] },",
    ]) + "\n"
    root = _build_root(tmp_path, sites={"workflows/adlc-sprint.workflow.js": js})
    values = sorted(f.message.split("`")[3] for f in _checks(check.check_lane_vocabulary(root)))
    assert values == ["ful", "lit"]


def test_workflow_known_forms_pass(tmp_path):
    js = "if (r.lane === 'lite') {}\nlane: { type: 'string', enum: ['lite', 'full'] },\n"
    root = _build_root(tmp_path, sites={"workflows/adlc-sprint.workflow.js": js})
    assert _checks(check.check_lane_vocabulary(root)) == []


def test_known_limit_only_first_value_of_a_prose_list_is_read(tmp_path):
    """Accepted limit, pinned so a change to it is deliberate: in `lane: lite|medium`
    only the first token is a value; prose lists of lanes are not parsed."""
    root = _build_root(tmp_path, sites={"spec/SKILL.md": "lane: lite|medium\n"})
    assert _checks(check.check_lane_vocabulary(root)) == []
