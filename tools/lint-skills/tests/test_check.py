"""Pytest cases for tools/lint-skills/check.py.

Tests invoke the linter via subprocess against per-case fixture roots
copied into tmp_path. This exercises the CLI contract rather than
importing internals.
"""
from __future__ import annotations

import os
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
    # (REQ-522 flag-file-derived shape).
    assert result.stdout.count("canonical-helper") == 5
    assert 'skill-flag.sh mark "$flag" start_s ' in result.stdout
    assert "_adlc_emit_step_telemetry " in result.stdout
    assert '"$DELEGATE_TOOLS"/emit-telemetry.sh ' in result.stdout
    assert ". .adlc/partials/delegate-gate.sh 2>/dev/null" in result.stdout
    assert ". .adlc/partials/delegate-tools-path.sh 2>/dev/null" in result.stdout


def test_delegate_gate_new_spelling_is_clean(tmp_path):
    """REQ-522: a SKILL.md using the de-branded flag-file telemetry shape
    (delegate-gate.sh / delegate-tools-path.sh / $DELEGATE_TOOLS /
    skill-flag.sh mark start_s / the shared resolver call) must pass with zero
    canonical findings. The emit-telemetry literal lives in the sourced
    emit-step-telemetry.sh partial, so stage that partial to exercise the
    partial-aware canonical rule."""
    root = _stage(tmp_path, "delegate-gate-ok")
    _stage_partial(root)
    result = _run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "canonical-helper" not in result.stdout, result.stdout
    assert result.stdout.strip() == "", result.stdout


def test_new_disable_anchor_triggers_canonical_check(tmp_path):
    """A SKILL.md that mentions ADLC_DISABLE_DELEGATE but wires up NO canonical
    helpers must still be flagged (don't let the guard go vacuous behind the
    de-brand rename)."""
    sub = tmp_path / "naked-new-anchor"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "# Mentions the new disable anchor but wires up no gate.\n\n"
        "Set `ADLC_DISABLE_DELEGATE=1` to opt out.\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    # All five canonical literals are missing → five canonical-helper findings.
    assert result.stdout.count("canonical-helper") == 5, result.stdout


def test_missing_only_resolver_source_reports_one(tmp_path):
    """REQ-433 guard (de-branded): a skill that kept the `"$DELEGATE_TOOLS"/…`
    invocation but lost the delegate-tools-path resolver-source line must raise
    exactly ONE canonical-helper finding naming that literal — proves the linter
    enforces each literal independently, not as an all-or-nothing group."""
    root = _stage(tmp_path, "missing-resolver-source")
    result = _run(root)
    assert result.returncode >= 1, result.stdout
    # Exactly one finding, and it is the missing resolver-source literal (the
    # count==1 already proves the other four present literals were NOT flagged).
    assert result.stdout.count("canonical-helper") == 1, result.stdout
    assert ". .adlc/partials/delegate-tools-path.sh 2>/dev/null" in result.stdout


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
    """REQ-436 ADR-4 (REQ-522 shape): a skill keeping the gate/tools-path/start_s
    /resolver-call literals inline but the emit-telemetry literal in the partial
    is clean.

    `canonical-via-partial-skill` mentions `ADLC_DISABLE_DELEGATE` and keeps four
    literals inline but NOT the `"$DELEGATE_TOOLS"/emit-telemetry.sh` literal (it
    lives in `partials/emit-step-telemetry.sh`). With the real telemetry partial
    staged under the scan root — in EITHER resolution layout `load_partials_blob`
    supports — `check_canonical` must find the relocated literal in the partial
    blob and emit ZERO `canonical-helper` findings (LESSON-019 #3), both layouts.
    """
    root = _stage(tmp_path, "canonical-via-partial-skill")
    _stage_partial(root, layout=layout)
    result = _run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "canonical-helper" not in result.stdout, result.stdout
    assert result.stdout.strip() == "", result.stdout


def test_canonical_via_partial_negative_without_partial(tmp_path):
    """The negative half of ADR-4: the SAME SKILL.md staged WITHOUT any
    telemetry partial yields EXACTLY the one missing-canonical finding (the
    relocated emit-telemetry literal). Proves the partial is genuinely what
    satisfies it — ADR-4 is load-bearing, not vacuously green.
    """
    root = _stage(tmp_path, "canonical-via-partial-skill")
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert result.stdout.count("canonical-helper") == 1, result.stdout
    # The one absent literal is the relocated emit-telemetry exec; the inline
    # four must NOT be flagged (count==1 already implies that).
    assert '"$DELEGATE_TOOLS"/emit-telemetry.sh ' in result.stdout
    assert 'skill-flag.sh mark "$flag" start_s ' not in result.stdout
    assert ". .adlc/partials/delegate-gate.sh 2>/dev/null" not in result.stdout
    assert ". .adlc/partials/delegate-tools-path.sh 2>/dev/null" not in result.stdout


def test_canonical_partial_does_not_rescue_skill_that_does_not_source_it(tmp_path):
    """REQ-436 Phase-5 security hardening: a SKILL.md that mentions
    ADLC_DISABLE_DELEGATE but sources NO telemetry partial must NOT be rescued by
    an unrelated `partials/emit-step-telemetry.sh` elsewhere in the repo.
    Otherwise the partial-aware canonical rule (ADR-4) re-rots into vacuity —
    the exact LESSON-019 #1 failure ADR-4 exists to prevent.
    """
    sub = tmp_path / "no-source"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "# no-source\n\n"
        "```sh\n"
        ". .adlc/partials/delegate-gate.sh 2>/dev/null || "
        ". ~/.claude/skills/partials/delegate-gate.sh\n"
        ". .adlc/partials/delegate-tools-path.sh 2>/dev/null || "
        ". ~/.claude/skills/partials/delegate-tools-path.sh\n"
        'flag=$("$DELEGATE_TOOLS"/skill-flag.sh create)\n'
        '"$DELEGATE_TOOLS"/skill-flag.sh mark "$flag" start_s "$(date -u +%s)"\n'
        "_adlc_emit_step_telemetry some-skill Some-Step\n"
        "# anchor: ADLC_DISABLE_DELEGATE gate-case comment\n"
        "```\n"
    )
    # A telemetry partial DOES exist in the repo (it supplies the emit-telemetry
    # literal) — but this SKILL.md never sources it (no
    # `partials/emit-step-telemetry.sh` marker in its text), so the guard must
    # still flag the missing emit-telemetry literal.
    _stage_partial(tmp_path, layout="partials")
    result = _run(tmp_path)
    assert result.returncode >= 1, result.stdout
    assert result.stdout.count("canonical-helper") == 1, result.stdout
    assert '"$DELEGATE_TOOLS"/emit-telemetry.sh ' in result.stdout
    # The inline four are present, so they are NOT flagged (count==1 implies it).
    assert 'skill-flag.sh mark "$flag" start_s ' not in result.stdout


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


def test_arg_templating_flags_bare_positionals(tmp_path):
    """A bare `$<digit>` — shell positional or awk field, in a fence OR in
    prose — is flagged with an `arg-templating` finding on its line. The
    templating-safe spellings `${1}` / `$(0)` and the `$$1` PID form are
    never flagged.
    """
    root = _stage(tmp_path, "arg-templating")
    result = _run(root)
    assert result.returncode > 0, result.stdout
    at_lines = [
        ln for ln in result.stdout.splitlines() if " arg-templating:" in ln
    ]
    prose_line = _line_of("arg-templating", "Prose mention of a positional")
    unsafe_line = _line_of("arg-templating", 'emit() { awk -v k="$1"')
    safe_line = _line_of("arg-templating", 'safe() { awk -v k="${1}"')
    pid_line = _line_of("arg-templating", "pid-then-digit")
    # Exactly the prose line and the unsafe fence line are flagged.
    assert len(at_lines) == 2, result.stdout
    assert any(
        f"arg-templating/SKILL.md:{prose_line}: arg-templating:" in ln
        for ln in at_lines
    ), (at_lines, prose_line)
    assert any(
        f"arg-templating/SKILL.md:{unsafe_line}: arg-templating:" in ln
        for ln in at_lines
    ), (at_lines, unsafe_line)
    for exempt in (safe_line, pid_line):
        assert not any(
            f":{exempt}: arg-templating:" in ln for ln in at_lines
        ), (at_lines, exempt)
    assert all("clobbered by Skill argument templating" in ln for ln in at_lines)


def test_forge_direct_gh_flagged(tmp_path):
    """REQ-520 BR-1: a direct `gh pr merge` inside a shell fence → one
    `forge-direct-gh` finding naming the op, on the fence line (not the prose
    mention). The prose `gh pr merge` outside the fence is NOT flagged.
    """
    root = _stage(tmp_path, "forge-direct-gh")
    result = _run(root)
    assert result.returncode > 0, result.stdout
    fd_lines = [
        ln for ln in result.stdout.splitlines() if " forge-direct-gh:" in ln
    ]
    assert len(fd_lines) == 1, result.stdout
    fence_line = _line_of("forge-direct-gh", 'gh pr merge "$prUrl"')
    assert f"forge-direct-gh/SKILL.md:{fence_line}: forge-direct-gh:" in fd_lines[0]
    assert "merge" in fd_lines[0]
    assert "partials/forge.sh" in fd_lines[0]


def test_forge_adapter_ok_is_clean(tmp_path):
    """REQ-520 BR-1: adapter calls + the exempt `gh pr diff`/`gh pr checks`
    produce no `forge-direct-gh` finding.
    """
    root = _stage(tmp_path, "forge-adapter-ok")
    result = _run(root)
    fd_lines = [
        ln for ln in result.stdout.splitlines() if " forge-direct-gh:" in ln
    ]
    assert fd_lines == [], result.stdout


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


def test_cross_fence_var_flagged(tmp_path):
    """REQ-522 BR-5: a non-exported variable assigned in one fenced block and
    read in a DIFFERENT fenced block → one `cross-fence-var` finding naming the
    variable, reported on the READ line. An exported var crossing fences is NOT
    flagged."""
    root = _stage(tmp_path, "cross-fence-var")
    result = _run(root)
    cf_lines = [
        ln for ln in result.stdout.splitlines() if " cross-fence-var:" in ln
    ]
    # Exactly one cross-fence-var finding, and it names `captured` (not `shared`).
    assert len(cf_lines) == 1, result.stdout
    assert "'captured'" in cf_lines[0], cf_lines[0]
    assert "shared" not in result.stdout, result.stdout
    read_line = _line_of("cross-fence-var", 'echo "step two sees captured=$captured"')
    assert f"cross-fence-var/SKILL.md:{read_line}: cross-fence-var:" in cf_lines[0]


def test_cross_fence_var_same_fence_control_is_clean(tmp_path):
    """A var assigned AND read within the SAME fenced block is legitimate (shell
    state is shared within one block) and must NOT produce a cross-fence-var
    finding."""
    sub = tmp_path / "samefencevar"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "# Same-fence assign-and-read — legitimate\n\n"
        "```sh\n"
        "x=$(date -u +%s)\n"
        'echo "x=$x"\n'
        "```\n"
    )
    result = _run(tmp_path)
    assert "cross-fence-var" not in result.stdout, result.stdout
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


def test_io_error_finding_does_not_leak_absolute_path(tmp_path):
    """BUG-054 / REQ-435 verify Low #1: an unreadable SKILL.md must produce an
    `io-error` finding whose label is root-relative and whose message is the
    path-free POSIX reason. The absolute filesystem path must NOT appear
    anywhere in stdout — findings are printed and land in CI logs. Pre-fix the
    branch emitted `Finding(str(skill_path), 1, "io-error", f"...{exc}")`,
    leaking the absolute path twice: once as the label and once via
    `str(OSError)` = `[Errno N] <reason>: '<abs path>'`. LESSON-007: the
    assertion is made at the leak point itself, not a proxy.
    """
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("running as root: chmod 0 does not block read; cannot force OSError")
    sub = tmp_path / "unreadable"
    sub.mkdir()
    skill = sub / "SKILL.md"
    skill.write_text("# unreadable\n")
    skill.chmod(0)
    try:
        result = _run(tmp_path)
    finally:
        # Restore mode so pytest's tmp_path teardown removes it cleanly.
        skill.chmod(0o644)
    assert result.returncode > 0, result.stdout + result.stderr
    assert "io-error" in result.stdout, result.stdout
    # The regression assertion: no absolute path component anywhere in stdout.
    assert str(tmp_path) not in result.stdout, result.stdout
    assert str(sub) not in result.stdout, result.stdout
    # `str(OSError)` embeds `[Errno N] ...: '<abs path>'`; the hardened branch
    # uses `exc.strerror` only, so the errno-prefixed form must be absent.
    assert "[Errno" not in result.stdout, result.stdout
    # Positive: the finding is present under the root-relative basename label.
    assert (
        "unreadable/SKILL.md:1: io-error: could not read:" in result.stdout
    ), result.stdout


# ---------------------------------------------------------------------------
# REQ-435: supplementary coverage for the REQ-436 ADR-5 root-skip fix.
# REQ-436 already made find_skill_files root-relative and added
# test_root_under_worktrees_still_scanned / test_descendant_worktrees_still_skipped.
# These two tests cover surfaces REQ-436 left untested: the exact `check.sh`
# entrypoint /analyze Step 1.9 uses, and the symlink-escape guard (BR-5).
# ---------------------------------------------------------------------------


def test_check_sh_wrapper_nonvacuous_from_worktree_cwd(tmp_path):
    """REQ-435: /analyze Step 1.9 invokes `tools/lint-skills/check.sh` with
    CWD = the worktree (`.worktrees/REQ-xxx`) and NO `--root` (defaults to
    '.'). REQ-436's regression test exercises check.py via `_run` with an
    explicit `--root`; this exercises the *wrapper* + CWD-default path that
    Step 1.9 actually takes, so a future regression in check.sh or the
    `--root` default is caught. Asserts the audit is non-vacuous from a
    worktree CWD."""
    check_sh = REPO_ROOT / "tools" / "lint-skills" / "check.sh"
    worktree = tmp_path / ".worktrees" / "REQ-435"
    sub = worktree / "someskill"
    sub.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "corrupt-sentinel.md", sub / "SKILL.md")
    result = subprocess.run(
        ["sh", str(check_sh)],  # no --root → defaults to "." = cwd
        cwd=str(worktree),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode > 0, result.stdout + result.stderr
    assert "someskill/SKILL.md" in result.stdout
    assert "sentinel" in result.stdout


def test_symlink_outside_root_is_excluded(tmp_path):
    """REQ-435 BR-5: the symlink-escape defense (resolve + relative_to guard)
    must stay in force. A SKILL.md symlinked to a target OUTSIDE the scan
    root resolves outside the root and is dropped, while a real SKILL.md
    inside the root is still found. Load-bearing: this fails if the
    `resolved.relative_to(root_resolved)` guard is removed (the escaping
    symlink would then be followed and reported). REQ-436 added no
    symlink-escape regression test."""
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copyfile(FIXTURES / "corrupt-sentinel.md", outside / "SKILL.md")

    root = tmp_path / "root"
    real = root / "realskill"
    real.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "corrupt-sentinel.md", real / "SKILL.md")
    sneaky = root / "sneaky"
    sneaky.mkdir(parents=True)
    (sneaky / "SKILL.md").symlink_to(outside / "SKILL.md")

    result = _run(root)
    # The real in-root skill is found (walker is genuinely running)...
    assert result.returncode > 0, result.stdout + result.stderr
    assert "realskill/SKILL.md" in result.stdout
    # ...but the symlink escaping the scan root is excluded.
    assert "sneaky/SKILL.md" not in result.stdout
