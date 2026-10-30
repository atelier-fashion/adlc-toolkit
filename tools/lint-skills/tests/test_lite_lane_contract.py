"""Structural contract for the REQ-652 lite lane's skill text.

`lane-vocabulary` proves every lane value is in its closed set. It cannot prove
the instructions say the right things in the right places, which is what most of
REQ-652's structural-check obligations claim. These tests pin the load-bearing
sentences, so deleting one is a red test rather than a silent drift: the halt
count, every lane-check call point (AC-16), absent-means-full in every reader
(BR-12 / AC-8), the halting and non-halting actors (BR-8 / AC-6), the fresh
retrieval set handed to the review (AC-9), the PR body's Lane section (BR-13 /
AC-10), the escalation lesson (BR-14 / AC-11) and the status columns (BR-15 /
AC-12).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_halt_count_is_four_everywhere_it_is_stated():
    text = _read("proceed/SKILL.md")
    assert "exactly **four** legitimate halt points" in text
    assert "4. **The lane check fails on a forced-lite REQ in a solo run**" in text
    for rel in ("proceed/SKILL.md", "proceed/phases-lite.md", "proceed/phases-6-8-ship.md",
                "agents/pipeline-runner.md"):
        assert not re.search(r"\bthree(-halt| legitimate)", _read(rel)), rel


def test_lane_check_runs_at_every_call_point():
    """AC-16: after the review fixes, after Phase 7 commits, before the merge,
    and after a Phase 8 conflict-resolution commit — and each companion points
    at the one fence that runs it."""
    lite = _read("proceed/phases-lite.md")
    assert lite.count("adlc_lane_check ") == 1, "one fence runs the check"
    for when in ("Phase 5, after the review fixes are committed and pushed",
                 "End of Phase 7", "Phase 8, immediately before the trial-merge gate",
                 "Phase 8, after any conflict-resolution commit"):
        assert when in lite, when
    ship = _read("proceed/phases-6-8-ship.md")
    assert ship.count('"The lane check"') >= 2, "Phase 7 and Phase 8 point at the fence"
    skill = _read("proceed/SKILL.md")
    assert "re-run the lane check before leaving it" in skill
    assert "re-run the lane check immediately before the pre-merge trial-merge gate" in skill


def test_lane_check_fence_guards_run_before_the_partial_is_sourced():
    lite = _read("proceed/phases-lite.md")
    fence = lite[lite.index("wt='<worktree>'"):]
    fence = fence[:fence.index("```")]
    source = fence.index(". .adlc/partials/lane-check.sh")
    for guard in ("pwd -P", "status --porcelain", "fetch origin", 'rev-parse "origin/$br"', "':(icase).adlc/partials'"):
        assert fence.index(guard) < source, guard


def test_absent_lane_means_full_in_every_reader():
    for rel, needle in (
        ("spec/SKILL.md", "A missing `lane` means `full`"),
        ("proceed/SKILL.md", "A spec with no `lane` key is on the **full** lane"),
        ("proceed/phases-lite.md", "A missing `lane` key\n     means `full`"),
        ("status/SKILL.md", "A missing `lane` means `full`"),
        ("wrapup/SKILL.md", "a missing `lane` means `full`"),
        ("agents/pipeline-runner.md", "A missing `lane` means `full`"),
        ("workflows/adlc-sprint.workflow.js", "absent means"),
    ):
        assert needle in _read(rel), rel


def test_forced_lite_halts_solo_and_escalates_unattended():
    lite = _read("proceed/phases-lite.md")
    assert "legitimate halt #4" in lite
    assert "main conversation mode" in lite and "**subagent mode**" in lite
    assert "never ends\n     `blocked` on this" in lite
    assert "`sprint-runner` in subagent mode" in lite
    runner = _read("agents/pipeline-runner.md")
    assert "**never** ends your run as `blocked`" in runner


def test_check_error_is_never_overridable():
    lite = _read("proceed/phases-lite.md")
    assert "If no failing trigger is `check-error`" in lite
    assert "an error is never overridable" in lite
    assert '"pairs": [...]' in lite


def test_lite_review_gets_the_fresh_retrieval_set():
    lite = _read("proceed/phases-lite.md")
    assert "**fresh retrieval set** from\n     Phase 4" in lite
    assert "trigger `reversal`" in lite and "trigger `implementer`" in lite


def test_lite_pr_body_carries_the_lane():
    lite = _read("proceed/phases-lite.md")
    body = lite[lite.index("Lite PR body:"):]
    assert "## Lane" in body and "[lane_reason]" in body
    ship = _read("proceed/phases-6-8-ship.md")
    assert "`## Lane` section" in ship


def test_wrapup_writes_the_escalation_lesson_and_only_then():
    text = _read("wrapup/SKILL.md")
    section = text[text.index("#### Lane escalations (REQ-652)"):text.index("#### Convention Updates")]
    assert "**No escalation, no lesson.**" in section
    assert "`kind: process`" in section and "`lane_reason`" in section
    assert "trigger `check-error`" in section


def test_status_shows_lane_and_escalations():
    text = _read("status/SKILL.md")
    assert "| ID | Title | Status | Lane | Escalated | Tasks | Progress |" in text
    assert "| REQ | Primary | Branch | Lane |" in text
    assert "#### Escalations" in text and "No recorded lane escalations." in text


def test_every_consumer_branches_on_every_review_section():
    """The lite-reviewer's sections are acted on wherever the review is run."""
    for rel in ("proceed/phases-lite.md", "proceed/SKILL.md", "agents/pipeline-runner.md"):
        text = _read(rel)
        for section in ("reversals:", "out_of_lane:", "questions:", "coverage"):
            assert section in text, f"{rel} does not act on `{section}`"


def test_override_shape_is_documented_in_the_state_schema():
    text = _read("proceed/phases-state.md")  # REQ-661: the state schema moved whole
    assert "`{ at, phase, sha, triggers, pairs, actor }`" in text
