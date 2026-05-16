"""Pytest cases for tools/lint-skills/check.py.

Tests invoke the linter via subprocess against per-case fixture roots
copied into tmp_path. This exercises the CLI contract rather than
importing internals.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK_PY = REPO_ROOT / "tools" / "lint-skills" / "check.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


PARTIALS_DIR = REPO_ROOT / "partials"


def _stage(tmp_path: Path, *fixture_names: str) -> Path:
    """Copy named fixtures into tmp_path/<name>/SKILL.md and return tmp_path."""
    for name in fixture_names:
        src = FIXTURES / f"{name}.md"
        sub = tmp_path / name
        sub.mkdir()
        shutil.copyfile(src, sub / "SKILL.md")
    return tmp_path


def _stage_partial(tmp_path: Path, layout: str = "partials") -> Path:
    """Stage the real `partials/emit-step-telemetry.sh` under the scan root so
    `check_canonical`'s partial-aware path (REQ-436 ADR-4) is exercised.

    `check.py`'s `load_partials_blob` resolves, in order, `<root>/partials/*.sh`
    then `<root>/.adlc/partials/*.sh`. `layout` selects which of those two real
    layouts (toolkit-self vs consumer) to stage into. The real partial is the
    source of canonical literals L2/L3, so staging it is what makes the
    post-REQ-436 `canonical-via-partial-skill` shape clean — exactly the
    indirection ADR-4 generalizes the guard to follow.
    """
    assert layout in ("partials", ".adlc/partials")
    pdir = tmp_path / layout
    pdir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        PARTIALS_DIR / "emit-step-telemetry.sh",
        pdir / "emit-step-telemetry.sh",
    )
    return tmp_path


def _line_of(fixture_name: str, needle: str) -> int:
    """1-based line number of the first line containing `needle` in a fixture.

    Used so the posix-fence / cross-fence-fn line assertions are COMPUTED from
    the fixture (per the task's "do not hardcode line numbers" constraint), not
    pinned to a literal that silently rots if the fixture is reflowed.
    """
    lines = (FIXTURES / f"{fixture_name}.md").read_text().splitlines()
    return next(i + 1 for i, ln in enumerate(lines) if needle in ln)


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK_PY), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_sentinels_file_exists_and_loads():
    sentinels = (REPO_ROOT / "tools" / "lint-skills" / "sentinels.txt").read_text()
    # BR-2: the REQ-424 sentinel is present and uncommented
    lines = [
        ln.strip()
        for ln in sentinels.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert "20 20 12 61 80 33 98 100" in lines


def test_clean_fixture_is_clean(tmp_path):
    root = _stage(tmp_path, "clean")
    result = _run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == ""


def test_sentinel_finding_reports_file_and_line(tmp_path):
    root = _stage(tmp_path, "corrupt-sentinel")
    result = _run(root)
    assert result.returncode > 0
    assert "corrupt-sentinel/SKILL.md" in result.stdout
    assert "sentinel" in result.stdout
    assert "20 20 12 61 80 33 98 100" in result.stdout
    # Compute the expected line from the fixture rather than hardcoding it.
    fixture = (FIXTURES / "corrupt-sentinel.md").read_text().splitlines()
    expected_line = next(
        i + 1 for i, ln in enumerate(fixture) if "20 20 12 61 80 33 98 100" in ln
    )
    assert f":{expected_line}: sentinel:" in result.stdout


def test_unbalanced_parens_reports_balance_finding(tmp_path):
    root = _stage(tmp_path, "unbalanced-parens")
    result = _run(root)
    assert result.returncode > 0
    assert "balance" in result.stdout
    assert "unbalanced-parens/SKILL.md" in result.stdout
    # Fence opens on line 3 of the fixture
    assert "fence at line 3" in result.stdout


def test_missing_canonical_reports_per_rule(tmp_path):
    root = _stage(tmp_path, "missing-canonical")
    result = _run(root)
    assert result.returncode >= 5, result.stdout
    # All five canonical literals should be reported as separate findings
    assert result.stdout.count("canonical-helper") == 5
    assert "start_s=$(date -u +%s)" in result.stdout
    assert "duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))" in result.stdout
    assert '"$KIMI_TOOLS"/emit-telemetry.sh ' in result.stdout
    assert ". .adlc/partials/kimi-gate.sh 2>/dev/null" in result.stdout
    assert ". .adlc/partials/kimi-tools-path.sh 2>/dev/null" in result.stdout


def test_kimi_gate_happy_path_is_clean(tmp_path):
    root = _stage(tmp_path, "kimi-gate-ok")
    result = _run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    # Not just rc 0 — assert the fixture produces NO findings at all, so a
    # future regression that emits warnings while keeping exit 0 is caught
    # (mirrors test_clean_fixture_is_clean's stricter assertion surface).
    assert "canonical-helper" not in result.stdout, result.stdout
    assert result.stdout.strip() == "", result.stdout


def test_missing_only_resolver_source_reports_one(tmp_path):
    """REQ-433 guard: a skill that kept the `"$KIMI_TOOLS"/…` invocation but
    lost the kimi-tools-path resolver-source line must raise exactly ONE
    canonical-helper finding naming that literal — proves the linter enforces
    each literal independently, not as an all-or-nothing group."""
    root = _stage(tmp_path, "missing-resolver-source")
    result = _run(root)
    assert result.returncode >= 1, result.stdout
    # Exactly one finding, and it is the missing resolver-source literal (the
    # count==1 already proves the other four present literals were NOT flagged).
    assert result.stdout.count("canonical-helper") == 1, result.stdout
    assert ". .adlc/partials/kimi-tools-path.sh 2>/dev/null" in result.stdout


def test_mixed_clean_and_corrupt_scans_both(tmp_path):
    """BR-6/BR-10: when a root contains clean AND corrupt SKILL.md files,
    only the corrupt one produces findings, and the exit code is the
    finding count from the corrupt one alone."""
    root = _stage(tmp_path, "clean", "corrupt-sentinel")
    result = _run(root)
    assert result.returncode == 1
    assert "corrupt-sentinel/SKILL.md" in result.stdout
    assert "clean/SKILL.md" not in result.stdout


def test_double_deficit_flagged(tmp_path):
    """Unbalanced $(( ... without matching )) — the double-deficit branch."""
    sub = tmp_path / "double"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "# Bad arithmetic\n\n```sh\nfoo=$(( 1 + 2\n```\n"
    )
    result = _run(tmp_path)
    assert result.returncode > 0
    assert "balance" in result.stdout
    assert "'$((' opens exceed '))'" in result.stdout


def test_unclosed_fence_flagged(tmp_path):
    """A fence that never closes is itself a structural corruption finding."""
    sub = tmp_path / "unclosed"
    sub.mkdir()
    (sub / "SKILL.md").write_text("# Bad\n\n```sh\necho hello\n")
    result = _run(tmp_path)
    assert result.returncode > 0
    assert "unclosed" in result.stdout


def test_recursive_walk_finds_nested_skill(tmp_path):
    """ADR-4: the walker recurses, not just one level deep."""
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "corrupt-sentinel.md", nested / "SKILL.md")
    result = _run(tmp_path)
    assert result.returncode > 0
    assert "a/b/c/SKILL.md" in result.stdout


def test_skip_dirs_are_excluded(tmp_path):
    """ADR-4: .git, .worktrees, node_modules are excluded from the walk."""
    for skip in [".git", ".worktrees", "node_modules"]:
        sub = tmp_path / skip / "ignored"
        sub.mkdir(parents=True)
        shutil.copyfile(FIXTURES / "corrupt-sentinel.md", sub / "SKILL.md")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_exit_code_capped_at_255(tmp_path):
    """BR-6: exit code is min(num_findings, 255)."""
    # 256 sentinel hits via 256 separate skill files
    for i in range(256):
        sub = tmp_path / f"sk{i:03d}"
        sub.mkdir()
        (sub / "SKILL.md").write_text("20 20 12 61 80 33 98 100\n")
    result = _run(tmp_path)
    assert result.returncode == 255


# ---------------------------------------------------------------------------
# REQ-436 ADR-8: realistic post-change fixtures for every TASK-049 guard.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layout", ["partials", ".adlc/partials"])
def test_canonical_satisfied_via_partial(tmp_path, layout):
    """REQ-436 ADR-4: the post-REQ-436 `analyze` shape is clean.

    `canonical-via-partial-skill` mentions `ADLC_DISABLE_KIMI` and keeps
    L1/L4/L5 inline but NOT L2/L3 (they moved into
    `partials/emit-step-telemetry.sh`). With the real telemetry partial staged
    under the scan root — in EITHER resolution layout `load_partials_blob`
    supports — `check_canonical` must find L2/L3 in the partial blob and emit
    ZERO `canonical-helper` findings. Asserts the indirection-following guard
    on the genuine post-change input (LESSON-019 #3), both layouts.
    """
    root = _stage(tmp_path, "canonical-via-partial-skill")
    _stage_partial(root, layout=layout)
    result = _run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "canonical-helper" not in result.stdout, result.stdout
    assert result.stdout.strip() == "", result.stdout


def test_canonical_via_partial_negative_without_partial(tmp_path):
    """The negative half of ADR-4: the SAME SKILL.md staged WITHOUT any
    telemetry partial yields EXACTLY the two missing-canonical findings (L2 and
    L3). This proves the partial is genuinely what satisfies them — ADR-4 is
    load-bearing, not vacuously green (without it the post-REQ-436 shape would
    self-inflict a regression of REQ-428's AC-3).
    """
    root = _stage(tmp_path, "canonical-via-partial-skill")
    result = _run(root)
    assert result.returncode == 2, result.stdout
    assert result.stdout.count("canonical-helper") == 2, result.stdout
    # The two absent literals are exactly L2 and L3 (the relocated ones); the
    # inline L1/L4/L5 must NOT be flagged (count==2 already implies that).
    assert "duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))" in result.stdout
    assert '"$KIMI_TOOLS"/emit-telemetry.sh ' in result.stdout
    assert "start_s=$(date -u +%s)" not in result.stdout
    assert ". .adlc/partials/kimi-gate.sh 2>/dev/null" not in result.stdout
    assert ". .adlc/partials/kimi-tools-path.sh 2>/dev/null" not in result.stdout


def test_canonical_partial_does_not_rescue_skill_that_does_not_source_it(tmp_path):
    """REQ-436 Phase-5 security hardening: a SKILL.md that mentions
    ADLC_DISABLE_KIMI but sources NO telemetry partial must NOT be rescued by
    an unrelated `partials/emit-step-telemetry.sh` elsewhere in the repo.
    Otherwise the partial-aware canonical rule (ADR-4) re-rots into vacuity —
    the exact LESSON-019 #1 failure ADR-4 exists to prevent.
    """
    sub = tmp_path / "no-source"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "# no-source\n\n"
        "```sh\n"
        ". .adlc/partials/kimi-gate.sh 2>/dev/null || "
        ". ~/.claude/skills/partials/kimi-gate.sh\n"
        ". .adlc/partials/kimi-tools-path.sh 2>/dev/null || "
        ". ~/.claude/skills/partials/kimi-tools-path.sh\n"
        "start_s=$(date -u +%s)\n"
        "# anchor: ADLC_DISABLE_KIMI gate-case comment\n"
        "```\n"
    )
    # A telemetry partial DOES exist in the repo (it supplies L2/L3) — but this
    # SKILL.md never sources it, so the guard must still flag the missing L2/L3.
    _stage_partial(tmp_path, layout="partials")
    result = _run(tmp_path)
    assert result.returncode >= 2, result.stdout
    assert result.stdout.count("canonical-helper") == 2, result.stdout
    assert "duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))" in result.stdout
    assert '"$KIMI_TOOLS"/emit-telemetry.sh ' in result.stdout
    # The inline L1/L4/L5 are present, so they are NOT flagged (count==2 implies it).
    assert "start_s=$(date -u +%s)" not in result.stdout


def test_posix_fence_flags_sh_and_shell_not_bash(tmp_path):
    """REQ-436 ADR-6: `local` at statement position inside a ```sh fence AND
    inside a ```shell fence is flagged (one finding each, on the offending
    line); the identical construct inside a ```bash fence is EXEMPT and never
    appears in any posix-fence finding. Lines computed from the fixture.
    """
    root = _stage(tmp_path, "local-in-sh-fence")
    result = _run(root)
    assert result.returncode > 0, result.stdout
    sh_line = _line_of("local-in-sh-fence", "local x=1")
    shell_line = _line_of("local-in-sh-fence", "local z=3")
    bash_line = _line_of("local-in-sh-fence", "local y=2")

    posix_lines = [
        ln for ln in result.stdout.splitlines() if " posix-fence:" in ln
    ]
    # sh AND shell fences flagged; bash exempt → exactly two findings.
    assert len(posix_lines) == 2, result.stdout
    assert any(
        f"local-in-sh-fence/SKILL.md:{sh_line}: posix-fence:" in ln
        for ln in posix_lines
    ), (posix_lines, sh_line)
    assert any(
        f"local-in-sh-fence/SKILL.md:{shell_line}: posix-fence:" in ln
        for ln in posix_lines
    ), (posix_lines, shell_line)
    assert all("is not POSIX" in ln for ln in posix_lines), posix_lines
    # The bash `local` line is NOT flagged by any posix-fence finding.
    assert not any(
        f":{bash_line}: posix-fence:" in ln for ln in posix_lines
    ), (posix_lines, bash_line)


def test_cross_fence_fn_flagged(tmp_path):
    """REQ-436 ADR-7: `myfn` defined in fence A but invoked only from fence B
    (a different fenced block) → one `cross-fence-fn` finding naming `myfn`,
    reporting the def line and the (different) invocation line, both computed
    from the fixture.
    """
    root = _stage(tmp_path, "cross-fence-fn")
    result = _run(root)
    assert result.returncode > 0, result.stdout
    cf_lines = [
        ln for ln in result.stdout.splitlines() if " cross-fence-fn:" in ln
    ]
    assert len(cf_lines) == 1, result.stdout
    def_line = _line_of("cross-fence-fn", "myfn() {")
    inv_line = next(
        i + 1
        for i, ln in enumerate(
            (FIXTURES / "cross-fence-fn.md").read_text().splitlines()
        )
        if ln.strip() == "myfn"
    )
    assert def_line != inv_line
    assert f"cross-fence-fn/SKILL.md:{def_line}: cross-fence-fn:" in cf_lines[0]
    assert "'myfn'" in cf_lines[0]
    assert f"line {def_line}" in cf_lines[0]
    assert f"line {inv_line}" in cf_lines[0]


def test_cross_fence_fn_same_fence_control_is_clean(tmp_path):
    """Same-fence control: a function DEFINED and CALLED within ONE fenced
    block is legitimate (shell state IS shared within a single fence) and must
    NOT produce a cross-fence-fn finding. Mirrors the inline-fixture style of
    `test_double_deficit_flagged`.
    """
    sub = tmp_path / "samefence"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "# Same-fence define-and-call — legitimate\n\n"
        "```sh\n"
        "g() {\n"
        '    echo "in g"\n'
        "}\n"
        "g\n"
        "```\n"
    )
    result = _run(tmp_path)
    assert "cross-fence-fn" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout + result.stderr


def test_root_under_worktrees_still_scanned(tmp_path):
    """REQ-436 ADR-5 / LESSON-019 #2 regression: when the resolved scan ROOT
    itself sits under a `.worktrees` directory (every `/proceed` phase runs
    inside `.worktrees/...`), the linter must STILL scan it. Pre-ADR-5 code
    applied the skip-list to the root's own components and scanned ZERO files,
    exiting 0 — a confident green having checked nothing. Staging a corrupt
    SKILL.md at `<tmp>/.worktrees/x/` and running with that as the root must
    produce the finding (returncode > 0).
    """
    root = tmp_path / ".worktrees" / "x"
    root.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "corrupt-sentinel.md", root / "SKILL.md")
    result = _run(root)
    assert result.returncode > 0, (
        "root under .worktrees was NOT scanned (pre-ADR-5 vacuous walk): "
        + result.stdout
        + result.stderr
    )
    assert "SKILL.md:" in result.stdout
    assert "sentinel" in result.stdout
    assert "20 20 12 61 80 33 98 100" in result.stdout


def test_descendant_worktrees_still_skipped(tmp_path):
    """ADR-5 control (and the invariant `test_skip_dirs_are_excluded` relies
    on): ADR-5 ONLY changes ROOT-part handling. A `.worktrees` DESCENDANT
    *below* the scan root must STILL be skipped. If this regressed, the linter
    (TASK-049) would be wrong — this asserts the bound of the ADR-5 change.
    """
    sub = tmp_path / ".worktrees" / "ignored"
    sub.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "corrupt-sentinel.md", sub / "SKILL.md")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "", result.stdout
