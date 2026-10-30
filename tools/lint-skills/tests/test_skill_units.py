"""REQ-661 — skill units: the companion walk, the unit scope and the two new checks.

A skill unit is a ``SKILL.md`` and its companions (``<skill>/references/*.md``,
and ``proceed/phase*.md`` for ``/proceed``). Content moved into a companion must
stay under every check that guarded it in ``SKILL.md`` (LESSON-019), so each
per-file check is proven here on a companion in both layouts, and each test that
asserts a finding is absent also asserts a positive control in the same run
(LESSON-602). The linter runs through its CLI, as in ``test_check.py``.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_DIR = REPO_ROOT / "tools" / "lint-skills"
CHECK_PY = LINT_DIR / "check.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(LINT_DIR))
import check  # noqa: E402

CLEAN = (FIXTURES / "clean.md").read_text(encoding="utf-8")


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK_PY), "--root", str(root)],
                          capture_output=True, text=True, check=False)


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _hits(result: subprocess.CompletedProcess, check_id: str) -> list[str]:
    return [ln for ln in result.stdout.splitlines() if f": {check_id}:" in ln]


def _scanned(result: subprocess.CompletedProcess) -> int:
    m = re.search(r"scanned (\d+) SKILL\.md file\(s\)", result.stderr)
    assert m, result.stderr
    return int(m.group(1))


# --- BR-2 / AC-2: skill-line-budget -----------------------------------------

def _lines(n: int) -> str:
    return "".join(f"line {i}\n" for i in range(1, n + 1))


def test_line_budget_fires_at_500_not_499(tmp_path):
    """AC-2: a 500-line SKILL.md is a finding naming the count and the budget;
    a 499-line one beside it is not."""
    _write(tmp_path, "over/SKILL.md", _lines(500))
    _write(tmp_path, "under/SKILL.md", _lines(499))
    result = _run(tmp_path)
    hits = _hits(result, check.SKILL_LINE_BUDGET_CHECK)
    assert hits == [f"over/SKILL.md:1: {check.SKILL_LINE_BUDGET_CHECK}: 500 lines, at or over "
                    "the 500-line budget the Agent Skills specification sets for a SKILL.md — "
                    "move whole steps into <skill>/references/ and leave a read-and-follow "
                    "pointer (REQ-661 BR-2)"], result.stdout
    assert _scanned(result) == 2


def test_line_budget_counts_newlines_like_wc(tmp_path):
    """500 lines without a final newline is 499 to `wc -l`, so it passes."""
    _write(tmp_path, "edge/SKILL.md", _lines(500).rstrip("\n"))
    _write(tmp_path, "over/SKILL.md", _lines(501))
    result = _run(tmp_path)
    assert [h.split(":")[0] for h in _hits(result, check.SKILL_LINE_BUDGET_CHECK)] == ["over/SKILL.md"]


def test_line_budget_never_reads_a_companion(tmp_path):
    """The budget is a SKILL.md budget: a long companion is the point of the split."""
    _write(tmp_path, "x/SKILL.md", CLEAN)
    _write(tmp_path, "x/references/long.md", _lines(900))
    _write(tmp_path, "y/SKILL.md", _lines(600))  # positive control
    result = _run(tmp_path)
    assert [h.split(":")[0] for h in _hits(result, check.SKILL_LINE_BUDGET_CHECK)] == ["y/SKILL.md"]


def test_every_shipped_skill_is_under_the_budget():
    """BR-1 on the real tree, counted the way the check counts."""
    counts = {p.relative_to(REPO_ROOT).as_posix(): p.read_text(encoding="utf-8").count("\n")
              for p in REPO_ROOT.glob("*/SKILL.md")}
    assert len(counts) >= 17
    assert {k: v for k, v in counts.items() if v >= check.SKILL_LINE_BUDGET} == {}


# --- BR-6 / AC-5: companion-templating --------------------------------------

@pytest.mark.parametrize("line", [
    "   adlc_intake_detect '<request>'; gate=$?",
    "self_args='<req-ids>'",
    "Substitute the request for `<request>` as one single-quoted literal.",
    "Target: $ARGUMENTS",
    "Target: ${ARGUMENTS}",
    "!`cat .adlc/context/conventions.md`",
])
def test_companion_templating_fires(tmp_path, line):
    _write(tmp_path, "x/SKILL.md", CLEAN)
    _write(tmp_path, "x/references/step.md", f"# step\n\n{line}\n")
    result = _run(tmp_path)
    assert [h.split(": ")[0] for h in _hits(result, check.COMPANION_TEMPLATING_CHECK)] == [
        "x/references/step.md:3"], result.stdout


def test_companion_templating_benign_paths(tmp_path):
    """A bang line inside a fence is an example; the placeholder in SKILL.md is
    where it belongs; other angle-bracket placeholders are not argument tokens.
    The positive control in the same run fires."""
    _write(tmp_path, "x/SKILL.md", CLEAN + "\n   adlc_intake_detect '<request>'; gate=$?\n")
    _write(tmp_path, "x/references/ok.md",
           "# ok\n\n```text\n!`cat x`\n```\n\nRun `adlc_intake_range <n> <lines>`.\n"
           "The `$ARGUMENTS_FILE` variable is not the token.\n")
    _write(tmp_path, "y/SKILL.md", CLEAN)
    _write(tmp_path, "y/references/bad.md", "self_args='<req-ids>'\n")
    result = _run(tmp_path)
    assert [h.split(": ")[0] for h in _hits(result, check.COMPANION_TEMPLATING_CHECK)] == [
        "y/references/bad.md:1"], result.stdout


def test_companion_templating_covers_proceed_phase_files(tmp_path):
    _write(tmp_path, "proceed/SKILL.md", CLEAN)
    _write(tmp_path, "proceed/phases-x.md", "Run `/spec '<request>'`.\n")
    result = _run(tmp_path)
    assert [h.split(": ")[0] for h in _hits(result, check.COMPANION_TEMPLATING_CHECK)] == [
        "proceed/phases-x.md:1"], result.stdout


def test_shipped_companions_carry_no_preprocessing():
    """AC-5's second half, on the real tree, with the walk proven non-empty."""
    companions = check.find_companion_files(REPO_ROOT)
    assert len(companions) >= 4, companions
    for path in companions:
        rel = path.relative_to(REPO_ROOT).as_posix()
        assert check.check_companion_templating(path.read_text(encoding="utf-8"), rel) == []


# --- BR-7 / AC-7: every per-file check walks the companions -----------------

# fixture -> the check it trips when it is a SKILL.md (test_check.py proves that).
PER_FILE = {
    "corrupt-sentinel": "sentinel",
    "unbalanced-parens": "balance",
    "missing-canonical": "canonical-helper",
    "local-in-sh-fence": "posix-fence",
    "arg-templating": "arg-templating",
    "cross-fence-fn": "cross-fence-fn",
    "cross-fence-var": "cross-fence-var",
    "forge-direct-gh": "forge-direct-gh",
    "read-bin-fallback": "read-bin-fallback",
    "unguarded-source-fence": "unguarded-source",
    "toolkit-root-line-missing": "toolkit-root-line",
    "dispatch-fallback-missing": "dispatch-has-fallback",
}
LAYOUTS = {
    "references": ("alpha/SKILL.md", "alpha/references/{name}.md"),
    "phase": ("proceed/SKILL.md", "proceed/phases-{name}.md"),
    "phase-alone": (None, "proceed/phases-{name}.md"),
}


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
@pytest.mark.parametrize("fixture", sorted(PER_FILE))
def test_every_per_file_check_walks_companions(tmp_path, fixture, layout):
    skill_rel, comp_rel = LAYOUTS[layout]
    comp_rel = comp_rel.format(name=fixture)
    if skill_rel:
        _write(tmp_path, skill_rel, CLEAN)
    _write(tmp_path, "control/SKILL.md", CLEAN)
    _write(tmp_path, comp_rel, (FIXTURES / f"{fixture}.md").read_text(encoding="utf-8"))
    result = _run(tmp_path)
    hits = _hits(result, PER_FILE[fixture])
    assert hits and all(h.startswith(comp_rel + ":") for h in hits), result.stdout
    assert _scanned(result) == (2 if skill_rel else 1)


def test_ethos_line_in_a_companion_is_a_finding(tmp_path):
    """BR-7: a companion carries zero ETHOS lines, and is never owed one."""
    ethos, _ = check.load_ethos_line(REPO_ROOT)
    assert ethos
    _write(tmp_path, "VERSION", "0.0.0\n")
    _write(tmp_path, "alpha/SKILL.md", f"---\nname: alpha\ndescription: x\n---\n\n## Ethos\n\n{ethos}\n")
    _write(tmp_path, "alpha/references/copy.md", f"# copy\n\n{ethos}\n")
    _write(tmp_path, "alpha/references/plain.md", "# plain\n\nNo preamble here.\n")
    result = _run(tmp_path)
    hits = _hits(result, check.ETHOS_LINE_CHECK)
    assert [h.split(": ")[0] for h in hits] == ["alpha/references/copy.md:3"], result.stdout
    assert "belongs to the skill's SKILL.md only" in hits[0]


def test_description_budget_and_skills_ref_report_nothing_on_a_companion(tmp_path):
    """BR-7: `description-budget` reads no companion (a long companion
    `description:` is not one), and `skills-ref` without the validator SKIPs."""
    ethos, _ = check.load_ethos_line(REPO_ROOT)
    _write(tmp_path, "VERSION", "0.0.0\n")
    _write(tmp_path, "alpha/SKILL.md", f"---\nname: alpha\ndescription: x\n---\n\n{ethos}\n")
    _write(tmp_path, "alpha/references/a.md", "---\ndescription: " + "y" * 900 + "\n---\n")
    _write(tmp_path, "beta/SKILL.md", f"---\nname: beta\ndescription: {'z' * 600}\n---\n\n{ethos}\n")
    result = _run(tmp_path)
    budget = _hits(result, check.DESCRIPTION_BUDGET_CHECK)
    assert [h.split(":")[0] for h in budget] == ["beta/SKILL.md"], result.stdout
    assert not [h for h in result.stdout.splitlines() if "alpha/references" in h], result.stdout


def test_no_harness_path_reads_references(tmp_path):
    ethos, _ = check.load_ethos_line(REPO_ROOT)
    _write(tmp_path, "VERSION", "0.0.0\n")
    _write(tmp_path, "alpha/SKILL.md", f"---\nname: alpha\ndescription: x\n---\n\n{ethos}\n")
    _write(tmp_path, "alpha/references/a.md", "Read `~/.codex/config.toml` first.\n")
    hits = _hits(_run(tmp_path), check.NO_HARNESS_PATH_CHECK)
    assert [h.split(": ")[0] for h in hits] == ["alpha/references/a.md:1"], hits


def test_scanned_counts_skill_md_only(tmp_path):
    """BR-9 / AC-7: companions never enter the scanned figure, and a root with
    companions but no SKILL.md is still a vacuous scan."""
    _write(tmp_path, "alpha/SKILL.md", CLEAN)
    for i in range(3):
        _write(tmp_path, f"alpha/references/c{i}.md", CLEAN)
    _write(tmp_path, "proceed/phases-x.md", CLEAN)
    assert _scanned(_run(tmp_path)) == 1
    lone = tmp_path / "lone"
    _write(lone, "proceed/phases-x.md", CLEAN)
    result = _run(lone)
    assert _scanned(result) == 0 and result.returncode == check.VACUOUS_SCAN_EXIT


def test_companion_walk_follows_the_skill_walk_pruning(tmp_path):
    """A unit under `.worktrees/` or `.claude/worktrees/` is not walked, its
    companions included; the root's own skill is (BUG-254, LESSON-019)."""
    _write(tmp_path, "alpha/SKILL.md", CLEAN)
    _write(tmp_path, "alpha/references/bad.md", "self_args='<req-ids>'\n")
    for nested in (".worktrees/REQ-1/beta", ".claude/worktrees/s/beta"):
        _write(tmp_path, f"{nested}/SKILL.md", CLEAN)
        _write(tmp_path, f"{nested}/references/bad.md", "self_args='<req-ids>'\n")
    result = _run(tmp_path)
    assert [h.split(":")[0] for h in _hits(result, check.COMPANION_TEMPLATING_CHECK)] == [
        "alpha/references/bad.md"], result.stdout
    assert _scanned(result) == 1


def test_no_nested_companions_and_one_proceed_layout(tmp_path):
    """BR-12: only one level below `references/` is a companion."""
    _write(tmp_path, "alpha/SKILL.md", CLEAN)
    _write(tmp_path, "alpha/references/deep/bad.md", "self_args='<req-ids>'\n")
    _write(tmp_path, "alpha/references/top.md", "self_args='<req-ids>'\n")
    hits = _hits(_run(tmp_path), check.COMPANION_TEMPLATING_CHECK)
    assert [h.split(":")[0] for h in hits] == ["alpha/references/top.md"]
    assert list(REPO_ROOT.glob("*/references/*/*.md")) == []
    proceed = REPO_ROOT / "proceed"
    assert not ((proceed / "references").exists() and list(proceed.glob("phase*.md")))


# --- BR-8 / AC-8: the unit is one scope -------------------------------------

FN_DEF = "# alpha\n\n```sh\nhelper() {\n  echo hi\n}\n```\n"
FN_CALL = "# step\n\nText.\n\n```sh\nhelper\n```\n"
VAR_SET = "# alpha\n\n```sh\nwant=$(date)\n```\n"
VAR_READ = "# step\n\n```sh\necho \"$want\"\n```\n"


def test_cross_fence_checks_span_the_unit(tmp_path):
    """AC-8: a function defined in SKILL.md and called in a companion is a
    finding at the call site, and a variable likewise at the read."""
    _write(tmp_path, "fn/SKILL.md", FN_DEF)
    _write(tmp_path, "fn/references/x.md", FN_CALL)
    _write(tmp_path, "var/SKILL.md", VAR_SET)
    _write(tmp_path, "var/references/x.md", VAR_READ)
    result = _run(tmp_path)
    fn = _hits(result, "cross-fence-fn")
    var = _hits(result, "cross-fence-var")
    assert [h.split(": ")[0] for h in fn] == ["fn/references/x.md:6"], result.stdout
    assert "fn/SKILL.md:4" in fn[0]
    assert [h.split(": ")[0] for h in var] == ["var/references/x.md:4"], result.stdout
    assert "var/SKILL.md" in var[0]


def test_cross_fence_unit_scope_benign_paths(tmp_path):
    """The same function defined and called in one companion fence, and an
    exported variable, are clean — beside a positive control that fires."""
    _write(tmp_path, "ok/SKILL.md", "# ok\n\n```sh\nexport shared=1\n```\n")
    _write(tmp_path, "ok/references/x.md",
           "# x\n\n```sh\nhelper() {\n  echo hi\n}\nhelper\necho \"$shared\"\n```\n")
    _write(tmp_path, "bad/SKILL.md", FN_DEF)
    _write(tmp_path, "bad/references/x.md", FN_CALL)
    result = _run(tmp_path)
    assert [h.split(":")[0] for h in _hits(result, "cross-fence-fn")] == ["bad/references/x.md"]
    assert _hits(result, "cross-fence-var") == []


def test_units_are_separate_scopes(tmp_path):
    """Two skills never share a scope: a definition in one skill does not make a
    call in another skill's companion a finding."""
    _write(tmp_path, "a/SKILL.md", FN_DEF)
    _write(tmp_path, "b/SKILL.md", CLEAN)
    _write(tmp_path, "b/references/x.md", FN_CALL)
    _write(tmp_path, "c/SKILL.md", FN_DEF)  # positive control: c's own companion
    _write(tmp_path, "c/references/x.md", FN_CALL)
    hits = _hits(_run(tmp_path), "cross-fence-fn")
    assert [h.split(":")[0] for h in hits] == ["c/references/x.md"]


def test_within_file_findings_are_unchanged():
    """A unit of one reports exactly what the per-file check always has, and
    the fixtures do report something (not a vacuous equality)."""
    fn_text = (FIXTURES / "cross-fence-fn.md").read_text(encoding="utf-8")
    var_text = (FIXTURES / "cross-fence-var.md").read_text(encoding="utf-8")
    fn = check.check_cross_fence_fn(fn_text, "s/SKILL.md")
    var = check.check_cross_fence_var(var_text, "s/SKILL.md")
    assert fn and var
    assert check.check_cross_fence_fn_unit([("s/SKILL.md", fn_text)]) == fn
    assert check.check_cross_fence_var_unit([("s/SKILL.md", var_text)]) == var


def test_canonical_literal_in_a_companion_satisfies_the_unit(tmp_path):
    """AC-8: the gate anchor in SKILL.md and every canonical literal in a
    companion is clean; an anchor with no literal anywhere is the control."""
    canonical = (FIXTURES / "delegate-gate-ok.md").read_text(encoding="utf-8")
    assert "ADLC_DISABLE_DELEGATE" in canonical
    _write(tmp_path, "unit/SKILL.md", "# unit\n\nSet `ADLC_DISABLE_DELEGATE=1` to opt out.\n")
    _write(tmp_path, "unit/references/fences.md",
           canonical.replace("ADLC_DISABLE_DELEGATE", "the opt-out"))
    _write(tmp_path, "control/SKILL.md", "# control\n\nSet `ADLC_DISABLE_DELEGATE=1` to opt out.\n")
    shutil.copytree(REPO_ROOT / "partials", tmp_path / "partials")
    result = _run(tmp_path)
    hits = _hits(result, "canonical-helper")
    assert hits and {h.split(":")[0] for h in hits} == {"control/SKILL.md"}, result.stdout


# --- BR-4 / AC-4: every shipped companion is named by its SKILL.md -----------

POINTER = "Read `{path}` and follow it before you continue."
SUMMARY_COMPANIONS = {"proceed/phases-1-3-validation.md", "proceed/phase-4-implementation.md",
                      "proceed/phases-6-8-ship.md"}


def test_shipped_companions_are_named_by_their_skill():
    """AC-4: each read-and-follow companion is named at its old position by the
    pointer sentence, and names its SKILL.md back; each summary companion is
    named by its marker. An orphaned companion fails here (LESSON-012)."""
    seen = 0
    for unit in check.find_skill_units(REPO_ROOT):
        if unit.skill_md is None:
            continue
        skill = unit.skill_md.read_text(encoding="utf-8")
        skill_rel = unit.skill_md.relative_to(REPO_ROOT).as_posix()
        for path in unit.companions:
            rel = path.relative_to(REPO_ROOT).as_posix()
            seen += 1
            if rel in SUMMARY_COMPANIONS:
                assert f"<!-- companion: {rel} -->" in skill, rel
            elif rel == "proceed/phases-lite.md":
                assert "`proceed/phases-lite.md`" in skill, rel
            else:
                assert POINTER.format(path=rel) in skill, rel
                assert f"Companion to `{skill_rel}`" in path.read_text(encoding="utf-8"), rel
    assert seen >= 4
