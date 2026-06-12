"""Test the sync-surface parity check (REQ-525 / AC4 / BR-4).

`check_sync_surface_parity` parses the `<!-- sync-surfaces: init -->` block from
`init/SKILL.md` and the `<!-- sync-surfaces: template-drift -->` block from
`template-drift/SKILL.md` and reports when `/init`'s vendored-surface copy list
and `/template-drift`'s checked-surface list diverge. The check is per-root and
degrades to zero findings (no crash) outside the toolkit checkout — same posture
as `check_agent_model_drift`.

Tests exercise the parser and the check against synthetic tmp roots, plus a
parity assertion against the REAL toolkit tree (the shipped marker blocks must
agree).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_DIR = REPO_ROOT / "tools" / "lint-skills"

sys.path.insert(0, str(LINT_DIR))
import check  # noqa: E402


def _block(which: str, surfaces: list[str]) -> str:
    body = "\n".join(f"- `{s}` — copy command here" for s in surfaces)
    return f"<!-- sync-surfaces: {which} -->\n{body}\n<!-- /sync-surfaces -->\n"


def _build_root(tmp_path: Path, init_surfaces, td_surfaces) -> Path:
    """tmp root with init/SKILL.md + template-drift/SKILL.md, each with a marker block.

    Pass ``None`` for a surface list to OMIT the marker block entirely (tests the
    graceful-degradation path).
    """
    (tmp_path / "init").mkdir(parents=True)
    (tmp_path / "template-drift").mkdir(parents=True)
    init_body = "---\nname: init\n---\n# init\n"
    if init_surfaces is not None:
        init_body += "\n" + _block("init", init_surfaces)
    td_body = "---\nname: template-drift\n---\n# td\n"
    if td_surfaces is not None:
        td_body += "\n" + _block("template-drift", td_surfaces)
    (tmp_path / "init" / "SKILL.md").write_text(init_body, encoding="utf-8")
    (tmp_path / "template-drift" / "SKILL.md").write_text(td_body, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Parser unit tests
# ---------------------------------------------------------------------------

def test_parse_returns_surface_set():
    text = "intro\n" + _block("init", ["ethos", "templates"]) + "\ntrailer\n"
    assert check.parse_sync_surface_block(text, "init") == {"ethos", "templates"}


def test_parse_returns_none_when_block_absent():
    text = "# a skill with no sync-surfaces marker\n"
    assert check.parse_sync_surface_block(text, "init") is None


def test_parse_distinguishes_which():
    # An init block is present but we ask for template-drift -> None.
    text = _block("init", ["ethos"])
    assert check.parse_sync_surface_block(text, "template-drift") is None


def test_parse_empty_block_is_empty_set_not_none():
    text = "<!-- sync-surfaces: init -->\n<!-- /sync-surfaces -->\n"
    assert check.parse_sync_surface_block(text, "init") == set()


def test_parse_ignores_backticked_prose_mention_before_real_block():
    # A cross-reference PROSE mention of the SAME block's marker (inside backticks,
    # mid-sentence) must NOT be mistaken for the real block opener. The real block
    # starts at column 0; the prose mention is indented inside a backtick. Without
    # the start-of-line anchor the parser would latch onto the prose line and return
    # an empty/wrong set. This guards that regression (the real markers in the shipped
    # SKILL.md files cross-reference each other's markers in prose).
    text = (
        "See the `<!-- sync-surfaces: init -->` list for the copy targets.\n"
        "\n"
        "<!-- sync-surfaces: init -->\n"
        "- `ethos` — copy\n"
        "- `templates` — copy\n"
        "<!-- /sync-surfaces -->\n"
    )
    assert check.parse_sync_surface_block(text, "init") == {"ethos", "templates"}


# ---------------------------------------------------------------------------
# check_sync_surface_parity behavior
# ---------------------------------------------------------------------------

def test_parity_holds_when_lists_agree(tmp_path):
    # init copies four; template-drift checks those four + the td-only landmine.
    root = _build_root(
        tmp_path,
        ["ethos", "templates", "partials", "workflow-runtime"],
        ["ethos", "templates", "partials", "workflow-runtime", "workflow-test-landmine"],
    )
    assert check.check_sync_surface_parity(root) == []


def test_finding_when_init_surface_unchecked_by_template_drift(tmp_path):
    # /init copies `ethos` but /template-drift forgot to check it (Rule 2).
    root = _build_root(
        tmp_path,
        ["ethos", "templates", "partials", "workflow-runtime"],
        ["templates", "partials", "workflow-runtime", "workflow-test-landmine"],
    )
    findings = check.check_sync_surface_parity(root)
    assert any(
        f.check == "sync-surface-parity" and "ethos" in f.message
        and f.file == "template-drift/SKILL.md"
        for f in findings
    ), findings


def test_finding_when_init_missing_a_checked_copied_surface(tmp_path):
    # /template-drift checks `partials` (an init-copied surface) but /init's list
    # dropped it (Rule 3) -> divergence reported against init/SKILL.md.
    root = _build_root(
        tmp_path,
        ["ethos", "templates", "workflow-runtime"],
        ["ethos", "templates", "partials", "workflow-runtime", "workflow-test-landmine"],
    )
    findings = check.check_sync_surface_parity(root)
    assert any(
        f.check == "sync-surface-parity" and "partials" in f.message
        and f.file == "init/SKILL.md"
        for f in findings
    ), findings


def test_landmine_asymmetry_is_allowed(tmp_path):
    # workflow-test-landmine is template-drift-only and must NOT be flagged as a
    # missing /init entry.
    root = _build_root(
        tmp_path,
        ["ethos", "templates", "partials", "workflow-runtime"],
        ["ethos", "templates", "partials", "workflow-runtime", "workflow-test-landmine"],
    )
    findings = check.check_sync_surface_parity(root)
    assert not any("workflow-test-landmine" in f.message for f in findings), findings


def test_unknown_surface_name_is_flagged(tmp_path):
    # A typo'd / un-enumerated surface name in either block is a finding (Rule 1).
    root = _build_root(
        tmp_path,
        ["ethos", "templates", "partials", "workflow-runtime", "bogus-surface"],
        ["ethos", "templates", "partials", "workflow-runtime", "workflow-test-landmine"],
    )
    findings = check.check_sync_surface_parity(root)
    assert any(
        f.check == "sync-surface-parity" and "bogus-surface" in f.message
        for f in findings
    ), findings


def test_degrades_when_skill_absent(tmp_path):
    # A root with no init/template-drift SKILL.md -> zero findings, no crash.
    (tmp_path / "unrelated").mkdir()
    assert check.check_sync_surface_parity(tmp_path) == []


def test_degrades_when_marker_block_absent(tmp_path):
    # SKILL.md files exist but neither has a marker block -> degrade silently.
    root = _build_root(tmp_path, None, None)
    assert check.check_sync_surface_parity(root) == []


# ---------------------------------------------------------------------------
# Parity against the REAL shipped toolkit tree
# ---------------------------------------------------------------------------

def test_real_toolkit_tree_parity_holds():
    # The shipped init/SKILL.md and template-drift/SKILL.md marker blocks must agree.
    findings = check.check_sync_surface_parity(REPO_ROOT)
    assert findings == [], [f.format() for f in findings]
