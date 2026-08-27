"""Test the retrieval-status parity check (BUG-194).

`check_retrieval_status_parity` compares the REQ `status:` values the lifecycle
skills WRITE (`architect/SKILL.md`, `wrapup/SKILL.md`,
`proceed/phases-6-8-ship.md`) against the values `/spec` Step 1.6 EXCLUDES from
spec-corpus retrieval (`spec/SKILL.md`). Before BUG-194 the reader used an
allowlist of `approved` | `in-progress` | `deployed` while the writers emitted
`approved` and `complete`, so spec retrieval returned ~0 of 543 specs
ecosystem-wide and reported it as a cold start.

Tests exercise the parser and the check against synthetic tmp roots, plus a
regression assertion against the REAL toolkit tree (the shipped blocks must not
contradict each other) and an explicit reconstruction of the pre-fix state to
prove the guard would have caught the original defect.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_DIR = REPO_ROOT / "tools" / "lint-skills"

sys.path.insert(0, str(LINT_DIR))
import check  # noqa: E402


def _block(which: str, statuses: list[str]) -> str:
    body = "\n".join(f"- `{s}` — rationale here" for s in statuses)
    return f"<!-- retrieval-status: {which} -->\n{body}\n<!-- /retrieval-status -->\n"


def _build_root(tmp_path: Path, excluded, written) -> Path:
    """tmp root with spec/SKILL.md plus every lifecycle write site.

    ``excluded``: statuses for the spec-exclude block, or ``None`` to omit the
    block entirely (the pre-BUG-194 / non-toolkit degradation path).
    ``written``: mapping of relative site path -> list of statuses, or ``None``
    for that site to omit its block. A site absent from the mapping is not
    created at all.
    """
    (tmp_path / "spec").mkdir(parents=True)
    spec_body = "---\nname: spec\n---\n# spec\n"
    if excluded is not None:
        spec_body += "\n" + _block("spec-exclude", excluded)
    (tmp_path / "spec" / "SKILL.md").write_text(spec_body, encoding="utf-8")

    for rel, statuses in (written or {}).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "# write site\n"
        if statuses is not None:
            body += "\n" + _block("lifecycle-write", statuses)
        path.write_text(body, encoding="utf-8")
    return tmp_path


ALL_SITES_CLEAN = {
    "architect/SKILL.md": ["approved"],
    "wrapup/SKILL.md": ["complete"],
    "proceed/phases-6-8-ship.md": ["complete"],
}


# ---------------------------------------------------------------------------
# Parser unit tests
# ---------------------------------------------------------------------------

def test_parse_returns_status_set():
    text = "intro\n" + _block("spec-exclude", ["draft", "superseded"]) + "\ntrailer\n"
    assert check.parse_retrieval_status_block(text, "spec-exclude") == {
        "draft",
        "superseded",
    }


def test_parse_returns_none_when_block_absent():
    text = "# a skill with no retrieval-status marker\n"
    assert check.parse_retrieval_status_block(text, "spec-exclude") is None


def test_parse_distinguishes_absent_from_empty():
    """None (absent) and set() (present-but-empty) are different outcomes."""
    text = "<!-- retrieval-status: spec-exclude -->\n<!-- /retrieval-status -->\n"
    assert check.parse_retrieval_status_block(text, "spec-exclude") == set()


def test_parse_ignores_other_which_values():
    text = _block("lifecycle-write", ["complete"])
    assert check.parse_retrieval_status_block(text, "spec-exclude") is None
    assert check.parse_retrieval_status_block(text, "lifecycle-write") == {"complete"}


def test_parse_unions_multiple_blocks_of_same_which():
    """A file may write a status from more than one step; the second must add, not shadow."""
    text = _block("lifecycle-write", ["approved"]) + "\nprose\n" + _block(
        "lifecycle-write", ["complete"]
    )
    assert check.parse_retrieval_status_block(text, "lifecycle-write") == {
        "approved",
        "complete",
    }


def test_parse_ignores_mid_sentence_prose_mention():
    """A backticked cross-reference must not be mistaken for the block opener."""
    text = (
        "see the `<!-- retrieval-status: spec-exclude -->` block for the list\n"
        + _block("spec-exclude", ["draft"])
    )
    assert check.parse_retrieval_status_block(text, "spec-exclude") == {"draft"}


# ---------------------------------------------------------------------------
# Check behaviour — graceful degradation
# ---------------------------------------------------------------------------

def test_no_findings_outside_toolkit_checkout(tmp_path):
    """No spec/SKILL.md at all → inert, never a crash."""
    assert check.check_retrieval_status_parity(tmp_path) == []


def test_no_findings_when_exclude_block_absent(tmp_path):
    """Pre-BUG-194 checkout: reader has no marker → degrade silently, no false red."""
    root = _build_root(tmp_path, None, ALL_SITES_CLEAN)
    assert check.check_retrieval_status_parity(root) == []


def test_clean_tree_has_no_findings(tmp_path):
    root = _build_root(tmp_path, ["draft", "superseded", "cancelled"], ALL_SITES_CLEAN)
    assert check.check_retrieval_status_parity(root) == []


# ---------------------------------------------------------------------------
# Check behaviour — the BUG-194 invariant
# ---------------------------------------------------------------------------

def test_written_status_in_exclusion_list_is_flagged(tmp_path):
    """The core defect: `/wrapup` writes `complete`, `/spec` excludes it."""
    root = _build_root(tmp_path, ["draft", "complete"], ALL_SITES_CLEAN)
    findings = check.check_retrieval_status_parity(root)
    assert findings, "excluding a written status must be a finding"
    assert all(f.check == "retrieval-status-parity" for f in findings)
    msgs = " ".join(f.message for f in findings)
    assert "`complete`" in msgs
    assert "wrapup/SKILL.md" in msgs
    assert "proceed/phases-6-8-ship.md" in msgs
    # Reported against the reader — that is the file whose list must change.
    assert all(f.file == "spec/SKILL.md" for f in findings)


def test_pre_bug194_allowlist_shape_is_caught(tmp_path):
    """Reconstruct the original defect: the old allowlist as its exclusion complement.

    The shipped filter admitted `approved` | `in-progress` | `deployed`, i.e. it
    excluded `complete` (and `done`, `completed`, ...). Expressed as an exclusion
    list, that is what the guard must reject.
    """
    root = _build_root(
        tmp_path,
        ["draft", "complete", "done", "completed", "superseded", "cancelled"],
        ALL_SITES_CLEAN,
    )
    findings = check.check_retrieval_status_parity(root)
    flagged = {f.message.split("`")[1] for f in findings}
    assert "complete" in flagged


def test_approved_only_overlap_is_still_flagged(tmp_path):
    """Excluding `approved` alone (the /architect write) is equally a finding."""
    root = _build_root(tmp_path, ["draft", "approved"], ALL_SITES_CLEAN)
    findings = check.check_retrieval_status_parity(root)
    assert any("architect/SKILL.md" in f.message for f in findings)


# ---------------------------------------------------------------------------
# Check behaviour — anti-rot rules (LESSON-019 #1)
# ---------------------------------------------------------------------------

def test_missing_write_site_declaration_is_flagged(tmp_path):
    """Deleting a declaration must fail, not silently disarm the guard."""
    sites = dict(ALL_SITES_CLEAN)
    sites["wrapup/SKILL.md"] = None  # file exists, no marker block
    root = _build_root(tmp_path, ["draft"], sites)
    findings = check.check_retrieval_status_parity(root)
    assert any(
        f.file == "wrapup/SKILL.md" and "declares no" in f.message for f in findings
    )


def test_missing_write_site_file_is_flagged(tmp_path):
    """A relocated write site must fail loudly so the registry is updated with it."""
    sites = {k: v for k, v in ALL_SITES_CLEAN.items() if k != "proceed/phases-6-8-ship.md"}
    root = _build_root(tmp_path, ["draft"], sites)
    findings = check.check_retrieval_status_parity(root)
    assert any(
        f.file == "proceed/phases-6-8-ship.md" and "is missing" in f.message
        for f in findings
    )


def test_empty_exclusion_block_is_flagged(tmp_path):
    """A gutted filter would admit `draft` and `superseded` specs as prior art."""
    root = _build_root(tmp_path, [], ALL_SITES_CLEAN)
    findings = check.check_retrieval_status_parity(root)
    assert any("present but empty" in f.message for f in findings)


def test_empty_write_site_block_is_flagged(tmp_path):
    sites = dict(ALL_SITES_CLEAN)
    sites["architect/SKILL.md"] = []
    root = _build_root(tmp_path, ["draft"], sites)
    findings = check.check_retrieval_status_parity(root)
    assert any(
        f.file == "architect/SKILL.md" and "present but empty" in f.message
        for f in findings
    )


# ---------------------------------------------------------------------------
# Regression assertion against the REAL toolkit tree
# ---------------------------------------------------------------------------

def test_shipped_toolkit_tree_is_clean():
    """The shipped blocks must not contradict each other."""
    assert check.check_retrieval_status_parity(REPO_ROOT) == []


def test_shipped_spec_excludes_no_terminal_status():
    """Belt-and-braces: the shipped exclusion list must not name a shipped-work status."""
    excluded = check.parse_retrieval_status_block(
        (REPO_ROOT / "spec" / "SKILL.md").read_text(encoding="utf-8"), "spec-exclude"
    )
    assert excluded is not None, "spec/SKILL.md must carry the spec-exclude block"
    # `complete` is what /wrapup and /proceed write; `done`/`completed`/`deployed`
    # are the consumer-repo synonyms surveyed in BUG-194.
    for status in ("complete", "done", "completed", "deployed", "approved", "in-progress"):
        assert status not in excluded, f"`{status}` must remain retrievable (BUG-194)"


def test_shipped_write_sites_all_declare():
    for rel in check.LIFECYCLE_WRITE_SITES:
        path = REPO_ROOT / rel
        assert path.is_file(), f"{rel} missing — update LIFECYCLE_WRITE_SITES"
        written = check.parse_retrieval_status_block(
            path.read_text(encoding="utf-8"), "lifecycle-write"
        )
        assert written, f"{rel} must declare the status it writes"
