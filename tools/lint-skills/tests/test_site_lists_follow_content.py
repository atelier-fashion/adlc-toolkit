"""REQ-661 BR-10 / AC-9 — per-root site lists follow the content into companions.

Each per-root check that names its sites by path (`retrieval-status-parity`,
`lane-vocabulary`, `lesson-rules-parity`) or keys on a skill's name
(`lesson-check-order`, `lesson-question-coverage`) must, after a split, still
fire on its known-bad input where the block now lives, and must say so — never
pass silently — when a listed site is missing or its block moved within the
unit (LESSON-019). Every negative assertion sits beside a positive control
(LESSON-602).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_DIR = REPO_ROOT / "tools" / "lint-skills"
CHECK_PY = LINT_DIR / "check.py"
LCO = Path(__file__).resolve().parent / "fixtures" / "lesson-check-order"

sys.path.insert(0, str(LINT_DIR))
import check  # noqa: E402


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK_PY), "--root", str(root)],
                          capture_output=True, text=True, check=False)


def _lco(result) -> list[tuple[str, int, str]]:
    out = []
    for ln in result.stdout.splitlines():
        if " lesson-check-order: " not in ln:
            continue
        file, line, rest = ln.split(":", 2)
        out.append((file, int(line), rest.split(" lesson-check-order: ", 1)[1].split(":", 1)[0]))
    return out


EXCLUDE = "<!-- retrieval-status: spec-exclude -->\n- `draft` — not prior art\n<!-- /retrieval-status -->\n"


def _write_block(status: str) -> str:
    return f"<!-- retrieval-status: lifecycle-write -->\n- `{status}` — written here\n<!-- /retrieval-status -->\n"


# --- retrieval-status-parity -------------------------------------------------

def test_retrieval_writer_in_a_companion_still_fires(tmp_path, monkeypatch):
    """Known-bad input in the post-split layout: a writer site that is a
    companion writes a status the reader excludes."""
    monkeypatch.setattr(check, "LIFECYCLE_WRITE_SITES", ("wrapup/references/status.md",))
    _write(tmp_path, "spec/SKILL.md", "# spec\n\n" + EXCLUDE)
    _write(tmp_path, "wrapup/SKILL.md", "# wrapup\n\nRead `wrapup/references/status.md`.\n")
    _write(tmp_path, "wrapup/references/status.md", "# status\n\n" + _write_block("draft"))
    findings = check.check_retrieval_status_parity(tmp_path)
    assert [(f.file, "`draft`" in f.message) for f in findings] == [("spec/SKILL.md", True)]
    # Benign: the same writer writing `complete` is clean.
    _write(tmp_path, "wrapup/references/status.md", "# status\n\n" + _write_block("complete"))
    assert check.check_retrieval_status_parity(tmp_path) == []


def test_retrieval_reader_in_a_companion_still_fires(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "RETRIEVAL_READER_SITE", "spec/references/retrieval.md")
    monkeypatch.setattr(check, "LIFECYCLE_WRITE_SITES", ("architect/SKILL.md",))
    _write(tmp_path, "spec/SKILL.md", "# spec\n")
    _write(tmp_path, "spec/references/retrieval.md", "# retrieval\n\n" + EXCLUDE)
    _write(tmp_path, "architect/SKILL.md", "# architect\n\n" + _write_block("draft"))
    findings = check.check_retrieval_status_parity(tmp_path)
    assert [f.file for f in findings] == ["spec/references/retrieval.md"]
    assert "architect/SKILL.md" in findings[0].message


def test_retrieval_listed_sites_missing_are_named(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "RETRIEVAL_READER_SITE", "spec/references/gone.md")
    _write(tmp_path, "spec/SKILL.md", "# spec\n\n" + EXCLUDE)
    findings = check.check_retrieval_status_parity(tmp_path)
    assert [f.file for f in findings] == ["spec/references/gone.md"]
    assert "RETRIEVAL_READER_SITE" in findings[0].message
    monkeypatch.setattr(check, "RETRIEVAL_READER_SITE", "spec/SKILL.md")
    monkeypatch.setattr(check, "LIFECYCLE_WRITE_SITES", ("proceed/phase-0-gone.md",))
    findings = check.check_retrieval_status_parity(tmp_path)
    assert [f.file for f in findings] == ["proceed/phase-0-gone.md"]
    assert "LIFECYCLE_WRITE_SITES" in findings[0].message


def test_retrieval_blocks_moved_within_the_unit_are_named(tmp_path, monkeypatch):
    """A block moved to a sibling file while the list still names the old site
    is reported where it went, not as a silent pass or a vague 'no block'."""
    monkeypatch.setattr(check, "LIFECYCLE_WRITE_SITES", ("proceed/SKILL.md",))
    _write(tmp_path, "spec/SKILL.md", "# spec\n")
    _write(tmp_path, "spec/references/retrieval.md", EXCLUDE)
    findings = check.check_retrieval_status_parity(tmp_path)
    assert [f.file for f in findings] == ["spec/SKILL.md"]
    assert "spec/references/retrieval.md" in findings[0].message
    assert "RETRIEVAL_READER_SITE" in findings[0].message
    _write(tmp_path, "spec/SKILL.md", "# spec\n\n" + EXCLUDE)
    _write(tmp_path, "proceed/SKILL.md", "# proceed\n")
    _write(tmp_path, "proceed/phase-0-setup.md", _write_block("approved"))
    findings = check.check_retrieval_status_parity(tmp_path)
    assert [f.file for f in findings] == ["proceed/SKILL.md"]
    assert "proceed/phase-0-setup.md" in findings[0].message
    assert "LIFECYCLE_WRITE_SITES" in findings[0].message


def test_retrieval_stays_inert_outside_the_toolkit(tmp_path):
    """The gate is unchanged: no spec/SKILL.md, no finding, even with sites missing."""
    _write(tmp_path, "other/SKILL.md", "# other\n")
    assert check.check_retrieval_status_parity(tmp_path) == []


def test_shipped_write_sites_carry_their_blocks():
    """Positive control on the real tree: every listed site holds its block."""
    for rel in check.LIFECYCLE_WRITE_SITES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert check.parse_retrieval_status_block(text, "lifecycle-write"), rel
    reader = (REPO_ROOT / check.RETRIEVAL_READER_SITE).read_text(encoding="utf-8")
    assert check.parse_retrieval_status_block(reader, "spec-exclude")


# --- lane-vocabulary ---------------------------------------------------------

VOCAB = ("<!-- lane-vocabulary -->\n- lane: `lite`, `full`\n- trigger: `reversal`\n"
         "- actor: `solo`\n- lane_check: `pass`\n<!-- /lane-vocabulary -->\n")


def test_lane_value_in_a_references_companion_fires(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "LANE_SITES", ("spec/SKILL.md",))
    _write(tmp_path, "partials/lane-check.md", VOCAB)
    _write(tmp_path, "spec/SKILL.md", '# spec\n\nWrite `lane: "full"`.\n')
    _write(tmp_path, "spec/references/triage.md", '# triage\n\nWrite `lane: "medium"`.\n')
    findings = check.check_lane_vocabulary(tmp_path)
    assert [(f.file, f.line) for f in findings] == [("spec/references/triage.md", 3)]


def test_lane_listed_site_missing_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "LANE_SITES", ("spec/SKILL.md", "proceed/phase-0-setup.md"))
    _write(tmp_path, "partials/lane-check.md", VOCAB)
    _write(tmp_path, "spec/SKILL.md", '# spec\n\nWrite `lane: "lite"`.\n')
    findings = check.check_lane_vocabulary(tmp_path)
    assert [f.file for f in findings] == ["proceed/phase-0-setup.md"]
    assert "LANE_SITES" in findings[0].message


# --- lesson-rules-parity -----------------------------------------------------

def _rules(text: str) -> str:
    start = text.index("<!-- lesson-capture-rules -->")
    end = text.index("<!-- /lesson-capture-rules -->") + len("<!-- /lesson-capture-rules -->\n")
    return text[start:end]


def test_rules_parity_reads_a_companion_site(tmp_path, monkeypatch):
    """Known-bad input in the post-split layout: /wrapup's block lives in a
    companion the list names, and differs from /bugfix's."""
    monkeypatch.setattr(check, "LESSON_RULES_PARITY_SITES",
                        ("wrapup/references/capture.md", "bugfix/SKILL.md"))
    good = (LCO / "wrapup-good.md").read_text(encoding="utf-8")
    _write(tmp_path, "wrapup/SKILL.md", "# wrapup\n")
    _write(tmp_path, "wrapup/references/capture.md", good)
    _write(tmp_path, "bugfix/SKILL.md", (LCO / "bugfix-rules-mismatch.md").read_text(encoding="utf-8"))
    findings = check.check_lesson_rules_parity(tmp_path)
    assert [f.file for f in findings] == ["bugfix/SKILL.md"]
    assert "rules-block-mismatch" in findings[0].message
    assert "wrapup/references/capture.md" in findings[0].message
    # Benign: byte-equal blocks are clean.
    _write(tmp_path, "bugfix/SKILL.md", "# bugfix\n\n" + _rules(good))
    assert check.check_lesson_rules_parity(tmp_path) == []


def test_rules_parity_listed_site_missing_is_named_once_armed(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "LESSON_RULES_PARITY_SITES",
                        ("wrapup/references/capture.md", "bugfix/SKILL.md"))
    good = (LCO / "wrapup-good.md").read_text(encoding="utf-8")
    _write(tmp_path, "wrapup/SKILL.md", "# wrapup\n")
    _write(tmp_path, "bugfix/SKILL.md", "# bugfix\n\n" + _rules(good))
    findings = check.check_lesson_rules_parity(tmp_path)
    assert [f.file for f in findings] == ["wrapup/references/capture.md"]
    assert "rules-block-site-missing" in findings[0].message
    assert "LESSON_RULES_PARITY_SITES" in findings[0].message
    # Unarmed (no bugfix/SKILL.md): inert, as before.
    (tmp_path / "bugfix" / "SKILL.md").unlink()
    assert check.check_lesson_rules_parity(tmp_path) == []


def test_rules_parity_block_moved_within_the_unit_is_named(tmp_path):
    good = (LCO / "wrapup-good.md").read_text(encoding="utf-8")
    _write(tmp_path, "wrapup/SKILL.md", "# wrapup\n\nRead `wrapup/references/capture.md`.\n")
    _write(tmp_path, "wrapup/references/capture.md", good)
    _write(tmp_path, "bugfix/SKILL.md", "# bugfix\n\n" + _rules(good))
    findings = check.check_lesson_rules_parity(tmp_path)
    assert [f.file for f in findings] == ["wrapup/SKILL.md"]
    assert "rules-block-site-moved" in findings[0].message
    assert "wrapup/references/capture.md" in findings[0].message


# --- lesson-check-order and lesson-question-coverage on a companion ----------

def _wrapup_unit(tmp_path: Path, companion: str, skill: str = "# wrapup\n\nRead the companion.\n") -> Path:
    _write(tmp_path, "wrapup/SKILL.md", skill)
    _write(tmp_path, "wrapup/references/capture.md", companion)
    shutil.copyfile(LCO / "bugfix-good.md", tmp_path / "bugfix-good.md")
    _write(tmp_path, "bugfix/SKILL.md", (LCO / "bugfix-good.md").read_text(encoding="utf-8"))
    (tmp_path / "bugfix-good.md").unlink()
    return tmp_path


def test_capture_step_in_a_companion_is_held_to_the_contract(tmp_path):
    """The good shape moved whole into a companion is clean, and SKILL.md is
    owed nothing; the reordered shape in a companion fires there. With the
    shipped LESSON_RULES_PARITY_SITES still naming `wrapup/SKILL.md`, the
    parity check reports where the block went (BR-10) instead of passing."""
    good = (LCO / "wrapup-good.md").read_text(encoding="utf-8")
    result = _run(_wrapup_unit(tmp_path, good))
    assert _lco(result) == [("wrapup/SKILL.md", 1, "rules-block-site-moved")], result.stdout
    bad = (LCO / "bugfix-recheck-before-check.md").read_text(encoding="utf-8")
    other = tmp_path / "bad"
    _write(other, "bugfix/SKILL.md", "# bugfix\n\nRead the companion.\n")
    _write(other, "bugfix/references/capture.md", bad)
    _write(other, "wrapup/SKILL.md", good)
    hits = _lco(_run(other))
    assert [(f, i) for f, _n, i in hits] == [("bugfix/references/capture.md", "recheck-before-check"),
                                             ("bugfix/SKILL.md", "rules-block-site-moved")], hits


def test_question_coverage_runs_on_a_wrapup_companion(tmp_path):
    missing = (LCO / "wrapup-question-missing-rule.md").read_text(encoding="utf-8")
    hits = _lco(_run(_wrapup_unit(tmp_path, missing)))
    assert [(f, i) for f, _n, i in hits if i != "rules-block-site-moved"] == [
        ("wrapup/references/capture.md", "rules-line-not-in-question")], hits


def test_capture_step_split_across_files(tmp_path):
    """BR-5: the write point in SKILL.md and the fences in a companion are one
    step split in two — a finding on the second file."""
    good = (LCO / "wrapup-good.md").read_text(encoding="utf-8")
    head, tail = good.split("**Write and check**", 1)
    result = _run(_wrapup_unit(tmp_path, "**Write and check**" + tail, skill=head))
    ids = [(f, i) for f, _n, i in _lco(result)]
    assert ("wrapup/references/capture.md", "capture-step-split") in ids, result.stdout


def test_lesson_gate_keys_on_the_unit_name():
    assert check._lesson_skill("wrapup/references/capture.md") == "wrapup"
    assert check._lesson_skill("bugfix/SKILL.md") == "bugfix"
    assert check._lesson_skill("spec/references/x.md") is None
    assert check._lesson_skill("references/SKILL.md") is None


def test_shipped_lesson_steps_are_whole():
    """AC-10 on the real tree: in each lesson skill one file holds the three
    constructs, in order."""
    for skill in check.LESSON_CHECK_ORDER_SKILLS:
        unit = next(u for u in check.find_skill_units(REPO_ROOT) if u.name == skill)
        files = [(p.relative_to(REPO_ROOT).as_posix(), p.read_text(encoding="utf-8"))
                 for p in [unit.skill_md, *unit.companions]]
        assert check.check_lesson_units(skill, files) == []
        holders = [rel for rel, text in files if check._lesson_construct_line(text) is not None]
        assert len(holders) == 1, holders


def test_moved_within_unit_never_reads_outside_the_root(tmp_path):
    """The unit a site belongs to keeps the symlink-escape guard: a SKILL.md that
    points outside the scan root is not read for the moved block, while an
    in-root companion holding it is (the positive control)."""
    outside = tmp_path / "outside"
    _write(outside, "SKILL.md", EXCLUDE)
    root = tmp_path / "root"
    _write(root, "spec/references/retrieval.md", "# no block here\n")
    (root / "spec" / "SKILL.md").symlink_to(outside / "SKILL.md")
    assert check.moved_within_unit(root, "spec/references/retrieval.md",
                                   lambda t: "spec-exclude" in t) is None
    _write(root, "spec/references/other.md", EXCLUDE)
    assert check.moved_within_unit(root, "spec/references/retrieval.md",
                                   lambda t: "spec-exclude" in t) == "spec/references/other.md"
