"""Pytest cases for tools/lint-skills/check.py.

Tests invoke the linter via subprocess against per-case fixture roots
copied into tmp_path. This exercises the CLI contract rather than
importing internals.
"""
from __future__ import annotations

import importlib.util
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
CONVENTIONS_MD = REPO_ROOT / ".adlc" / "context" / "conventions.md"


def _load_check_module():
    """Import `check.py` by path, for the few REQ-669 cases that need its pinned
    constants (`TOOLKIT_ROOT_LINE`, `guarded_source_line`) rather than a copy of
    their bytes here. Every finding is still read from the CLI's output."""
    spec = importlib.util.spec_from_file_location("_lint_check_main", CHECK_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_check = _load_check_module()


def _stage(tmp_path: Path, *fixture_names: str) -> Path:
    """Copy named fixtures into tmp_path/<name>/SKILL.md and return tmp_path."""
    for name in fixture_names:
        src = FIXTURES / f"{name}.md"
        sub = tmp_path / name
        sub.mkdir()
        shutil.copyfile(src, sub / "SKILL.md")
    return tmp_path


def _stage_agent(tmp_path: Path, *fixture_names: str) -> Path:
    """Copy named fixtures into tmp_path/agents/<name>.md and return tmp_path.

    `agents/*.md` is the one extra surface `check_read_bin_fallback` walks
    (REQ-609): `agents/delegate-pre-pass.md` hands a corpus to the delegate
    exactly as a skill does. Kept as its own staging helper because the file
    lands under a fixed directory name rather than in a per-skill subdirectory.
    """
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    for name in fixture_names:
        shutil.copyfile(FIXTURES / f"{name}.md", agents / f"{name}.md")
    return tmp_path


def _stage_phase(tmp_path: Path, *names: str, dest_name: str | None = None) -> Path:
    """Copy named fixtures into tmp_path/proceed/<name>.md and return tmp_path.

    `proceed/phase*.md` is the extra surface `check_unguarded_source` walks
    (REQ-610 ADR-3): the `/proceed` companion phase files carry executable
    fences — one of them sources `forge.sh` — and no check walked them before.
    `dest_name` renames a single fixture on the way in, so a test can stage a
    fixture at the REAL file name (`phases-6-8-ship.md`) and prove the
    `phase*.md` glob covers it.
    """
    proceed = tmp_path / "proceed"
    proceed.mkdir(exist_ok=True)
    if dest_name is not None:
        assert len(names) == 1, "dest_name renames exactly one fixture"
        shutil.copyfile(FIXTURES / f"{names[0]}.md", proceed / dest_name)
        return tmp_path
    for name in names:
        shutil.copyfile(FIXTURES / f"{name}.md", proceed / f"{name}.md")
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
    # REQ-610 ADR-4: the two source literals are the `[ -f ]`-guarded spelling.
    assert "if [ -f .adlc/partials/delegate-gate.sh ]; then" in result.stdout
    assert "if [ -f .adlc/partials/delegate-tools-path.sh ]; then" in result.stdout
    # REQ-669 BR-5: the ToolkitRoot spelling is the one offered. Since TASK-124
    # retired the REQ-610 operand, the finding no longer offers it as well.
    gate_line = next(
        ln for ln in result.stdout.splitlines() if "delegate-gate.sh ]; then" in ln
    )
    assert '. "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi' in gate_line, gate_line
    assert ". ~/.claude/skills/partials/delegate-gate.sh; fi" not in gate_line, gate_line


def test_canonical_helper_accepts_toolkit_root_spelling(tmp_path):
    """REQ-669 BR-5: the two delegate-* canonical literals accept the ToolkitRoot
    spelling. A skill whose gate and tools-path lines both use it, behind the
    fence's root line, has every literal and no other finding. Since TASK-124
    it is the only operand that satisfies the literal: the REQ-610 operand and
    the retired `2>/dev/null ||` shape satisfy neither
    (`test_old_delegate_gate_spelling_fails_...`).
    """
    sub = tmp_path / "toolkit-root-gate"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "# The post-REQ-669 telemetry shape.\n\n"
        "```sh\n"
        + _check.TOOLKIT_ROOT_LINE + "\n"
        + _check.guarded_source_line("delegate-gate") + "\n"
        + _check.guarded_source_line("delegate-tools-path") + "\n"
        'flag=$("$DELEGATE_TOOLS"/skill-flag.sh create)\n'
        '"$DELEGATE_TOOLS"/skill-flag.sh mark "$flag" start_s "$(date -u +%s)"\n'
        "adlc_delegate_gate_check; gate=$?\n"
        + _check.guarded_source_line("emit-step-telemetry") + "\n"
        "_adlc_emit_step_telemetry some-skill Some-Step\n"
        "# anchor: ADLC_DISABLE_DELEGATE gate-case comment\n"
        "```\n",
        encoding="utf-8",
    )
    _stage_partial(tmp_path, layout="partials")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "", result.stdout

    # Benign-path control (LESSON-440): drop the gate line and exactly that
    # literal is reported, so the clean run above was the literal being found.
    text = (sub / "SKILL.md").read_text(encoding="utf-8")
    (sub / "SKILL.md").write_text(
        text.replace(_check.guarded_source_line("delegate-gate") + "\n", ""),
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.stdout.count("canonical-helper") == 1, result.stdout
    assert "delegate-gate.sh ]; then" in result.stdout, result.stdout


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
    assert "if [ -f .adlc/partials/delegate-tools-path.sh ]; then" in result.stdout


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
    """ADR-4: .git, .worktrees, node_modules are excluded from the walk.

    A real, clean in-root skill is staged alongside the buried corrupt ones so
    the walker is provably running (same construction as
    `test_symlink_outside_root_is_excluded`). Without it this asserted only
    "nothing was reported", which a totally broken walker also satisfies — and
    which REQ-595's vacuous-scan guard now reports as status 255 rather than a
    green.
    """
    for skip in [".git", ".worktrees", "node_modules"]:
        sub = tmp_path / skip / "ignored"
        sub.mkdir(parents=True)
        shutil.copyfile(FIXTURES / "corrupt-sentinel.md", sub / "SKILL.md")
    real = tmp_path / "realskill"
    real.mkdir()
    shutil.copyfile(FIXTURES / "clean.md", real / "SKILL.md")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == ""
    # Exactly the one real skill was walked — the three buried ones were not.
    assert "scanned 1 SKILL.md file(s)" in result.stderr, result.stderr


def test_exit_code_capped_below_the_vacuous_status(tmp_path):
    """BR-6, as amended by REQ-595 BR-5: the findings exit is
    `min(num_findings, 254)`. The cap moved down by one so status 255 can mean
    "vacuous scan" unambiguously — POSIX statuses are 8-bit, so the distinct
    value had to be carved out of the top of the findings range rather than
    placed above it. A saturating findings run must NOT be mistakable for a
    scan that checked nothing.
    """
    # 256 sentinel hits via 256 separate skill files
    for i in range(256):
        sub = tmp_path / f"sk{i:03d}"
        sub.mkdir()
        (sub / "SKILL.md").write_text("20 20 12 61 80 33 98 100\n")
    result = _run(tmp_path)
    assert result.returncode == 254, result.stderr
    # ...and it is emphatically not the vacuous status.
    assert "VACUOUS SCAN" not in result.stderr, result.stderr
    assert "scanned 256 SKILL.md file(s)" in result.stderr, result.stderr


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
    assert "if [ -f .adlc/partials/delegate-gate.sh ]; then" not in result.stdout
    assert (
        "if [ -f .adlc/partials/delegate-tools-path.sh ]; then" not in result.stdout
    )


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
        + _check.TOOLKIT_ROOT_LINE + "\n"
        + _check.guarded_source_line("delegate-gate") + "\n"
        + _check.guarded_source_line("delegate-tools-path") + "\n"
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


def test_read_bin_fallback_fires_and_passes(tmp_path):
    """REQ-609 BR-12: a `${ADLC_READ_BIN:-…}` default inside a shell fence →
    exactly one `read-bin-fallback` finding, on the fence line (the prose
    mention above it is NOT flagged). The post-REQ-609 shape — gate sourced,
    empty `ADLC_READ_BIN` refused, `"$ADLC_READ_BIN"` invoked — produces none.

    Both fixtures are staged into ONE scan so the clean half is a positive
    control for the flagged half: "the guarded shape reported nothing" only
    means something when the same run demonstrably reports the shape the check
    exists to catch (LESSON-602). The flagged fixture's default is deliberately
    not the bare name, which also pins the match to the expansion operator
    rather than to one default value.
    """
    root = _stage(tmp_path, "read-bin-fallback", "read-bin-guarded")
    result = _run(root)
    assert result.returncode > 0, (result.stdout, result.stderr)
    rb_lines = [
        ln for ln in result.stdout.splitlines() if " read-bin-fallback:" in ln
    ]
    assert len(rb_lines) == 1, result.stdout
    fence_line = _line_of("read-bin-fallback", '--paths ./notes.md')
    assert (
        f"read-bin-fallback/SKILL.md:{fence_line}: read-bin-fallback:" in rb_lines[0]
    ), rb_lines
    assert "REQ-609 BR-12" in rb_lines[0]
    # Positive-control half: the guarded fixture draws no finding from ANY check.
    guarded = [
        ln for ln in result.stdout.splitlines() if "read-bin-guarded/SKILL.md" in ln
    ]
    assert guarded == [], result.stdout
    # And the scan was not vacuous — both fixtures were actually walked.
    assert "scanned 2 SKILL.md file(s)" in result.stderr, result.stderr


def test_read_bin_missing_command_prefix_fires(tmp_path):
    """REQ-609 ADR-3: an invocation without the `command` prefix → exactly one
    `read-bin-fallback` finding, on the invocation line.

    bash and zsh both permit a function whose NAME is an absolute path, so a
    bare `"$ADLC_READ_BIN" --paths …` runs that function and it — not the file
    the resolver proved is on disk — receives the corpus. The fixture's guard is
    correct and its `:-` default absent, so this isolates the `command` half;
    `read-bin-guarded` is staged alongside as the positive control, proving the
    same run reports nothing for the shape that IS correct (LESSON-602).
    """
    root = _stage(tmp_path, "read-bin-no-command", "read-bin-guarded")
    result = _run(root)
    rb_lines = [
        ln for ln in result.stdout.splitlines() if " read-bin-fallback:" in ln
    ]
    assert len(rb_lines) == 1, result.stdout
    # `--paths` on the needle: the fixture also mentions the bare invocation in
    # PROSE, which must not be flagged, and `_line_of` takes the first match.
    fence_line = _line_of("read-bin-no-command", '"$ADLC_READ_BIN" --no-warn --paths')
    assert (
        f"read-bin-no-command/SKILL.md:{fence_line}: read-bin-fallback:"
        in rb_lines[0]
    ), rb_lines
    assert "`command`" in rb_lines[0]
    assert "REQ-609 ADR-3" in rb_lines[0]
    assert [
        ln for ln in result.stdout.splitlines() if "read-bin-guarded/SKILL.md" in ln
    ] == [], result.stdout
    assert "scanned 2 SKILL.md file(s)" in result.stderr, result.stderr


def test_read_bin_legacy_nonempty_guard_fires(tmp_path):
    """REQ-609 BR-12: `[ -n "$ADLC_READ_BIN" ]` is not a guard → one finding.

    A stale vendored `delegate-gate.sh` still exports the BARE NAME on a `$PATH`
    hit, and a non-empty test passes it through to the shell's lookup machinery.
    The fixture carries `command` and no `:-` default, so this isolates the
    guard half.
    """
    root = _stage(tmp_path, "read-bin-guard-missing", "read-bin-guarded")
    result = _run(root)
    rb_lines = [
        ln for ln in result.stdout.splitlines() if " read-bin-fallback:" in ln
    ]
    assert len(rb_lines) == 1, result.stdout
    fence_line = _line_of("read-bin-guard-missing", 'command "$ADLC_READ_BIN"')
    assert (
        f"read-bin-guard-missing/SKILL.md:{fence_line}: read-bin-fallback:"
        in rb_lines[0]
    ), rb_lines
    assert 'case "$ADLC_READ_BIN" in /*)' in rb_lines[0]
    assert [
        ln for ln in result.stdout.splitlines() if "read-bin-guarded/SKILL.md" in ln
    ] == [], result.stdout


def test_read_bin_guard_after_invocation_fires(tmp_path):
    """REQ-609 BR-12: the guard must PRECEDE the invocation, not merely exist.

    The fixture contains the exact guard literal, so a presence-only check calls
    it clean — while the corpus has already left the machine by the time the
    refusal runs. Order is the whole property.
    """
    root = _stage(tmp_path, "read-bin-guard-late", "read-bin-guarded")
    result = _run(root)
    rb_lines = [
        ln for ln in result.stdout.splitlines() if " read-bin-fallback:" in ln
    ]
    assert len(rb_lines) == 1, result.stdout
    fence_line = _line_of("read-bin-guard-late", 'command "$ADLC_READ_BIN"')
    guard_line = _line_of("read-bin-guard-late", 'case "$ADLC_READ_BIN" in /*)')
    assert guard_line > fence_line, "the fixture no longer orders them wrongly"
    assert (
        f"read-bin-guard-late/SKILL.md:{fence_line}: read-bin-fallback:"
        in rb_lines[0]
    ), rb_lines


def test_read_bin_unquoted_invocation_fires(tmp_path):
    """REQ-609 verify D3: `command $ADLC_READ_BIN --paths …` → one finding.

    The guard and the `command` prefix are both correct, so this isolates the
    quoting half. An unquoted expansion is word-split and glob-expanded before
    it is a command name: `/Users/a b/bin/adlc-read` becomes two words and a
    path carrying a glob character becomes whatever matches — which is the
    shell re-deriving the binary the resolver already proved, the BUG-209 class
    the whole contract exists to close.
    """
    root = _stage(tmp_path, "read-bin-unquoted", "read-bin-guarded")
    result = _run(root)
    rb_lines = [
        ln for ln in result.stdout.splitlines() if " read-bin-fallback:" in ln
    ]
    assert len(rb_lines) == 1, result.stdout
    fence_line = _line_of("read-bin-unquoted", "command $ADLC_READ_BIN --no-warn")
    assert (
        f"read-bin-unquoted/SKILL.md:{fence_line}: read-bin-fallback:" in rb_lines[0]
    ), rb_lines
    assert "unquoted" in rb_lines[0]
    assert [
        ln for ln in result.stdout.splitlines() if "read-bin-guarded/SKILL.md" in ln
    ] == [], result.stdout


def test_read_bin_braced_spelling_is_an_invocation(tmp_path):
    """REQ-609 verify D3: `"${ADLC_READ_BIN}"` is the same invocation.

    A check that sees only `"$ADLC_READ_BIN"` lets the braced spelling — the
    same command, written the other legal way — walk past every one of the
    three obligations. The fixture's fence is correct except that it has NO
    guard, so the single finding it draws can only be produced by a check that
    recognised the braced form as an invocation in the first place.
    """
    root = _stage(tmp_path, "read-bin-braced-no-guard", "read-bin-guarded")
    result = _run(root)
    rb_lines = [
        ln for ln in result.stdout.splitlines() if " read-bin-fallback:" in ln
    ]
    assert len(rb_lines) == 1, result.stdout
    fence_line = _line_of("read-bin-braced-no-guard", 'command "${ADLC_READ_BIN}"')
    assert (
        f"read-bin-braced-no-guard/SKILL.md:{fence_line}: read-bin-fallback:"
        in rb_lines[0]
    ), rb_lines
    assert 'case "$ADLC_READ_BIN" in /*)' in rb_lines[0]
    assert [
        ln for ln in result.stdout.splitlines() if "read-bin-guarded/SKILL.md" in ln
    ] == [], result.stdout


def test_read_bin_copied_into_another_variable_fires(tmp_path):
    """REQ-609 verify D3: one hop into another name → one finding.

    `READER="$ADLC_READ_BIN"` moves the resolver's answer into a variable no
    guard covers and no check knows the name of; the fence that follows reads
    as clean to every other obligation here. The finding is on the ASSIGNMENT,
    because that is the line that leaves the contract.
    """
    root = _stage(tmp_path, "read-bin-copied", "read-bin-guarded")
    result = _run(root)
    rb_lines = [
        ln for ln in result.stdout.splitlines() if " read-bin-fallback:" in ln
    ]
    assert len(rb_lines) == 1, result.stdout
    fence_line = _line_of("read-bin-copied", 'READER="$ADLC_READ_BIN"')
    assert (
        f"read-bin-copied/SKILL.md:{fence_line}: read-bin-fallback:" in rb_lines[0]
    ), rb_lines
    assert 'command "$ADLC_READ_BIN"' in rb_lines[0]
    assert [
        ln for ln in result.stdout.splitlines() if "read-bin-guarded/SKILL.md" in ln
    ] == [], result.stdout


def test_read_bin_handed_to_eval_fires(tmp_path):
    """REQ-609 verify D3: `eval "$ADLC_READ_BIN …"` → one finding.

    `eval` re-parses the string as shell source, which undoes the quoting AND
    puts function lookup back in play no matter what prefix is written inside
    it — so the value the resolver vouched for is resolved a second time, by
    the weaker rule, at the moment the corpus is handed over.
    """
    root = _stage(tmp_path, "read-bin-eval", "read-bin-guarded")
    result = _run(root)
    rb_lines = [
        ln for ln in result.stdout.splitlines() if " read-bin-fallback:" in ln
    ]
    assert len(rb_lines) == 1, result.stdout
    fence_line = _line_of("read-bin-eval", 'eval "$ADLC_READ_BIN')
    assert (
        f"read-bin-eval/SKILL.md:{fence_line}: read-bin-fallback:" in rb_lines[0]
    ), rb_lines
    assert 'command "$ADLC_READ_BIN"' in rb_lines[0]
    assert [
        ln for ln in result.stdout.splitlines() if "read-bin-guarded/SKILL.md" in ln
    ] == [], result.stdout


def test_read_bin_commented_guard_does_not_satisfy_the_ordering(tmp_path):
    """REQ-609 verify D3: a `#`-prefixed guard is not a guard.

    The literal is present character-for-character and runs nowhere. Reading it
    as the refusal makes the ordering obligation satisfiable by pasting a
    comment above the invocation, which is the guard-rot class LESSON-019 is
    about — a check anchored on text that no longer executes.
    """
    root = _stage(tmp_path, "read-bin-comment-guard", "read-bin-guarded")
    result = _run(root)
    rb_lines = [
        ln for ln in result.stdout.splitlines() if " read-bin-fallback:" in ln
    ]
    assert len(rb_lines) == 1, result.stdout
    fence_line = _line_of("read-bin-comment-guard", 'command "$ADLC_READ_BIN"')
    assert (
        f"read-bin-comment-guard/SKILL.md:{fence_line}: read-bin-fallback:"
        in rb_lines[0]
    ), rb_lines
    assert 'case "$ADLC_READ_BIN" in /*)' in rb_lines[0]
    assert [
        ln for ln in result.stdout.splitlines() if "read-bin-guarded/SKILL.md" in ln
    ] == [], result.stdout


def test_read_bin_retired_shapes_in_comments_are_clean(tmp_path):
    """REQ-609 verify D3: the other half of the comment rule — no false fire.

    A call site that was edited into the current shape ordinarily keeps the old
    one beside it, commented. Neither a commented invocation nor a commented
    `:-` default hands anything to anything, so neither is a finding — and the
    fence's live lines are the correct shape, so the whole fixture is clean.
    Staged with `read-bin-comment-guard`, which draws its finding in the SAME
    run: without that, "the comments drew nothing" would also be produced by a
    linter that had stopped running the check (LESSON-602).
    """
    root = _stage(tmp_path, "read-bin-comment-ok", "read-bin-comment-guard")
    result = _run(root)
    assert [
        ln for ln in result.stdout.splitlines() if "read-bin-comment-ok/SKILL.md" in ln
    ] == [], result.stdout
    assert [
        ln for ln in result.stdout.splitlines()
        if "read-bin-comment-guard/SKILL.md" in ln and " read-bin-fallback:" in ln
    ], result.stdout
    assert "scanned 2 SKILL.md file(s)" in result.stderr, result.stderr


def test_read_bin_fallback_walks_agents_and_nothing_else_does(tmp_path):
    """REQ-609: `read-bin-fallback` — and ONLY it — also scans `agents/*.md`.

    `agents/delegate-pre-pass.md` hands a redacted diff to the delegate exactly
    as a skill does and is not a `SKILL.md`, so the structural guard could not
    see the very fences BR-12 was written for. The walk is deliberately narrow,
    and both halves of that claim are asserted in one run:

    * the flagged agent fixture draws its `read-bin-fallback` finding, and the
      clean agent fixture draws none — an exclusion with a working subject;
    * neither agent file draws a `posix-fence` finding for the `local` in its
      `sh` fence, while `local-in-sh-fence` staged as a `SKILL.md` in the SAME
      run does. Without that control, "no posix-fence on agents" would also be
      produced by a linter that had stopped running `check_posix_fence` at all
      (LESSON-602).
    * the vacuous-scan count still counts `SKILL.md` files only, so agent files
      can never mask a dead skill walk (REQ-595 BR-5).
    """
    root = _stage(tmp_path, "read-bin-guarded", "local-in-sh-fence")
    _stage_agent(tmp_path, "read-bin-agent-fallback", "read-bin-agent-ok")
    result = _run(root)

    rb_lines = [
        ln for ln in result.stdout.splitlines() if " read-bin-fallback:" in ln
    ]
    assert len(rb_lines) == 1, result.stdout
    fence_line = _line_of("read-bin-agent-fallback", "ADLC_READ_BIN:-")
    assert rb_lines[0].startswith(
        f"agents/read-bin-agent-fallback.md:{fence_line}: read-bin-fallback:"
    ), rb_lines
    assert [
        ln for ln in result.stdout.splitlines() if "read-bin-agent-ok.md" in ln
    ] == [], result.stdout

    posix_lines = [
        ln for ln in result.stdout.splitlines() if " posix-fence:" in ln
    ]
    assert posix_lines, (
        "no posix-fence finding at all — the scoping assertion below would pass "
        "against a linter that had stopped running the check"
    )
    assert all("agents/" not in ln for ln in posix_lines), posix_lines

    assert "scanned 2 SKILL.md file(s)" in result.stderr, result.stderr


def _unguarded_lines(result) -> list[str]:
    return [ln for ln in result.stdout.splitlines() if " unguarded-source:" in ln]


def test_unguarded_source_flags_retired_and_chain_forms(tmp_path):
    """REQ-610 BR-3/BR-5: every non-canonical way of sourcing a partial inside a
    shell fence is a finding, on the offending line.

    Seven shapes, seven findings, and each carries information the others do not
    (the fifth, the bash-only ``source`` spelling, is silent degradation under
    ``dash``, which has no ``source`` builtin at all):

    * the retired two-level spelling in an ``sh`` fence — the shape that made
      `/architect` Step 5 die at its first line under `/bin/sh`;
    * the SAME line in a ``bash`` fence — unlike `posix-fence`, ``bash`` is NOT
      exempt (ADR-2): the label does not choose the shell that runs the block;
    * the ``&&``/``||`` chain, which reads as guarded and double-sources when
      the repo-local copy's final status is non-zero;
    * a guard whose ``<name>`` does not match what it sources — the assertion
      that `CANONICAL_SOURCE_RE`'s backreference is load-bearing;
    * the bash-only ``source`` spelling of the retired line;
    * the ``${HOME}`` operand spelling — the canonical form never uses it, so the
      regex branch that recognises it is otherwise unexercised;
    * a quoted operand (``. ".adlc/partials/x.sh"``) — the optional-quote branch.

    REQ-669 BR-5 adds three must-fire shapes of the ToolkitRoot operand
    ``"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"``, each in a fence that carries the
    root line (so ``toolkit-root-line`` is silent): ``||``-chained behind the
    repo-local copy, sourced alone with no repo-local arm, and guarded with a
    mismatched ``<name>`` (the backreference holds for the new operand too).

    REQ-669 TASK-124 adds the eleventh: the guarded REQ-610 spelling, whose
    ``else`` arm is ``~/.claude/skills/partials/<name>.sh``. TASK-122 accepted
    it while the corpus was rewritten; it is now a finding like the rest.

    The retired lines (both operands) match BOTH of the check's rules; the exact
    count is what proves the per-line dedupe (one finding, not two).
    """
    root = _stage(tmp_path, "unguarded-source-fence")
    result = _run(root)
    assert result.returncode == 11, result.stdout + result.stderr

    lines = _unguarded_lines(result)
    assert len(lines) == 11, result.stdout
    sh_retired = _line_of(
        "unguarded-source-fence", "2>/dev/null || . ~/.claude/skills/partials/forge.sh"
    )
    bash_retired = _line_of("unguarded-source-fence", "partials/intake.sh 2>/dev/null")
    chain = _line_of("unguarded-source-fence", "] && . .adlc/partials/id-alloc.sh")
    mismatch = _line_of(
        "unguarded-source-fence", "else . ~/.claude/skills/partials/intake.sh; fi"
    )
    source_spelling = _line_of("unguarded-source-fence", "source .adlc/partials/forge.sh")
    home_spelling = _line_of("unguarded-source-fence", "${HOME}/.claude/skills/partials/forge.sh")
    quoted = _line_of("unguarded-source-fence", '. ".adlc/partials/forge.sh"')
    new_chained = _line_of(
        "unguarded-source-fence", '2>/dev/null || . "$ADLC_TOOLKIT_ROOT/partials/lane-check.sh"'
    )
    new_alone = _line_of(
        "unguarded-source-fence", '. "$ADLC_TOOLKIT_ROOT/partials/conflict-bound.sh"'
    )
    new_mismatch = _line_of(
        "unguarded-source-fence", 'else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi'
    )
    old_operand = _line_of(
        "unguarded-source-fence", "else . ~/.claude/skills/partials/forge.sh; fi"
    )
    assert [
        sh_retired, bash_retired, chain, mismatch, source_spelling, home_spelling,
        quoted, new_chained, new_alone, new_mismatch, old_operand,
    ] == sorted(int(ln.split(":")[1]) for ln in lines), lines
    for ln in lines:
        assert ln.startswith("unguarded-source-fence/SKILL.md:"), ln
        assert "conventions.md 'Bash in skills'" in ln, ln
        # Every message names the ToolkitRoot spelling, never the retired one.
        assert '"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"' in ln, ln
        assert "~/.claude/skills/partials/<name>.sh" not in ln, ln
    # The whole finding set is unguarded-source — no collateral from another
    # check, so the counts above mean what they say.
    assert len(result.stdout.strip().splitlines()) == 11, result.stdout


def test_unguarded_source_flags_prose_occurrence(tmp_path):
    """REQ-610 BR-5 rule 2: the retired spelling in PROSE is a finding, reported
    at the prose line.

    `analyze/SKILL.md` Step 1.5 carried a sentence telling the agent to type the
    retired line — as executable as a fence, since the agent types what the
    sentence says. The fences in this fixture are all canonical, so the finding
    can only come from the prose pass.
    """
    root = _stage(tmp_path, "unguarded-source-prose")
    result = _run(root)
    assert result.returncode == 2, result.stdout + result.stderr

    lines = _unguarded_lines(result)
    assert len(lines) == 2, result.stdout
    prose_line = _line_of("unguarded-source-prose", "source the adapter with")
    assert lines[0].startswith(
        f"unguarded-source-prose/SKILL.md:{prose_line}: unguarded-source:"
    ), lines
    assert "conventions.md 'Bash in skills'" in lines[0], lines
    # The aligned variant is the reason RETIRED_SOURCE_RE is whitespace-tolerant
    # rather than a fixed string: locate it, do not merely count it.
    aligned_line = _line_of("unguarded-source-prose", "2>/dev/null  ||  . ~/")
    assert lines[1].startswith(
        f"unguarded-source-prose/SKILL.md:{aligned_line}: unguarded-source:"
    ), lines


def test_guarded_source_ok_is_clean(tmp_path):
    """REQ-610 BR-5 benign path: the canonical spelling (in ``sh``, ``bash`` and
    ``shell`` fences, indented, and with a trailing comment), the
    executable-partial ``sh <local> ... || sh <canonical>`` macro, and a comment
    line naming a partial all produce ZERO findings. REQ-669: every guarded
    line uses the ToolkitRoot operand behind its fence's root line. TASK-124
    dropped the REQ-610 operand from this fixture; it is must-fire now, in
    ``unguarded-source-fence``.

    Staged a second time ALONGSIDE the negative fixture, so "clean" cannot be
    produced by a linter that had stopped running the check at all
    (LESSON-602): the same run must still report the eleven bad lines.
    """
    fixture = (FIXTURES / "guarded-source-ok.md").read_text(encoding="utf-8")
    assert 'else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi' in fixture
    assert "else . ~/.claude/skills/partials/" not in fixture

    alone = tmp_path / "alone"
    alone.mkdir()
    _stage(alone, "guarded-source-ok")
    result = _run(alone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "", result.stdout

    both = tmp_path / "both"
    both.mkdir()
    _stage(both, "guarded-source-ok", "unguarded-source-fence")
    result = _run(both)
    lines = _unguarded_lines(result)
    assert len(lines) == 11, result.stdout
    assert all("unguarded-source-fence/" in ln for ln in lines), lines
    assert "guarded-source-ok" not in result.stdout, result.stdout


def test_old_operand_now_fires(tmp_path):
    """REQ-669 TASK-124 (BR-2): the REQ-610 fallback operand
    ``~/.claude/skills/partials/<name>.sh`` is no longer accepted. TASK-122
    accepted it beside the ToolkitRoot operand while the corpus was rewritten;
    TASK-124 rewrote the corpus and retired that acceptance, so the guarded
    REQ-610 spelling is an ``unguarded-source`` finding on every surface the
    check walks: a SKILL.md fence, an ``agents/*.md`` fence, a
    ``proceed/phase*.md`` fence, and a ``partials/*.sh`` line. The message
    names the new spelling, and says the guard is fine and the operand is not.

    The same line behind the fence's root line (a half-finished rewrite) fires
    too. Benign control (LESSON-440): the ToolkitRoot spelling in the same
    places is clean, in the same run's shape.
    """
    old_line = _check.guarded_source_line("forge", _check.RETIRED_REQ610_OPERAND)
    assert old_line == (
        "if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; "
        "else . ~/.claude/skills/partials/forge.sh; fi"
    )
    old_partial = _check.guarded_source_line("intake", _check.RETIRED_REQ610_OPERAND)

    bad = tmp_path / "bad"
    (bad / "old-operand").mkdir(parents=True)
    (bad / "old-operand" / "SKILL.md").write_text(
        "# Old operand\n\n```sh\n" + old_line + "\n```\n\n"
        "Behind the root line, as a half-finished rewrite would leave it.\n\n"
        "```sh\n" + _check.TOOLKIT_ROOT_LINE + "\n" + old_line + "\n```\n",
        encoding="utf-8",
    )
    (bad / "agents").mkdir()
    (bad / "agents" / "some-agent.md").write_text(
        "# Agent\n\n```sh\n" + old_line + "\n```\n", encoding="utf-8"
    )
    (bad / "proceed").mkdir()
    (bad / "proceed" / "phases-x.md").write_text(
        "# Phase\n\n```sh\n" + old_line + "\n```\n", encoding="utf-8"
    )
    (bad / "partials").mkdir()
    (bad / "partials" / "some-partial.sh").write_text(
        "#!/bin/sh\n" + old_partial + "\n", encoding="utf-8"
    )
    result = _run(bad)
    lines = _unguarded_lines(result)
    assert sorted(ln.split(": unguarded-source:")[0] for ln in lines) == sorted([
        "agents/some-agent.md:4",
        "old-operand/SKILL.md:4",
        "old-operand/SKILL.md:11",
        "partials/some-partial.sh:2",
        "proceed/phases-x.md:4",
    ]), result.stdout
    for ln in lines:
        assert "retired REQ-610 operand" in ln, ln
        assert "~/.claude/skills/partials/<name>.sh" not in ln, ln
        if ln.startswith("partials/"):
            # A partial has no root line: it is offered the ADR-2 spelling.
            assert _check.guarded_source_line("<name>", _check.PARTIAL_SOURCE_OPERAND) in ln, ln
        else:
            assert _check.GUARDED_SOURCE_SPELLING in ln, ln
    # unguarded-source is the only check that fires: the old operand reads no
    # ToolkitRoot, so `toolkit-root-line` has nothing to say about it.
    assert len(result.stdout.strip().splitlines()) == 5, result.stdout
    assert result.returncode == 5, result.stdout + result.stderr

    good = tmp_path / "good"
    (good / "new-operand").mkdir(parents=True)
    fence = "```sh\n" + _check.TOOLKIT_ROOT_LINE + "\n" + _check.guarded_source_line("forge") + "\n```\n"
    (good / "new-operand" / "SKILL.md").write_text("# New operand\n\n" + fence, encoding="utf-8")
    (good / "agents").mkdir()
    (good / "agents" / "some-agent.md").write_text("# Agent\n\n" + fence, encoding="utf-8")
    (good / "proceed").mkdir()
    (good / "proceed" / "phases-x.md").write_text("# Phase\n\n" + fence, encoding="utf-8")
    (good / "partials").mkdir()
    (good / "partials" / "some-partial.sh").write_text(
        "#!/bin/sh\n" + _check.guarded_source_line("intake", _check.PARTIAL_SOURCE_OPERAND) + "\n",
        encoding="utf-8",
    )
    result = _run(good)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "", result.stdout

    # The accepted sets hold the ToolkitRoot operand alone (plus, in a partial,
    # the ADR-2 default-expansion one), and the transitional constant is gone.
    assert _check.ACCEPTED_SOURCE_OPERANDS == ('"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"',)
    assert _check.PARTIAL_ACCEPTED_SOURCE_OPERANDS == (
        '"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"',
        _check.PARTIAL_SOURCE_OPERAND,
    )
    assert not hasattr(_check, "TRANSITIONAL_OLD_OPERAND")


def test_repo_root_unguarded_source_and_root_line_clean():
    """REQ-669 TASK-124 (BR-2, BR-10): on the real tree, after the corpus
    rewrite, ``unguarded-source`` and ``toolkit-root-line`` report nothing, and
    neither do ``canonical-helper`` and ``sentinel`` (the rewrite moved the two
    delegate-* source literals, and touched no skill reference). Every
    top-level ``*/SKILL.md`` is walked, so the zero is over the whole corpus
    and not over an empty walk (REQ-595 BR-5, LESSON-019).

    A nested worktree under ``.claude/worktrees/`` is another checkout's tree;
    the walk itself leaves it out (BUG-254), so no output line is filtered here.
    """
    result = _run(REPO_ROOT)
    own = [ln for ln in result.stdout.splitlines() if ln.strip()]
    for check_id in ("unguarded-source", "toolkit-root-line", "canonical-helper", "sentinel"):
        hits = [ln for ln in own if f": {check_id}:" in ln]
        assert hits == [], "\n".join(hits)

    skills = sorted(p.parent.name for p in REPO_ROOT.glob("*/SKILL.md"))
    assert len(skills) >= 1
    walked = sorted(
        p.relative_to(REPO_ROOT).parts[0]
        for p in _check.find_skill_files(REPO_ROOT)
        if len(p.relative_to(REPO_ROOT).parts) == 2
    )
    assert walked == skills
    scanned = len(list(_check.find_skill_files(REPO_ROOT)))
    assert f"scanned {scanned} SKILL.md file(s)" in result.stderr, result.stderr


def test_unguarded_source_walks_phase_files_without_counting_them(tmp_path):
    """REQ-610 BR-12 / ADR-3: `proceed/phase*.md` is walked by
    `unguarded-source`, and is NOT counted toward `scanned N SKILL.md file(s)`.

    Both halves matter and are asserted in two runs:

    * staged ALONE, the phase file's finding is reported but the run still exits
      255 VACUOUS — a companion file can never stand in for a skill walk, so a
      dead `SKILL.md` walk cannot be masked (REQ-595 BR-5);
    * staged beside one clean `SKILL.md`, the finding is reported at its line
      and the scanned figure is 1, not 2.
    """
    alone = tmp_path / "alone"
    alone.mkdir()
    _stage_phase(alone, "phase-file-unguarded", dest_name="phases-6-8-ship.md")
    result = _run(alone)
    assert result.returncode == 255, result.stdout + result.stderr
    assert "VACUOUS SCAN" in result.stderr, result.stderr
    assert "scanned 0 SKILL.md file(s)" in result.stderr, result.stderr
    assert len(_unguarded_lines(result)) == 1, result.stdout

    with_skill = tmp_path / "with_skill"
    with_skill.mkdir()
    _stage(with_skill, "clean")
    _stage_phase(with_skill, "phase-file-unguarded", dest_name="phases-6-8-ship.md")
    result = _run(with_skill)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "VACUOUS SCAN" not in result.stderr, result.stderr
    assert "scanned 1 SKILL.md file(s)" in result.stderr, result.stderr

    lines = _unguarded_lines(result)
    assert len(lines) == 1, result.stdout
    fence_line = _line_of("phase-file-unguarded", "2>/dev/null")
    assert lines[0].startswith(
        f"proceed/phases-6-8-ship.md:{fence_line}: unguarded-source:"
    ), lines


def test_old_delegate_gate_spelling_fails_canonical_and_unguarded(tmp_path):
    """REQ-610 BR-6 / ADR-4: a SKILL.md that kept the OLD spelling of the
    delegate-gate source line is reported TWICE over — once by
    `canonical-helper` (the literal moved) and once by `unguarded-source` (the
    shape is retired).

    This is the deliberate old-shape negative case: it is what proves the
    `CANONICAL_LITERALS` entry genuinely moved to the guarded spelling rather
    than being widened to accept both (REQ-436 ADR-4 / LESSON-019 #1). REQ-669
    moves the entry to the ToolkitRoot operand (TASK-124 retired the
    transitional REQ-610 one); the retired shape is still not it. Every
    other literal in the file is present — the tools-path source line, the
    start_s mark, the resolver call, and (via the staged partial) the
    emit-telemetry exec — so `canonical-helper == 1` names the gate line alone.
    """
    sub = tmp_path / "old-gate-spelling"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "# The post-REQ-522 telemetry shape with ONE retired source line.\n\n"
        "```sh\n"
        + _check.TOOLKIT_ROOT_LINE + "\n"
        # The deliberate old shape under test — the only retired delegate-*
        # source line left anywhere in this suite (REQ-610 BR-6).
        ". .adlc/partials/delegate-gate.sh 2>/dev/null || "
        ". ~/.claude/skills/partials/delegate-gate.sh\n"
        + _check.guarded_source_line("delegate-tools-path") + "\n"
        'flag=$("$DELEGATE_TOOLS"/skill-flag.sh create)\n'
        '"$DELEGATE_TOOLS"/skill-flag.sh mark "$flag" start_s "$(date -u +%s)"\n'
        + _check.guarded_source_line("emit-step-telemetry") + "\n"
        "_adlc_emit_step_telemetry some-skill Some-Step\n"
        "# anchor: ADLC_DISABLE_DELEGATE gate-case comment\n"
        "```\n",
        encoding="utf-8",
    )
    _stage_partial(tmp_path, layout="partials")
    result = _run(tmp_path)

    assert result.stdout.count("canonical-helper") == 1, result.stdout
    assert "if [ -f .adlc/partials/delegate-gate.sh ]; then" in result.stdout
    # The retired spelling is what the file HAS, so it must not be what the
    # canonical check ASKS for.
    assert "canonical-helper: missing required literal" in result.stdout

    lines = _unguarded_lines(result)
    assert len(lines) == 1, result.stdout
    body = (sub / "SKILL.md").read_text().splitlines()
    # `2>/dev/null ||`, not `2>/dev/null`: the root line's pointer arm carries one.
    old_line = next(i + 1 for i, ln in enumerate(body) if "2>/dev/null ||" in ln)
    assert lines[0].startswith(
        f"old-gate-spelling/SKILL.md:{old_line}: unguarded-source:"
    ), lines


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
    # A real in-root skill keeps the scan non-vacuous, so this asserts
    # "the descendant was skipped" rather than the weaker "nothing was found"
    # (which a broken walker also satisfies — and which REQ-595's guard now
    # reports as status 255).
    real = tmp_path / "realskill"
    real.mkdir()
    shutil.copyfile(FIXTURES / "clean.md", real / "SKILL.md")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "", result.stdout
    assert "scanned 1 SKILL.md file(s)" in result.stderr, result.stderr


def test_nested_session_worktree_skipped(tmp_path):
    """BUG-254: a desktop-app session worktree at `.claude/worktrees/<name>/`
    below the scan root is another checkout and is not walked. Its planted
    violation is not reported and its SKILL.md is not counted. A SKILL.md
    elsewhere under `.claude/` is still walked, so only the
    `.claude/worktrees` pair is skipped, not all of `.claude/`.
    """
    nested = tmp_path / ".claude" / "worktrees" / "x" / "alpha"
    nested.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "corrupt-sentinel.md", nested / "SKILL.md")
    project = tmp_path / ".claude" / "skills" / "beta"
    project.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "clean.md", project / "SKILL.md")
    real = tmp_path / "realskill"
    real.mkdir()
    shutil.copyfile(FIXTURES / "clean.md", real / "SKILL.md")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "", result.stdout
    assert "scanned 2 SKILL.md file(s)" in result.stderr, result.stderr


def test_root_inside_session_worktree_still_scanned(tmp_path):
    """BUG-254 bound (LESSON-019, REQ-436 ADR-5): the skip applies below the
    scan root only. A root that itself sits inside `.claude/worktrees/<name>`
    (every desktop-app session lints from there) is scanned in full, so its
    planted violation is reported rather than a vacuous exit 255.
    """
    root = tmp_path / ".claude" / "worktrees" / "x"
    skill = root / "alpha"
    skill.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "corrupt-sentinel.md", skill / "SKILL.md")

    result = _run(root)
    assert 0 < result.returncode < 255, result.stdout + result.stderr
    assert "alpha/SKILL.md:" in result.stdout, result.stdout
    assert "sentinel" in result.stdout, result.stdout
    assert "scanned 1 SKILL.md file(s)" in result.stderr, result.stderr


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


# --- REQ-595 BR-5 / AC-7: the vacuous-run guard -----------------------------
#
# REQ-435 fixed the vacuous *walk* (a root sitting under `.worktrees` is no
# longer skipped into oblivion). These cases guard the vacuous *result*: a
# scan that walked zero files must not report success, because a clean result
# from a scan that checked nothing is a confident green proving nothing.
#
# Both directions are covered on purpose. A guard exercised only against its
# firing input can be unconditionally broken and still pass its own suite
# (LESSON-440) — so the benign case below is as load-bearing as the failing one.


def test_empty_root_is_a_vacuous_scan_not_a_pass(tmp_path):
    """AC-7: pointing the check at an empty directory reports failure."""
    result = _run(tmp_path)
    # Distinct from an ordinary findings count, so a caller can tell
    # "scanned nothing" from "found N problems".
    assert result.returncode == 255, result.stdout + result.stderr
    assert "VACUOUS SCAN" in result.stderr, result.stderr
    assert "scanned 0 SKILL.md file(s)" in result.stderr, result.stderr
    # No findings were invented to justify the failure.
    assert result.stdout.strip() == "", result.stdout


def test_populated_clean_root_still_passes(tmp_path):
    """BR-5 benign path (LESSON-440): the guard must NOT fire on a root that
    genuinely has skill files and genuinely has nothing wrong with them. This
    is the case that fails if the guard is wired to reject unconditionally."""
    root = _stage(tmp_path, "clean")
    result = _run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "VACUOUS SCAN" not in result.stderr, result.stderr
    assert "scanned 1 SKILL.md file(s)" in result.stderr, result.stderr


def test_root_of_only_skipped_dirs_is_vacuous(tmp_path):
    """A root whose only SKILL.md files live under skipped directories walks
    zero files — the same confident green as an empty root, reached by a
    different branch. Distinct from `test_empty_root_...`: here the files
    exist and are deliberately excluded, which is precisely the shape of the
    REQ-435 near-miss."""
    buried = tmp_path / "node_modules" / "someskill"
    buried.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "corrupt-sentinel.md", buried / "SKILL.md")

    result = _run(tmp_path)
    assert result.returncode == 255, result.stdout + result.stderr
    assert "VACUOUS SCAN" in result.stderr, result.stderr
    # The corrupt buried file was genuinely not scanned, not merely unreported.
    assert "sentinel" not in result.stdout, result.stdout


def test_scanned_count_is_reported_on_every_run(tmp_path):
    """BR-5: the work-done figure is emitted, not left to be inferred from a
    green exit — including on a run that DOES have findings."""
    root = _stage(tmp_path, "clean", "corrupt-sentinel")
    result = _run(root)
    assert result.returncode > 0, result.stdout
    assert "scanned 2 SKILL.md file(s)" in result.stderr, result.stderr


def test_unguarded_source_walks_partials_in_both_layouts_without_counting_them(tmp_path):
    """REQ-610 (find_partial_files): a partial that dot-sources another partial is
    walked in BOTH layouts (`partials/` and `.adlc/partials/`), an unguarded line
    is a finding, the canonical line is not, and neither layout counts toward the
    SKILL.md scanned figure. The unguarded shape here is the multi-line chain
    id-recheck.sh actually carried — continuation lines beginning with `||` —
    which no line-anchored extraction sees.

    REQ-669: the same continuation chain with the ToolkitRoot operand is a
    finding too (`bad-new.sh`), and the guarded line with the ToolkitRoot
    operand or the ADR-2 default-expansion one is not (`ok.sh`; the REQ-610
    operand was retired by TASK-124, `test_old_operand_now_fires`). A partial reads the root through the ADR-2 default-expansion
    spelling and carries no root line, so `toolkit-root-line` never walks
    `partials/*.sh` — `ok.sh` reads the variable with no root line and is clean.
    """
    _stage(tmp_path, "clean")
    (tmp_path / "partials").mkdir()
    (tmp_path / ".adlc" / "partials").mkdir(parents=True)
    bad = (
        "#!/bin/sh\n"
        "# header comment quoting `. .adlc/partials/x.sh` is not a source\n"
        "f() {\n"
        "  { [ -n \"$D\" ] && . \"$D/id-alloc.sh\" 2>/dev/null; } \\\n"
        "    || . .adlc/partials/id-alloc.sh 2>/dev/null \\\n"
        "    || . ~/.claude/skills/partials/id-alloc.sh 2>/dev/null \\\n"
        "    || return 2\n"
        "}\n"
    )
    bad_new = (
        "#!/bin/sh\n"
        "f() {\n"
        "  . .adlc/partials/id-alloc.sh 2>/dev/null \\\n"
        "    || . \"$ADLC_TOOLKIT_ROOT/partials/id-alloc.sh\"\n"
        "}\n"
    )
    ok = (
        "#!/bin/sh\n"
        "if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; "
        "else . \"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/delegate-tools-path.sh\"; fi\n"
        "if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; "
        "else . \"$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh\"; fi\n"
        "engine=\"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/lane_check.py\"\n"
    )
    (tmp_path / "partials" / "bad.sh").write_text(bad, encoding="utf-8")
    (tmp_path / ".adlc" / "partials" / "also-bad.sh").write_text(bad, encoding="utf-8")
    (tmp_path / "partials" / "bad-new.sh").write_text(bad_new, encoding="utf-8")
    (tmp_path / "partials" / "ok.sh").write_text(ok, encoding="utf-8")
    result = _run(tmp_path)
    out = result.stdout
    assert "partials/bad.sh:5: unguarded-source" in out
    assert "partials/bad.sh:6: unguarded-source" in out
    assert ".adlc/partials/also-bad.sh:5: unguarded-source" in out
    assert "partials/bad-new.sh:3: unguarded-source" in out
    assert "partials/bad-new.sh:4: unguarded-source" in out
    assert "partials/ok.sh" not in out
    assert "bad.sh:2:" not in out  # the header comment is not a source
    assert "toolkit-root-line" not in out, out
    assert "scanned 1 SKILL.md file(s)" in result.stderr
    # 2 findings x 2 copies + 2 in bad-new.sh; partials never inflate `scanned`.
    assert result.returncode == 6, out


def test_partial_default_expansion_operand_accepted_only_inside_partials(tmp_path):
    """REQ-669 ADR-2 (TASK-123): a partial sourcing another partial has no root
    line, and a test harness may source it with no ToolkitRoot set, so its
    guarded line ends in the default-expansion operand
    ``PARTIAL_SOURCE_OPERAND``. That line is clean in ``partials/*.sh`` (benign
    path) and a finding in a SKILL.md fence, which has its root line. The
    operand sourced without the guard, guarded under a different ``<name>``, or
    behind the retired ``2>/dev/null ||`` is a finding in a partial too, and the
    retired shape is one in prose.
    """
    assert _check.PARTIAL_SOURCE_OPERAND == (
        '"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/<name>.sh"'
    )
    op = _check.PARTIAL_SOURCE_OPERAND
    ok_line = _check.guarded_source_line("id-alloc", op)
    (tmp_path / "partials").mkdir()
    (tmp_path / "partials" / "ok.sh").write_text(
        "#!/bin/sh\n" + ok_line + "\n" + "  " + ok_line + "  # indented, commented\n",
        encoding="utf-8",
    )
    bad = (
        "#!/bin/sh\n"
        + '. "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/id-alloc.sh"\n'
        + ok_line.replace("partials/id-alloc.sh\"", "partials/forge.sh\"") + "\n"
        + '. .adlc/partials/x.sh 2>/dev/null || . "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/x.sh"\n'
        + '. "${ADLC_TOOLKIT_ROOT:-~/.claude/skills}/partials/x.sh"\n'
    )
    (tmp_path / "partials" / "bad.sh").write_text(bad, encoding="utf-8")
    sub = tmp_path / "fence-default-operand"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "# Default operand in a fence\n\n"
        "Never type `x 2>/dev/null || . \"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/x.sh\"`.\n\n"
        "```sh\n" + _check.TOOLKIT_ROOT_LINE + "\n" + ok_line + "\n```\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    out = result.stdout
    lines = _unguarded_lines(result)
    assert "partials/ok.sh" not in out, out
    assert "partials/bad.sh:2: unguarded-source" in out, out
    assert "partials/bad.sh:3: unguarded-source" in out, out
    assert "partials/bad.sh:4: unguarded-source" in out, out
    assert "partials/bad.sh:5: unguarded-source" in out, out
    assert "fence-default-operand/SKILL.md:3: unguarded-source" in out, out
    assert "fence-default-operand/SKILL.md:7: unguarded-source" in out, out
    assert len(lines) == 6, out
    assert "toolkit-root-line" not in out, out


def test_unguarded_source_walks_partials_companion_docs(tmp_path):
    """REQ-610 (review): `partials/*.md` — the companion docs whose copy-paste
    fences are where a call-site spelling ORIGINATES — are walked by
    `unguarded-source` (via find_phase_files) and do not count as SKILL.md.
    """
    _stage(tmp_path, "clean")
    (tmp_path / "partials").mkdir()
    doc = (
        "# forge.md\n\nSource it like this:\n\n```sh\n"
        ". .adlc/partials/forge.sh 2>/dev/null || . ~/.claude/skills/partials/forge.sh\n"
        "adlc_forge_pr_view 1\n```\n"
    )
    (tmp_path / "partials" / "forge.md").write_text(doc, encoding="utf-8")
    result = _run(tmp_path)
    assert "partials/forge.md:6: unguarded-source" in result.stdout, result.stdout
    assert "scanned 1 SKILL.md file(s)" in result.stderr
    assert result.returncode == 1


def test_new_walks_skip_symlinks_that_escape_root(tmp_path):
    """REQ-610 (review): `find_phase_files` and `find_partial_files` carry the
    same symlink-escape guard as the SKILL.md walk — proven, not just stated.
    A `proceed/phases-x.md` and a `partials/x.sh` that are symlinks to files
    OUTSIDE the scan root (each carrying an unguarded line) are skipped; their
    in-root counterparts with the same content are reported.
    """
    _stage(tmp_path, "clean")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    bad_fence = "```sh\n. .adlc/partials/forge.sh 2>/dev/null || . ~/.claude/skills/partials/forge.sh\n```\n"
    bad_sh = "#!/bin/sh\n. .adlc/partials/forge.sh 2>/dev/null || . ~/.claude/skills/partials/forge.sh\n"
    (outside / "escaped-phase.md").write_text(bad_fence, encoding="utf-8")
    (outside / "escaped.sh").write_text(bad_sh, encoding="utf-8")
    (tmp_path / "proceed").mkdir()
    (tmp_path / "partials").mkdir()
    (tmp_path / "proceed" / "phases-escaped.md").symlink_to(outside / "escaped-phase.md")
    (tmp_path / "partials" / "escaped.sh").symlink_to(outside / "escaped.sh")
    (tmp_path / "proceed" / "phases-real.md").write_text(bad_fence, encoding="utf-8")
    (tmp_path / "partials" / "real.sh").write_text(bad_sh, encoding="utf-8")
    result = _run(tmp_path)
    out = result.stdout
    assert "proceed/phases-real.md:2: unguarded-source" in out, out
    assert "partials/real.sh:2: unguarded-source" in out, out
    assert "escaped" not in out, out
    assert result.returncode == 2, out + result.stderr


# ---------------------------------------------------------------------------
# REQ-669 ADR-1: `toolkit-root-line`. A fence that reads $ADLC_TOOLKIT_ROOT
# carries the canonical root line, byte-exact, before its first read.
# ---------------------------------------------------------------------------


def _root_lines(result) -> list[str]:
    return [ln for ln in result.stdout.splitlines() if " toolkit-root-line:" in ln]


def _fixture_lines_equal(fixture_name: str, needle: str) -> list[int]:
    """1-based numbers of every line of a fixture that CONTAINS `needle`."""
    lines = (FIXTURES / f"{fixture_name}.md").read_text(encoding="utf-8").splitlines()
    return [i + 1 for i, ln in enumerate(lines) if needle in ln]


def test_toolkit_root_line_fixtures_carry_the_pinned_bytes():
    """The fixtures spell the root line out by hand. If the constant ever moves,
    every root line in them must move with it, or the fixtures would test a
    spelling the linter no longer pins (LESSON-019)."""
    for name in ("toolkit-root-line-ok", "toolkit-root-line-missing",
                 "guarded-source-ok", "unguarded-source-fence"):
        text = (FIXTURES / f"{name}.md").read_text(encoding="utf-8")
        assert _check.TOOLKIT_ROOT_LINE in text, name


def test_toolkit_root_line_ok_is_clean(tmp_path):
    """Benign path (LESSON-440): the root line before the first read, in `sh`,
    `bash` and indented `shell` fences, braced and unbraced reads, a comment
    naming the variable above the line, a second fence with its own root line,
    a fence that never names the variable, prose mentions and a `text` fence
    showing a variant — zero findings. Staged again beside the must-fire fixture
    so "clean" cannot come from a check that stopped running (LESSON-602)."""
    alone = tmp_path / "alone"
    alone.mkdir()
    _stage(alone, "toolkit-root-line-ok")
    result = _run(alone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "", result.stdout

    both = tmp_path / "both"
    both.mkdir()
    _stage(both, "toolkit-root-line-ok", "toolkit-root-line-missing")
    result = _run(both)
    lines = _root_lines(result)
    assert len(lines) == 4, result.stdout
    assert all(ln.startswith("toolkit-root-line-missing/") for ln in lines), lines


def test_toolkit_root_line_missing_fires(tmp_path):
    """A read with no root line above it in the same fence is one finding per
    fence, on the first read: no root line at all, the root line only after the
    read, a braced read in a `bash` fence, and a read that leans on an earlier
    fence's root line. The earlier fence itself is clean."""
    root = _stage(tmp_path, "toolkit-root-line-missing")
    result = _run(root)
    assert result.returncode == 4, result.stdout + result.stderr
    lines = _root_lines(result)
    assert len(lines) == 4, result.stdout
    expected = sorted([
        _line_of("toolkit-root-line-missing", 'else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi'),
        _line_of("toolkit-root-line-missing", 'echo "root is $ADLC_TOOLKIT_ROOT"'),
        _line_of("toolkit-root-line-missing", 'python3 "${ADLC_TOOLKIT_ROOT}/tools'),
        _line_of("toolkit-root-line-missing", "templates/across-fences"),
    ])
    assert [int(ln.split(":")[1]) for ln in lines] == expected, lines
    for ln in lines:
        assert "no root line above it in this fence" in ln, ln
        assert _check.TOOLKIT_ROOT_LINE in ln, ln  # the message names the fix
        assert "conventions.md 'Bash in skills'" in ln, ln
    assert len(result.stdout.strip().splitlines()) == 4, result.stdout


def test_toolkit_root_line_cross_fence_use_is_a_finding(tmp_path):
    """Architecture ADR-1 / task note: the root line is per fence by design, so
    `$ADLC_TOOLKIT_ROOT` set in fence 1 and read in fence 2 must still be a
    finding. `cross-fence-var` exempts exported names, and the root line
    exports, so it is `toolkit-root-line` that reports the read — on fence 2's
    read line, not on fence 1."""
    sub = tmp_path / "two-fences"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "# Two fences\n\n```sh\n"
        + _check.TOOLKIT_ROOT_LINE + "\n"
        + _check.guarded_source_line("forge") + "\n"
        "```\n\nLater:\n\n```sh\n"
        'ls "$ADLC_TOOLKIT_ROOT/templates"\n'
        "```\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    lines = _root_lines(result)
    assert len(lines) == 1, result.stdout
    assert lines[0].startswith("two-fences/SKILL.md:11: toolkit-root-line:"), lines
    assert "cross-fence-var" not in result.stdout, result.stdout
    assert result.returncode == 1, result.stdout + result.stderr


def test_toolkit_root_line_variant_fails(tmp_path):
    """BR-4: a variant of the root line is a finding, on the variant line — a
    dropped character, a changed character, a trailing space, the rejected
    `${CLAUDE_PLUGIN_ROOT:-…}` default form (Claude Code does not rewrite it,
    verification.md row 1), the unbraced token, and a re-assignment after a
    correct root line. The guarded source after each is canonical, so these
    six are the only findings."""
    root = _stage(tmp_path, "toolkit-root-line-variant")
    result = _run(root)
    assert result.returncode == 6, result.stdout + result.stderr
    lines = _root_lines(result)
    assert len(lines) == 6, result.stdout
    needles = (
        '"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skill}"',  # one character dropped
        '[ -z "$ADLC_TOOLKIT_ROOT" ]',                  # one character changed
        'skills}" ',                                    # one character added
        "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills}",  # the rejected default form
        'ADLC_TOOLKIT_ROOT="$CLAUDE_PLUGIN_ROOT"',      # the unbraced token
        "export ADLC_TOOLKIT_ROOT=/opt/elsewhere",      # re-assignment after the line
    )
    for needle in needles:  # each needle names exactly one line of the fixture
        assert len(_fixture_lines_equal("toolkit-root-line-variant", needle)) == 1, needle
    expected = sorted(_line_of("toolkit-root-line-variant", n) for n in needles)
    assert [int(ln.split(":")[1]) for ln in lines] == expected, (lines, expected)
    reassign = _line_of("toolkit-root-line-variant", "export ADLC_TOOLKIT_ROOT=/opt/elsewhere")
    for ln in lines:
        if ln.startswith(f"toolkit-root-line-variant/SKILL.md:{reassign}:"):
            assert "re-assigns ADLC_TOOLKIT_ROOT after the root line" in ln, ln
        else:
            assert "is not the canonical root line (first difference at column" in ln, ln
    assert len(result.stdout.strip().splitlines()) == 6, result.stdout


def test_toolkit_root_line_every_one_char_edit_fails(tmp_path):
    """AC: a one-character variant of the root line fails `toolkit-root-line`.
    Not a sample: every single-character deletion and every single-character
    substitution of the pinned line, one skill each, in one scan. Each skill
    must carry exactly one `toolkit-root-line` finding. (A deletion inside
    `$(` can also draw a `balance` finding; only this check is counted.)"""
    line = _check.TOOLKIT_ROOT_LINE
    variants: set[str] = set()
    for i in range(len(line)):
        variants.add(line[:i] + line[i + 1:])
        variants.add(line[:i] + ("X" if line[i] != "X" else "Y") + line[i + 1:])
    variants.discard(line)
    tail = _check.guarded_source_line("forge")
    for n, variant in enumerate(sorted(variants)):
        sub = tmp_path / f"v{n:04d}"
        sub.mkdir()
        (sub / "SKILL.md").write_text(
            f"# variant {n}\n\n```sh\n{variant}\n{tail}\n```\n", encoding="utf-8"
        )
    result = _run(tmp_path)
    assert f"scanned {len(variants)} SKILL.md file(s)" in result.stderr, result.stderr
    per_skill: dict[str, int] = {}
    for ln in _root_lines(result):
        per_skill[ln.split("/", 1)[0]] = per_skill.get(ln.split("/", 1)[0], 0) + 1
    missed = sorted(f"v{n:04d}" for n in range(len(variants)) if per_skill.get(f"v{n:04d}") != 1)
    assert not missed, [
        (name, sorted(variants)[int(name[1:])]) for name in missed[:5]
    ]


def test_toolkit_root_line_walks_agents_and_companion_files_not_partials(tmp_path):
    """`toolkit-root-line` walks the same markdown families as
    `unguarded-source` — `agents/*.md`, `proceed/phase*.md` and the partials'
    companion docs `partials/*.md` — none of which count toward `scanned`. It
    does NOT walk `partials/*.sh`, which read the root through the ADR-2
    default-expansion spelling and never carry the root line."""
    _stage(tmp_path, "clean")
    _stage_agent(tmp_path, "toolkit-root-line-missing")
    _stage_phase(tmp_path, "toolkit-root-line-missing", dest_name="phases-6-8-ship.md")
    (tmp_path / "partials").mkdir()
    shutil.copyfile(FIXTURES / "toolkit-root-line-missing.md", tmp_path / "partials" / "forge.md")
    (tmp_path / "partials" / "lane-check.sh").write_text(
        "#!/bin/sh\n"
        'engine="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/lane_check.py"\n'
        'python3 "$engine" "$ADLC_TOOLKIT_ROOT"\n',
        encoding="utf-8",
    )
    result = _run(tmp_path)
    lines = _root_lines(result)
    by_file: dict[str, int] = {}
    for ln in lines:
        by_file[ln.split(":", 1)[0]] = by_file.get(ln.split(":", 1)[0], 0) + 1
    assert by_file == {
        "agents/toolkit-root-line-missing.md": 4,
        "proceed/phases-6-8-ship.md": 4,
        "partials/forge.md": 4,
    }, result.stdout
    assert "lane-check.sh" not in result.stdout, result.stdout
    assert "scanned 1 SKILL.md file(s)" in result.stderr, result.stderr


def test_conventions_documents_root_line_and_spelling_byte_exact(tmp_path):
    """conventions.md 'Bash in skills' is where the spelling is taught, and
    `partials/tests/toolkit-root.test.sh` executes the copy it finds there. So
    the documented bytes must be the pinned bytes: every line of conventions.md
    that starts (after indentation) with `ADLC_TOOLKIT_ROOT=` is the root line,
    there is at least one, and the guarded spelling appears verbatim. Then the
    documented pair, staged as a fence, lints clean — and with the root line
    dropped, it does not."""
    text = CONVENTIONS_MD.read_text(encoding="utf-8")
    documented = [
        ln.lstrip() for ln in text.splitlines()
        if ln.lstrip().startswith("ADLC_TOOLKIT_ROOT=")
    ]
    assert documented, "conventions.md quotes no root line"
    assert set(documented) == {_check.TOOLKIT_ROOT_LINE}, documented
    assert _check.GUARDED_SOURCE_SPELLING in text.splitlines()
    assert _check.GUARDED_SOURCE_SPELLING == (
        'if [ -f .adlc/partials/<name>.sh ]; then . .adlc/partials/<name>.sh; '
        'else . "$ADLC_TOOLKIT_ROOT/partials/<name>.sh"; fi'
    )
    # Arm order and the never-written default form are documented in words too.
    assert "${CLAUDE_PLUGIN_ROOT:-" in text

    sub = tmp_path / "documented"
    sub.mkdir()
    body = documented[0] + "\n" + _check.GUARDED_SOURCE_SPELLING.replace("<name>", "forge") + "\n"
    (sub / "SKILL.md").write_text(f"# documented\n\n```sh\n{body}```\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "", result.stdout

    (sub / "SKILL.md").write_text(
        "# documented\n\n```sh\n"
        + _check.GUARDED_SOURCE_SPELLING.replace("<name>", "forge") + "\n```\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert len(_root_lines(result)) == 1, result.stdout


def test_toolkit_root_line_on_a_real_skill_rewrite(tmp_path):
    """LESSON-019: the checks read real trees, not only their fixtures. Take the
    real `architect/SKILL.md`, rewrite its guarded source line to the
    ToolkitRoot spelling with the root line above it (if TASK-124 has already
    done so, take the file as it is), and the rewrite adds no finding of any
    kind. Remove that one root line and exactly one `toolkit-root-line` finding
    appears, on the source line that lost it."""
    real = (REPO_ROOT / "architect" / "SKILL.md").read_text(encoding="utf-8")
    lines = real.splitlines(keepends=True)
    idx = next(
        i for i, ln in enumerate(lines)
        if _check.CANONICAL_SOURCE_RE.match(ln.rstrip("\n"))
    )
    src = lines[idx]
    indent = src[: len(src) - len(src.lstrip())]
    name = src.split(".adlc/partials/", 1)[1].split(".sh", 1)[0]
    new_src = indent + _check.guarded_source_line(name) + "\n"
    root_line = indent + _check.TOOLKIT_ROOT_LINE + "\n"
    if idx > 0 and lines[idx - 1] == root_line and lines[idx] == new_src:
        rewritten = lines
        root_at = idx - 1
    else:
        rewritten = lines[:idx] + [root_line, new_src] + lines[idx + 1:]
        root_at = idx

    def lint(content: list[str]) -> list[str]:
        d = tmp_path / f"run{len(list(tmp_path.iterdir()))}" / "architect"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("".join(content), encoding="utf-8")
        return [ln.split(": ", 2)[1] for ln in _run(d.parent).stdout.splitlines() if ": " in ln]

    baseline = sorted(lint(lines))
    assert sorted(lint(rewritten)) == baseline
    without_root = rewritten[:root_at] + rewritten[root_at + 1:]
    assert sorted(lint(without_root)) == sorted(baseline + ["toolkit-root-line"])


# ---------------------------------------------------------------------------
# REQ-646 ADR-5: lesson-check-order — /wrapup and /bugfix lesson capture order
# ---------------------------------------------------------------------------

LCO_FIXTURES = FIXTURES / "lesson-check-order"


def _stage_lesson_pair(tmp_path: Path, wrapup: str, bugfix: str) -> Path:
    """Stage two fixtures as `wrapup/SKILL.md` and `bugfix/SKILL.md` — the check
    is keyed on those directory names, so the per-name `_stage` cannot reach it."""
    for skill, name in (("wrapup", wrapup), ("bugfix", bugfix)):
        (tmp_path / skill).mkdir()
        shutil.copyfile(LCO_FIXTURES / f"{name}.md", tmp_path / skill / "SKILL.md")
    return tmp_path


def _lco(result) -> list[tuple[str, int, str]]:
    """`(file, line, finding-id)` for every lesson-check-order finding."""
    out = []
    for ln in result.stdout.splitlines():
        if " lesson-check-order: " not in ln:
            continue
        file, line, rest = ln.split(":", 2)
        fid = rest.split(" lesson-check-order: ", 1)[1].split(":", 1)[0]
        out.append((file, int(line), fid))
    return out


def _lco_text(name: str) -> str:
    return (LCO_FIXTURES / f"{name}.md").read_text(encoding="utf-8")


def _fence_span(lines: list[str], needle: str) -> tuple[int, int]:
    """0-based (opening, closing) of the fenced block whose body holds `needle`."""
    hit = next(i for i, ln in enumerate(lines) if needle in ln)
    opening = max(i for i in range(hit) if lines[i].lstrip().startswith("```"))
    closing = next(i for i in range(hit + 1, len(lines)) if lines[i].strip() == "```")
    return opening, closing


def _lco_fence_opening(name: str, needle: str) -> int:
    """1-based opening line of the fixture fence whose body holds `needle`."""
    return _fence_span(_lco_text(name).splitlines(), needle)[0] + 1


def _rules_block(text: str) -> str:
    lines = text.splitlines(keepends=True)
    start = lines.index("<!-- lesson-capture-rules -->\n")
    end = lines.index("<!-- /lesson-capture-rules -->\n")
    return "".join(lines[start + 1:end])


def test_lesson_check_order_good_pair_passes(tmp_path):
    """BR-3/AC-4 benign path: the good pair draws no finding at all — the
    recheck call is found mid-line (`if ! adlc_recheck_id lesson …`), every rule
    line is in the question, and the blocks are byte-equal. A third skill dir
    carrying the reordered shape is not read: the check is keyed on the two
    directory names, so nothing else is held to the lesson-capture contract."""
    root = _stage_lesson_pair(tmp_path, "wrapup-good", "bugfix-good")
    (tmp_path / "notes").mkdir()
    shutil.copyfile(
        LCO_FIXTURES / "bugfix-recheck-before-check.md", tmp_path / "notes" / "SKILL.md"
    )
    result = _run(root)
    assert _lco(result) == [], result.stdout
    assert result.returncode == 0, result.stdout + result.stderr
    assert "scanned 3 SKILL.md file(s)" in result.stderr, result.stderr


def test_lesson_check_order_recheck_before_check_fails(tmp_path):
    """BR-3: a recheck fence above the check fence is exactly one
    `recheck-before-check`, on the recheck fence's opening line."""
    root = _stage_lesson_pair(tmp_path, "wrapup-good", "bugfix-recheck-before-check")
    result = _run(root)
    opening = _lco_fence_opening("bugfix-recheck-before-check", "adlc_recheck_id lesson")
    assert _lco(result) == [("bugfix/SKILL.md", opening, "recheck-before-check")], result.stdout
    assert result.returncode == 1, result.stdout + result.stderr


def test_lesson_check_order_backtick_marker_is_decoy(tmp_path):
    """BR-3 / LESSON-404: the marker in backticks, and the marker with prose on
    its line, both sit above the check fence and neither is a write point —
    the only finding is `missing-write-point`."""
    text = _lco_text("bugfix-backtick-marker")
    # The decoys must really be there, or this test proves nothing.
    assert "`<!-- lesson-write-point -->`" in text
    assert "<!-- lesson-write-point --> **Write the lesson**" in text
    root = _stage_lesson_pair(tmp_path, "wrapup-good", "bugfix-backtick-marker")
    result = _run(root)
    assert _lco(result) == [("bugfix/SKILL.md", 1, "missing-write-point")], result.stdout
    assert result.returncode == 1, result.stdout + result.stderr


def test_lesson_check_order_rules_block_mismatch_fails(tmp_path):
    """BR-4/AC-6: rules blocks one byte apart are one `rules-block-mismatch`,
    reported once (on the /bugfix copy) at the differing line."""
    good = _rules_block(_lco_text("bugfix-good"))
    bad = _rules_block(_lco_text("bugfix-rules-mismatch"))
    assert good == _rules_block(_lco_text("wrapup-good"))
    assert len(good) == len(bad) and sum(a != b for a, b in zip(good, bad)) == 1
    root = _stage_lesson_pair(tmp_path, "wrapup-good", "bugfix-rules-mismatch")
    result = _run(root)
    differing = _line_of("lesson-check-order/bugfix-rules-mismatch", "never pad!")
    assert _lco(result) == [("bugfix/SKILL.md", differing, "rules-block-mismatch")], result.stdout
    assert result.returncode == 1, result.stdout + result.stderr


def test_lesson_check_order_rule_line_absent_from_question_fails(tmp_path):
    """BR-4: a rule line the `--question` string does not carry is one
    `rules-line-not-in-question`, on that line of the /wrapup block."""
    root = _stage_lesson_pair(tmp_path, "wrapup-question-missing-rule", "bugfix-good")
    result = _run(root)
    rule2 = _line_of("lesson-check-order/wrapup-question-missing-rule", "2. Declare the contrast")
    assert _lco(result) == [("wrapup/SKILL.md", rule2, "rules-line-not-in-question")], result.stdout
    assert result.returncode == 1, result.stdout + result.stderr


HARNESS_LITERAL = "**Validate the draft**"  # a prose anchor between the write point and the check fence
CHECK_CALL = "adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md"


def _write_lco(root: Path, skill: str, lines: list[str]) -> None:
    (root / skill / "SKILL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mutated_run(tmp_path: Path, skill: str, mutate) -> subprocess.CompletedProcess:
    """Stage the good pair, apply `mutate` to `skill`'s copy alone, and run."""
    root = _stage_lesson_pair(tmp_path, "wrapup-good", "bugfix-good")
    _write_lco(root, skill, mutate(_lco_text(f"{skill}-good").splitlines()))
    return _run(root)


def _rewrite(needle, change):
    """Mutation: replace the first line containing `needle` with `change(line)`."""
    def mutate(lines):
        i = next(i for i, ln in enumerate(lines) if needle in ln)
        return lines[:i] + [change(lines[i])] + lines[i + 1:]
    return mutate


def _drop_fence(needle):
    def mutate(lines):
        o, c = _fence_span(lines, needle)
        return lines[:o] + lines[c + 1:]
    return mutate


def _write_point_below_check(lines):
    lines = [ln for ln in lines if ln != "<!-- lesson-write-point -->"]
    _o, c = _fence_span(lines, "adlc_lesson_check ")
    return lines[:c + 1] + ["<!-- lesson-write-point -->"] + lines[c + 1:]


def _drop_rules_block(lines):
    o = lines.index("<!-- lesson-capture-rules -->")
    c = lines.index("<!-- /lesson-capture-rules -->")
    return lines[:o] + lines[c + 1:]


def _unclose_rules_block(lines):
    return [ln for ln in lines if ln != "<!-- /lesson-capture-rules -->"]


def _blank_rules_block(lines):
    """Both markers kept, every line between them blank."""
    o = lines.index("<!-- lesson-capture-rules -->")
    c = lines.index("<!-- /lesson-capture-rules -->")
    return lines[:o + 1] + [""] * (c - o - 1) + lines[c:]


@pytest.mark.parametrize("skill", ["wrapup", "bugfix"])
@pytest.mark.parametrize(
    "mutate, finding_id",
    [
        (_drop_fence("adlc_lesson_check "), "missing-check-fence"),
        (_drop_fence("adlc_recheck_id lesson"), "missing-recheck-fence"),
        (_write_point_below_check, "check-before-write-point"),
        (_drop_rules_block, "rules-block-missing"),
        (_unclose_rules_block, "rules-block-missing"),
        (_blank_rules_block, "rules-block-missing"),
    ],
    ids=[
        "no-check", "no-recheck", "check-before-wp",
        "no-block", "unclosed-block", "blank-block",
    ],
)
def test_lesson_check_order_remaining_ids_fire(tmp_path, skill, mutate, finding_id):
    """Every other documented finding id fires, alone, on a one-edit mutation of
    EITHER good fixture, so neither side is checked less than the other. A
    missing, unclosed or blank block is not ALSO a mismatch (the parity
    comparison skips it) nor, on /wrapup, a question-coverage finding."""
    result = _mutated_run(tmp_path, skill, mutate)
    assert [fid for _f, _l, fid in _lco(result)] == [finding_id], result.stdout
    assert all(f == f"{skill}/SKILL.md" for f, _l, _id in _lco(result)), result.stdout


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (_rewrite(CHECK_CALL, lambda ln: "true && " + ln), []),
        (_rewrite(CHECK_CALL, lambda ln: "# true && " + ln), ["missing-check-fence"]),
        (_rewrite("adlc_recheck_id lesson", lambda ln: "# " + ln), ["missing-recheck-fence"]),
        (
            _rewrite(CHECK_CALL, lambda ln: ln.replace("adlc_lesson_check ", "adlc_lesson_check_x ")),
            ["missing-check-fence"],
        ),
    ],
    ids=["mid-line-call", "commented-check", "commented-recheck", "longer-name"],
)
def test_lesson_check_order_call_detection(tmp_path, mutate, expected):
    """A call behind `&&` is a call (command position, not just line start); the
    SAME line commented out is not, so the only check call being a comment is
    `missing-check-fence` (likewise the recheck); and `adlc_lesson_check_x` is a
    different function, not a call of `adlc_lesson_check`."""
    result = _mutated_run(tmp_path, "bugfix", mutate)
    assert [fid for _f, _l, fid in _lco(result)] == expected, result.stdout


def _recheck_into_check_fence(lines):
    """Move the recheck fence's body into the check fence, above the check call."""
    ro, rc = _fence_span(lines, "adlc_recheck_id lesson")
    body = lines[ro + 1:rc]
    rest = lines[:ro] + lines[rc + 1:]
    call = rest.index(CHECK_CALL)
    return rest[:call] + body + rest[call:]


def _extra_check_fence_above_write_point(lines):
    """A second check fence, harness line and all, added above the write point."""
    wp = lines.index("<!-- lesson-write-point -->")
    co, cc = _fence_span(lines, "adlc_lesson_check ")
    return lines[:wp] + [HARNESS_LITERAL + " here too.", ""] + lines[co:cc + 1] + [""] + lines[wp:]


def _extra_rules_line(lines):
    c = lines.index("<!-- /lesson-capture-rules -->")
    return lines[:c] + ["4. One rule too many."] + lines[c:]


@pytest.mark.parametrize(
    "mutate, finding_id, where",
    [
        (_recheck_into_check_fence, "recheck-before-check",
         lambda ls: _fence_span(ls, "adlc_lesson_check ")[0] + 1),
        (_extra_check_fence_above_write_point, "check-before-write-point",
         lambda ls: _fence_span(ls, "adlc_lesson_check ")[0] + 1),
        (_extra_rules_line, "rules-block-mismatch",
         lambda ls: ls.index("4. One rule too many.") + 1),
    ],
    ids=["same-fence-recheck-first", "second-check-above-wp", "extra-trailing-rule"],
)
def test_lesson_check_order_sub_branches(tmp_path, mutate, finding_id, where):
    """The branches a one-fence-each fixture never reaches: a check and a recheck
    in ONE fence are still ordered by their call lines; with two check fences,
    only the one above the write point, or only the one without a harness line,
    is reported; and a /bugfix block equal to /wrapup's plus one trailing line is
    a mismatch at that line (the zip of the two bodies runs out before it)."""
    lines = mutate(_lco_text("bugfix-good").splitlines())
    result = _mutated_run(tmp_path, "bugfix", lambda _ls: lines)
    assert _lco(result) == [("bugfix/SKILL.md", where(lines), finding_id)], result.stdout


def _rules_marker_decoys_above_block(lines):
    o = lines.index("<!-- lesson-capture-rules -->")
    return lines[:o] + [
        "The rules sit between `<!-- lesson-capture-rules -->` and its closer.",
        "<!-- lesson-capture-rules --> with prose after it opens nothing.",
        "",
    ] + lines[o:]


def _fenced_rules_example_above_block(lines):
    o = lines.index("<!-- lesson-capture-rules -->")
    return lines[:o] + [
        "```markdown",
        "<!-- lesson-capture-rules -->",
        "An example rule.",
        "<!-- /lesson-capture-rules -->",
        "```",
        "",
    ] + lines[o:]


def _second_write_point_below_check(lines):
    _o, c = _fence_span(lines, "adlc_lesson_check ")
    return lines[:c + 1] + ["", "<!-- lesson-write-point -->"] + lines[c + 1:]


@pytest.mark.parametrize("skill", ["wrapup", "bugfix"])
@pytest.mark.parametrize(
    "mutate",
    [_rules_marker_decoys_above_block, _fenced_rules_example_above_block,
     _second_write_point_below_check],
    ids=["backticked-rules-marker", "fenced-rules-example", "second-write-point-below"],
)
def test_lesson_check_order_benign_shapes_pass(tmp_path, skill, mutate):
    """A backticked or prose-trailed `<!-- lesson-capture-rules -->` opens no
    block, nor does one inside an example fence — either would make the parsed
    block differ; and a second write point BELOW the check does not move the
    anchor (one write point above the first check call is enough)."""
    result = _mutated_run(tmp_path, skill, mutate)
    assert _lco(result) == [], result.stdout


@pytest.mark.parametrize(
    "fixture, finding_id",
    [
        ("bugfix-fenced-write-point", "check-before-write-point"),
    ],
)
def test_lesson_check_order_fenced_decoys_do_not_count(tmp_path, fixture, finding_id):
    """LESSON-404: a write-point marker inside a ```markdown fence sits above the
    check fence and would satisfy the check if fenced lines counted — the only
    finding is the one the real shape earns, on the check fence's opening line."""
    text = _lco_text(fixture)
    # The decoy must really be there, or this test proves nothing.
    assert "```markdown\n<!-- lesson-write-point -->\n" in text
    root = _stage_lesson_pair(tmp_path, "wrapup-good", fixture)
    result = _run(root)
    opening = _lco_fence_opening(fixture, "adlc_lesson_check ")
    assert _lco(result) == [("bugfix/SKILL.md", opening, finding_id)], result.stdout
    assert result.returncode == 1, result.stdout + result.stderr


GRANULARITY_RULE = "Granularity: aim between."


@pytest.mark.parametrize(
    "edits",
    [
        [("\n" + GRANULARITY_RULE + "\n", "\n"), (" " + GRANULARITY_RULE, "")],
        [(GRANULARITY_RULE, "Note on the rule. " + GRANULARITY_RULE)],
    ],
    ids=["dropped", "not-at-line-start"],
)
def test_lesson_check_order_rules_block_needs_granularity_line(tmp_path, edits):
    """BR-4: a rules block with no line STARTING `Granularity:` is one
    `rules-block-missing-granularity` per file, on its opening marker. Every
    copy — both blocks and /wrapup's question — is edited alike, so neither the
    parity comparison nor question coverage has anything to say."""
    root = _stage_lesson_pair(tmp_path, "wrapup-good", "bugfix-good")
    expected = []
    for skill in ("wrapup", "bugfix"):
        text = _lco_text(f"{skill}-good")
        assert edits[0][0] in text  # the block line itself is always edited
        for old, new in edits:
            text = text.replace(old, new)
        lines = text.splitlines()
        _write_lco(root, skill, lines)
        opening = lines.index("<!-- lesson-capture-rules -->") + 1
        expected.append((f"{skill}/SKILL.md", opening, "rules-block-missing-granularity"))
    result = _run(root)
    assert sorted(_lco(result)) == sorted(expected), result.stdout


def test_lesson_check_order_shipped_tree_is_clean():
    """AC-4/AC-14: the real wrapup/SKILL.md and bugfix/SKILL.md satisfy the check
    (`test_shipped_toolkit_tree_is_clean` covers only the retrieval-status
    parity check, so this is the real-tree assertion for this one)."""
    result = _run(REPO_ROOT)
    assert _lco(result) == [], result.stdout


def test_lesson_check_order_real_bugfix_reordered_fails(tmp_path):
    """AC-4: the REAL bugfix/SKILL.md with its lesson recheck fence moved above
    its check fence draws `recheck-before-check` — the check reads the shipped
    spelling, not just the fixture's."""
    (tmp_path / "wrapup").mkdir()
    (tmp_path / "bugfix").mkdir()
    shutil.copyfile(REPO_ROOT / "wrapup" / "SKILL.md", tmp_path / "wrapup" / "SKILL.md")
    lines = (REPO_ROOT / "bugfix" / "SKILL.md").read_text(encoding="utf-8").splitlines()
    ro, rc = _fence_span(lines, "adlc_recheck_id lesson")
    fence = lines[ro:rc + 1]
    rest = lines[:ro] + lines[rc + 1:]
    co, _cc = _fence_span(rest, "adlc_lesson_check ")
    moved = rest[:co] + fence + rest[co:]
    (tmp_path / "bugfix" / "SKILL.md").write_text("\n".join(moved) + "\n", encoding="utf-8")
    result = _run(tmp_path)
    assert _lco(result) == [("bugfix/SKILL.md", co + 1, "recheck-before-check")], result.stdout


# ---------------------------------------------------------------------------
# REQ-646 BR-4: /wrapup's delegated --question carries every rule line, in order
# ---------------------------------------------------------------------------

QUESTION_CALL = 'command "$ADLC_READ_BIN"'
RULE_1 = "1. Cite the moment: put it in evidence."
RULE_2 = "2. Declare the contrast: high, medium or low."


def _rule_line(fixture: str, rule: str) -> int:
    """1-based line of `rule` inside the fixture's capture-rules block."""
    lines = _lco_text(fixture).splitlines()
    return lines.index(rule, lines.index("<!-- lesson-capture-rules -->")) + 1


def test_lesson_question_coverage_ignores_prose_copies(tmp_path):
    """The rule line missing from the question also appears in prose elsewhere,
    so it occurs twice in the file — a count-based check passes that; the check
    reads the question argument itself, so it still fires on that block line."""
    root = _stage_lesson_pair(tmp_path, "wrapup-question-missing-rule", "bugfix-good")
    lines = _lco_text("wrapup-question-missing-rule").splitlines()
    _write_lco(root, "wrapup", lines + ["", "Rule two again, in prose:", RULE_2])
    result = _run(root)
    rule2 = _rule_line("wrapup-question-missing-rule", RULE_2)
    assert _lco(result) == [("wrapup/SKILL.md", rule2, "rules-line-not-in-question")], result.stdout


def test_lesson_question_coverage_requires_block_order(tmp_path):
    """Rules 1 and 2 swapped inside the question: each is present, but rule 2 is
    found only before rule 1's match, so it is one out-of-order finding on rule
    2's block line (and the lines after it are not judged)."""
    swap = _rewrite(
        QUESTION_CALL,
        lambda ln: ln.replace(RULE_1 + " " + RULE_2, RULE_2 + " " + RULE_1),
    )
    lines = swap(_lco_text("wrapup-good").splitlines())
    assert RULE_2 + " " + RULE_1 in "\n".join(lines)
    result = _mutated_run(tmp_path, "wrapup", lambda _ls: lines)
    rule2 = _rule_line("wrapup-good", RULE_2)
    assert _lco(result) == [("wrapup/SKILL.md", rule2, "rules-line-not-in-question")], result.stdout
    assert "only before the previous rule line" in result.stdout, result.stdout


@pytest.mark.parametrize(
    "mutate",
    [
        _drop_fence(QUESTION_CALL),
        _rewrite(QUESTION_CALL, lambda ln: "# " + ln),
        _rewrite(QUESTION_CALL, lambda ln: ln.replace('--question "', "--question ")),
    ],
    ids=["no-call", "commented-call", "unquoted-question"],
)
def test_lesson_question_coverage_without_a_question_fails(tmp_path, mutate):
    """No live `command "$ADLC_READ_BIN" … --question "…"` line means no rule
    reaches the delegate: one `rules-line-not-in-question`, on the block's first
    rule line. A rules block in prose elsewhere in the file does not stand in."""
    lines = mutate(_lco_text("wrapup-good").splitlines())
    result = _mutated_run(tmp_path, "wrapup", lambda _ls: lines)
    first = lines.index("<!-- lesson-capture-rules -->") + 2
    assert _lco(result) == [("wrapup/SKILL.md", first, "rules-line-not-in-question")], result.stdout


@pytest.mark.parametrize(
    "replacement, ids",
    [
        ('put it in "evidence".', ["rules-line-unsafe-in-question", "rules-line-not-in-question"]),
        ("put it in $HOME evidence.", ["rules-line-unsafe-in-question"]),
        ("put it in `evidence`.", ["rules-line-unsafe-in-question"]),
        ("put it in evidence \\ here.", ["rules-line-unsafe-in-question"]),
    ],
    ids=["double-quote", "dollar", "backtick", "backslash"],
)
def test_lesson_question_coverage_unsafe_characters(tmp_path, replacement, ids):
    """A rule line holding `"`, `$`, a backtick or `\\` is
    `rules-line-unsafe-in-question` even when pasted into the question verbatim:
    the shell would not hand it to the delegate as written. A `"` also ends the
    argument early, so that line is missing from the question too. Both copies
    of the block are edited alike, so parity stays quiet."""
    root = _stage_lesson_pair(tmp_path, "wrapup-good", "bugfix-good")
    for skill in ("wrapup", "bugfix"):
        text = _lco_text(f"{skill}-good")
        assert "put it in evidence." in text
        _write_lco(root, skill, text.replace("put it in evidence.", replacement).splitlines())
    result = _run(root)
    rule1 = _rule_line("wrapup-good", RULE_1)
    assert _lco(result) == [("wrapup/SKILL.md", rule1, fid) for fid in ids], result.stdout


def test_lesson_question_coverage_real_wrapup_missing_rule_fails(tmp_path):
    """The REAL wrapup/SKILL.md with one capture-rules line cut out of its
    delegated `--question` draws `rules-line-not-in-question` on that block line
    — the check reads the shipped call, not just the fixture's."""
    (tmp_path / "wrapup").mkdir()
    (tmp_path / "bugfix").mkdir()
    shutil.copyfile(REPO_ROOT / "bugfix" / "SKILL.md", tmp_path / "bugfix" / "SKILL.md")
    lines = (REPO_ROOT / "wrapup" / "SKILL.md").read_text(encoding="utf-8").splitlines()
    o = lines.index("<!-- lesson-capture-rules -->")
    c = lines.index("<!-- /lesson-capture-rules -->", o)
    target = [i for i in range(o + 1, c) if lines[i].strip()][1]
    rule = lines[target].strip()
    q = next(
        i for i, ln in enumerate(lines)
        if QUESTION_CALL in ln and '--question "' in ln and not ln.lstrip().startswith("#")
    )
    assert lines[q].count(rule) == 1, "the real question must carry the rule exactly once"
    lines[q] = lines[q].replace(rule, "")
    _write_lco(tmp_path, "wrapup", lines)
    result = _run(tmp_path)
    assert _lco(result) == [("wrapup/SKILL.md", target + 1, "rules-line-not-in-question")], result.stdout


# ---------------------------------------------------------------------------
# REQ-646 verify residuals: nested and tilde fences, call position, fence
# edges, parity and question behaviours, the harness window and a second
# recheck
# ---------------------------------------------------------------------------

RECHECK_CALL = 'if ! adlc_recheck_id lesson "$LESSON_ID"; then'
WRITE_POINT = "<!-- lesson-write-point -->"


def _wrap_fence(needle, opener, closer):
    """Mutation: put the fence whose body holds `needle` inside an outer fence."""
    def mutate(lines):
        o, c = _fence_span(lines, needle)
        return lines[:o] + [opener] + lines[o:c + 1] + [closer] + lines[c + 1:]
    return mutate


def _respell_fence(needle, opener, closer):
    """Mutation: respell the opening and closing lines of the fence holding `needle`."""
    def mutate(lines):
        o, c = _fence_span(lines, needle)
        return lines[:o] + [opener] + lines[o + 1:c] + [closer] + lines[c + 1:]
    return mutate


def _nested_example_above_write_point(needle):
    """Mutation: a copy of the fence holding `needle`, shown inside a
    ````markdown example above the write point — above every real call."""
    def mutate(lines):
        o, c = _fence_span(lines, needle)
        wp = lines.index(WRITE_POINT)
        return lines[:wp] + ["````markdown"] + lines[o:c + 1] + ["````", ""] + lines[wp:]
    return mutate


def _check_fence_into_unclosed_outer(lines):
    """The check fence moved to EOF, inside a ````markdown fence never closed."""
    o, c = _fence_span(lines, CHECK_CALL)
    return lines[:o] + lines[c + 1:] + ["", "````markdown"] + lines[o:c + 1]


def _unclose_last_fence(lines):
    """Drop the final ``` (the recheck fence's): that fence now runs to EOF."""
    assert lines[-1] == "```"
    return lines[:-1]


def _unclosed_tilde_above_write_point(lines):
    wp = lines.index(WRITE_POINT)
    return lines[:wp] + ["~~~text"] + lines[wp:]


def _write_point_after_inner_backticks(lines):
    """The write point moved into a ````markdown example, after a bare ``` line
    that would close a 3-backtick fence but not this 4-backtick one."""
    lines = [ln for ln in lines if ln != WRITE_POINT]
    h = next(i for i, ln in enumerate(lines) if HARNESS_LITERAL in ln)
    return lines[:h] + [
        "````markdown", "```sh", "echo example", "```", WRITE_POINT, "````", "",
    ] + lines[h:]


@pytest.mark.parametrize("skill", ["wrapup", "bugfix"])
@pytest.mark.parametrize(
    "mutate, expected",
    [
        (_wrap_fence(CHECK_CALL, "````markdown", "````"), ["missing-check-fence"]),
        (_wrap_fence(CHECK_CALL, "~~~markdown", "~~~"), ["missing-check-fence"]),
        (_wrap_fence("adlc_recheck_id lesson", "````text", "````"), ["missing-recheck-fence"]),
        (_respell_fence(CHECK_CALL, "~~~sh", "~~~"), []),
        (_respell_fence("adlc_recheck_id lesson", "~~~~bash", "~~~~"), []),
        (_nested_example_above_write_point(CHECK_CALL), []),
        (_nested_example_above_write_point("adlc_recheck_id lesson"), []),
        (_check_fence_into_unclosed_outer, ["missing-check-fence"]),
        (_unclose_last_fence, []),
        (_unclosed_tilde_above_write_point,
         ["missing-check-fence", "missing-recheck-fence", "missing-write-point"]),
        (_write_point_after_inner_backticks, ["missing-write-point"]),
    ],
    ids=[
        "check-in-4-backtick-outer", "check-in-tilde-outer", "recheck-in-4-backtick-outer",
        "tilde-check-fence", "tilde-recheck-fence", "nested-check-example-above-wp",
        "nested-recheck-example-above-wp", "check-in-unclosed-outer-at-eof",
        "unclosed-recheck-fence-to-eof", "unclosed-tilde-swallows-rest",
        "4-backtick-holds-3-backtick-line",
    ],
)
def test_lesson_check_order_nested_and_tilde_fences(tmp_path, skill, mutate, expected):
    """m6/L8: fences nest length-aware and only TOP-LEVEL shell fences carry
    calls. A ```sh fence shown inside an outer ````markdown or ~~~markdown
    fence calls nothing — so the only check (or recheck) being such an example
    is `missing-check-fence` (`missing-recheck-fence`), and an example placed
    above the write point is no `check-before-write-point` or
    `recheck-before-check`. `~~~sh` and `~~~~bash` fences are walked like
    backtick ones. An unclosed fence runs to EOF: a shell one keeps its call, a
    non-shell one swallows every marker and call after it. A bare ``` inside a
    ````markdown fence does not close it, so a write point after that line is
    still fenced."""
    result = _mutated_run(tmp_path, skill, mutate)
    assert sorted(fid for _f, _l, fid in _lco(result)) == expected, result.stdout
    assert all(f == f"{skill}/SKILL.md" for f, _l, _id in _lco(result)), result.stdout


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (_rewrite(CHECK_CALL, lambda ln: 'echo "' + ln + '"'), ["missing-check-fence"]),
        (_rewrite(CHECK_CALL, lambda ln: "echo " + ln), ["missing-check-fence"]),
        (_rewrite(CHECK_CALL, lambda ln: 'echo "x; ' + ln + '"'), ["missing-check-fence"]),
        (_rewrite(CHECK_CALL, lambda ln: "echo 'x && " + ln + "'"), ["missing-check-fence"]),
        (_rewrite(CHECK_CALL, lambda ln: "true # ; " + ln), ["missing-check-fence"]),
        (_rewrite(CHECK_CALL, lambda ln: "true;# " + ln), ["missing-check-fence"]),
        (_rewrite(CHECK_CALL, lambda ln: "if " + ln + "; then :; fi"), []),
        (_rewrite(CHECK_CALL, lambda ln: ln + "  # validate the draft"), []),
        (_rewrite(CHECK_CALL, lambda ln: 'echo "a #b"; ' + ln), []),
        (_rewrite(CHECK_CALL, lambda ln: "echo it\\'s; " + ln), []),
        (_rewrite(CHECK_CALL, lambda ln: "echo don't\n" + ln), []),
        (_rewrite(RECHECK_CALL, lambda _ln: ": # adlc_recheck_id lesson L"),
         ["missing-recheck-fence"]),
        (_rewrite(RECHECK_CALL, lambda ln: ln.replace(
            '! adlc_recheck_id lesson "$LESSON_ID"', '! echo "adlc_recheck_id lesson $LESSON_ID"')),
         ["missing-recheck-fence"]),
        (_rewrite(RECHECK_CALL, lambda ln: ln.replace("! adlc_recheck_id", "! echo adlc_recheck_id")),
         ["missing-recheck-fence"]),
        (_rewrite(RECHECK_CALL, lambda ln: ln.replace("adlc_recheck_id ", "adlc_recheck_idx ")),
         ["missing-recheck-fence"]),
        (_rewrite(RECHECK_CALL, lambda ln: ln.replace("adlc_recheck_id ", "my_adlc_recheck_id ")),
         ["missing-recheck-fence"]),
        (_rewrite(RECHECK_CALL, lambda ln: ln.replace(" lesson ", " lessons ")),
         ["missing-recheck-fence"]),
        (_rewrite(RECHECK_CALL, lambda ln: ln.replace("if ! ", "if ")), []),
    ],
    ids=[
        "check-in-double-quotes", "check-as-echo-argument", "separator-inside-quotes",
        "separator-inside-single-quotes", "trailing-comment-hides-separator",
        "comment-right-after-separator", "if-check-then", "call-with-trailing-comment",
        "hash-inside-quotes-is-not-a-comment", "escaped-apostrophe",
        "apostrophe-on-line-above", "recheck-in-comment", "recheck-in-double-quotes",
        "recheck-as-echo-argument", "recheck-name-longer", "recheck-name-prefixed",
        "recheck-kind-longer", "if-recheck-then",
    ],
)
def test_lesson_check_order_call_position_and_comments(tmp_path, mutate, expected):
    """L7: a call is a call only in a line's code and in command position. A
    mention inside a quoted string or as an `echo` argument is not a call —
    nor is a separator inside quotes a command position — and a trailing `#`
    comment is cut before matching, so `true # ; adlc_lesson_check x` and
    `: # adlc_recheck_id lesson L` call nothing. `if adlc_lesson_check x; then`
    IS a call, a call keeps a trailing comment, a `#` inside quotes opens no
    comment, and an apostrophe on one line does not quote the next. The name
    is pinned at both ends: `adlc_recheck_idx`, `my_adlc_recheck_id` and
    `adlc_recheck_id lessons` are not the recheck."""
    result = _mutated_run(tmp_path, "bugfix", mutate)
    assert [fid for _f, _l, fid in _lco(result)] == expected, result.stdout


def _fenced_closer_inside_block(lines):
    o = lines.index("<!-- lesson-capture-rules -->")
    return lines[:o + 1] + ["```text", "<!-- /lesson-capture-rules -->", "```"] + lines[o + 1:]


def test_lesson_check_order_fenced_closer_does_not_close_block(tmp_path):
    """L8: a `<!-- /lesson-capture-rules -->` inside a fence in the block closes
    nothing: the block runs on to the real closer, so it still holds its
    `Granularity:` line and the only finding is the parity mismatch at the
    inserted fence. Had the fenced closer closed the block, its body would be
    the one ```text line — a `rules-block-missing-granularity` as well."""
    lines = _fenced_closer_inside_block(_lco_text("bugfix-good").splitlines())
    result = _mutated_run(tmp_path, "bugfix", lambda _ls: lines)
    first_body = lines.index("<!-- lesson-capture-rules -->") + 2
    assert _lco(result) == [("bugfix/SKILL.md", first_body, "rules-block-mismatch")], result.stdout


@pytest.mark.parametrize("skill", ["wrapup", "bugfix"])
def test_lesson_check_order_prose_trailed_closer_is_not_a_closer(tmp_path, skill):
    """L8: `<!-- /lesson-capture-rules -->` with prose after it on its line is
    not a closing marker, so the block is never closed — one
    `rules-block-missing` on the opening marker (and, being unclosed, neither
    a parity mismatch nor a question-coverage finding)."""
    mutate = _rewrite("<!-- /lesson-capture-rules -->", lambda ln: ln + " (end of the rules)")
    result = _mutated_run(tmp_path, skill, mutate)
    opening = _lco_text(f"{skill}-good").splitlines().index("<!-- lesson-capture-rules -->") + 1
    assert _lco(result) == [(f"{skill}/SKILL.md", opening, "rules-block-missing")], result.stdout


@pytest.mark.parametrize("scope", ["whole-file", "one-line"])
def test_lesson_rules_parity_crlf_is_a_mismatch(tmp_path, scope):
    """L9: the parity check decodes bytes, so a /bugfix copy with CRLF line
    endings — throughout, or on one rule line — is one `rules-block-mismatch`
    at the first CRLF line of its block, though the per-file checks (which read
    in text mode) see an identical file."""
    root = _stage_lesson_pair(tmp_path, "wrapup-good", "bugfix-good")
    text = _lco_text("bugfix-good")
    lines = text.splitlines()
    if scope == "whole-file":
        data = text.replace("\n", "\r\n")
        line = lines.index("<!-- lesson-capture-rules -->") + 2
    else:
        assert text.count(RULE_1 + "\n") == 1
        data = text.replace(RULE_1 + "\n", RULE_1 + "\r\n")
        line = lines.index(RULE_1) + 1
    (root / "bugfix" / "SKILL.md").write_bytes(data.encode("utf-8"))
    result = _run(root)
    assert _lco(result) == [("bugfix/SKILL.md", line, "rules-block-mismatch")], result.stdout


@pytest.mark.parametrize("escaping", ["wrapup", "bugfix"])
def test_lesson_rules_parity_skips_symlink_escaping_root(tmp_path, escaping):
    """L9: a SKILL.md that is a symlink to a file OUTSIDE the scan root is not
    compared: the blocks one byte apart draw no `rules-block-mismatch` (nor any
    per-file finding — the walk skips the escaping file too). The control, the
    same content as a real in-root file, does draw the mismatch."""
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    sources = {"wrapup": "wrapup-good", "bugfix": "bugfix-rules-mismatch"}
    for skill, name in sources.items():
        (root / skill).mkdir()
        if skill == escaping:
            shutil.copyfile(LCO_FIXTURES / f"{name}.md", outside / f"{skill}.md")
            (root / skill / "SKILL.md").symlink_to(outside / f"{skill}.md")
        else:
            shutil.copyfile(LCO_FIXTURES / f"{name}.md", root / skill / "SKILL.md")
    result = _run(root)
    assert _lco(result) == [], result.stdout
    # Control: the same file, really in the root, is compared.
    (root / escaping / "SKILL.md").unlink()
    shutil.copyfile(outside / f"{escaping}.md", root / escaping / "SKILL.md")
    result = _run(root)
    assert [fid for _f, _l, fid in _lco(result)] == ["rules-block-mismatch"], result.stdout


@pytest.mark.parametrize(
    "old, new, flagged",
    [
        (" " + RULE_1, "\n    " + RULE_1, False),
        (RULE_1, "1. Cite the moment:\n    put it in evidence.", True),
        (RULE_1, "1. Cite the moment: \\\n    put it in evidence.", True),
        (RULE_1, "1. Cite the moment: \\\nput it in evidence.", True),
    ],
    ids=["break-between-rules", "rule-split-by-newline", "rule-split-by-continuation",
         "rule-split-by-unindented-continuation"],
)
def test_lesson_question_coverage_wrapped_question(tmp_path, old, new, flagged):
    """L9 (documented decision): a `--question` wrapped over several source
    lines is read as written, NOT joined. Breaking BETWEEN rule lines passes —
    every rule is still in the argument verbatim. A rule line split across a
    break is one `rules-line-not-in-question` on that block line, with a
    message naming the wrap — even a `\\` continuation that would hand the
    delegate the words intact: one rule per source line is the contract."""
    lines = _lco_text("wrapup-good").splitlines()
    q = next(i for i, ln in enumerate(lines) if QUESTION_CALL in ln)
    assert lines[q].count(old) == 1
    lines[q] = lines[q].replace(old, new)
    result = _mutated_run(tmp_path, "wrapup", lambda _ls: lines)
    if not flagged:
        assert _lco(result) == [], result.stdout
        return
    written = "\n".join(lines).splitlines()  # the wrap moved every later line down
    rule1 = written.index(RULE_1, written.index("<!-- lesson-capture-rules -->")) + 1
    assert _lco(result) == [("wrapup/SKILL.md", rule1, "rules-line-not-in-question")], result.stdout
    assert "wrapped across a line break" in result.stdout, result.stdout


@pytest.mark.parametrize(
    "new, flagged",
    [('Propose a \\"lesson\\" draft.', False), ('Propose a "lesson" draft.', True)],
    ids=["escaped-quote", "unescaped-quote"],
)
def test_lesson_question_coverage_escaped_quote(tmp_path, new, flagged):
    """L9: an escaped `\\"` inside the question does not end the argument, so
    every rule after it is still found. The control — the same quotes
    unescaped — ends the argument at `"Propose a "`, so the block's first rule
    line is not in the question."""
    lines = _lco_text("wrapup-good").splitlines()
    q = next(i for i, ln in enumerate(lines) if QUESTION_CALL in ln)
    assert lines[q].count("Propose a lesson draft.") == 1
    lines[q] = lines[q].replace("Propose a lesson draft.", new)
    result = _mutated_run(tmp_path, "wrapup", lambda _ls: lines)
    if not flagged:
        assert _lco(result) == [], result.stdout
        return
    first = lines.index("<!-- lesson-capture-rules -->") + 2
    assert _lco(result) == [("wrapup/SKILL.md", first, "rules-line-not-in-question")], result.stdout
    assert "is not in the question" in result.stdout, result.stdout


@pytest.mark.parametrize("skill", ["wrapup", "bugfix"])
def test_lesson_check_order_second_recheck_before_check_fails(tmp_path, skill):
    """L10: a SECOND recheck fence, placed between the write point and the
    check fence while the original stays below the check, is one
    `recheck-before-check` on the early fence alone."""
    lines = _lco_text(f"{skill}-good").splitlines()
    ro, rc = _fence_span(lines, "adlc_recheck_id lesson")
    h = next(i for i, ln in enumerate(lines) if HARNESS_LITERAL in ln)
    assert lines.index(WRITE_POINT) < h < ro
    lines = lines[:h] + lines[ro:rc + 1] + [""] + lines[h:]
    result = _mutated_run(tmp_path, skill, lambda _ls: lines)
    assert _lco(result) == [(f"{skill}/SKILL.md", h + 1, "recheck-before-check")], result.stdout


# ---------------------------------------------------------------------------
# dispatch-fallback (REQ-669 ADR-6, BR-9, BR-4). The canonical sentence is read
# from conventions.md, never copied into this file: fixtures carry a
# `{{DISPATCH_SENTENCE}}` placeholder that staging fills from the real block.
# ---------------------------------------------------------------------------

DISPATCH_CHECK = "dispatch-has-fallback"
# The skills ADR-6 names, plus /adversary, which dispatches its own agent. Each
# must name a dispatched agent and carry the sentence, so the repo-clean test is
# not passing over files the detector cannot see (LESSON-019).
DISPATCHING_FILES = (
    "review/SKILL.md", "reflect/SKILL.md", "architect/SKILL.md", "optimize/SKILL.md",
    "analyze/SKILL.md", "proceed/SKILL.md", "sprint/SKILL.md", "adversary/SKILL.md",
    "proceed/phase-4-implementation.md", "proceed/phases-lite.md",
)
# REQ-666 BR-12: /sprint cannot run without subagents, so it carries the
# explicit-stop block instead of the paragraph.
STOP_FILES = ("sprint/SKILL.md",)


def _dispatch_stop() -> str:
    stop, _source = _check.load_dispatch_stop(REPO_ROOT)
    assert stop, "conventions.md has no readable dispatch-requires-subagents block"
    return stop


def _owed_block(rel: str) -> str:
    return _dispatch_stop() if rel in STOP_FILES else _dispatch_sentence()


def _dispatch_sentence() -> str:
    sentence, _source = _check.load_dispatch_sentence(REPO_ROOT)
    assert sentence, "conventions.md has no readable dispatch-fallback-sentence block"
    return sentence


def _wrap(sentence: str, indent: str = "", width: int = 60) -> str:
    """Hard-wrap at spaces only, the way the /proceed companion files are."""
    lines, current = [], ""
    for word in sentence.split(" "):
        if current and len(current) + 1 + len(word) > width:
            lines.append(indent + current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    lines.append(indent + current)
    return "\n".join(lines)


def _stage_dispatch(tmp_path: Path, name: str, sentence: str | None = None) -> Path:
    """Stage `fixtures/<name>.md` as `<tmp>/<name>/SKILL.md`, filling the
    sentence placeholders (plain and hard-wrapped) from conventions.md."""
    sentence = sentence or _dispatch_sentence()
    text = (FIXTURES / f"{name}.md").read_text()
    text = text.replace("{{DISPATCH_SENTENCE_WRAPPED}}", _wrap(sentence, "   "))
    text = text.replace("{{DISPATCH_SENTENCE}}", sentence)
    sub = tmp_path / name
    sub.mkdir()
    (sub / "SKILL.md").write_text(text)
    return tmp_path


def _dispatch_findings(result) -> list[tuple[str, int, str]]:
    out = []
    for ln in result.stdout.splitlines():
        parts = ln.split(": ", 2)
        if len(parts) == 3 and parts[1] == DISPATCH_CHECK:
            path, lineno = parts[0].rsplit(":", 1)
            out.append((path, int(lineno), parts[2]))
    return out


def _staged_line(root: Path, name: str, needle: str) -> int:
    lines = (root / name / "SKILL.md").read_text().splitlines()
    return next(i + 1 for i, ln in enumerate(lines) if needle in ln)


def test_dispatch_fallback_missing_sentence_fires(tmp_path):
    """BR-9 must-fire: a step that dispatches the reflector with no canonical
    sentence is one finding, at the step's first mention (its heading)."""
    root = _stage_dispatch(tmp_path, "dispatch-fallback-missing")
    result = _run(root)
    found = _dispatch_findings(result)
    heading = _staged_line(root, "dispatch-fallback-missing", "### Step 2: Dispatch")
    assert [(p, n) for p, n, _ in found] == [("dispatch-fallback-missing/SKILL.md", heading)], result.stdout
    assert "`reflector` agent" in found[0][2]
    assert "conventions.md 'Agent dispatch patterns'" in found[0][2]
    assert result.returncode == 1, result.stdout


def test_dispatch_fallback_cross_reference_does_not_fire(tmp_path):
    """BR-9 benign path: the reflector named only in cross-references ("see the
    reflector's checklist in `/reflect`", "(the `reflector` agent)"), behind a
    negation or a time word, as `agent's`, or inside a fence is not a toolkit
    dispatch; a Claude Code built-in ("launch Explore agents") is a generic one,
    satisfied by the paragraph's leading clause (REQ-666 BR-12)."""
    root = _stage_dispatch(tmp_path, "dispatch-fallback-cross-reference")
    result = _run(root)
    assert _dispatch_findings(result) == [], result.stdout
    assert result.returncode == 0, result.stdout
    # Not vacuous: the fixture does name toolkit agents the detector knows.
    names = _check.load_agent_names(REPO_ROOT)
    text = (FIXTURES / "dispatch-fallback-cross-reference.md").read_text()
    assert {"reflector", "security-auditor", "test-auditor"} <= names
    assert all(n in text for n in ("reflector", "security-auditor", "test-auditor"))
    found = _check.dispatch_mentions(text, names, _dispatch_sentence())[0]
    assert [m.agent for m in found] == [""], found


def test_dispatch_fallback_with_sentence_does_not_fire(tmp_path):
    """Every dispatch step carries the sentence; one copy is hard-wrapped and
    indented, which whitespace normalization accepts."""
    root = _stage_dispatch(tmp_path, "dispatch-fallback-ok")
    result = _run(root)
    assert _dispatch_findings(result) == [], result.stdout
    text = (root / "dispatch-fallback-ok" / "SKILL.md").read_text()
    mentions, _ = _check.dispatch_mentions(text, _check.load_agent_names(REPO_ROOT), _dispatch_sentence())
    assert {m.agent for m in mentions} == {"reflector", "correctness-reviewer", "security-auditor"}


def test_dispatch_fallback_sentence_in_another_step_fires(tmp_path):
    """The sentence is owed once per dispatch step: a copy in Step 2 does not
    cover Step 3's task-implementer dispatch."""
    root = _stage_dispatch(tmp_path, "dispatch-fallback-wrong-step")
    result = _run(root)
    line = _staged_line(root, "dispatch-fallback-wrong-step", "dispatch a `task-implementer` agent")
    found = _dispatch_findings(result)
    assert [(p, n) for p, n, _ in found] == [("dispatch-fallback-wrong-step/SKILL.md", line)], result.stdout
    assert "`task-implementer` agent" in found[0][2]


def test_dispatch_fallback_near_miss_sentence_fires(tmp_path):
    """One changed word in the copy is a finding: the comparison is exact
    after whitespace normalization."""
    sentence = _dispatch_sentence()
    near = sentence.replace("never improvise a checklist", "never invent a checklist")
    assert near != sentence
    text = (FIXTURES / "dispatch-fallback-ok.md").read_text()
    text = text.replace("{{DISPATCH_SENTENCE_WRAPPED}}", sentence).replace("{{DISPATCH_SENTENCE}}", near, 1)
    (tmp_path / "near").mkdir()
    (tmp_path / "near" / "SKILL.md").write_text(text)
    result = _run(tmp_path)
    assert len(_dispatch_findings(result)) == 1, result.stdout


def test_dispatch_fallback_walks_proceed_phase_files(tmp_path):
    """/proceed's Phase 4 dispatch lives in a companion file, so the check walks
    `proceed/phase*.md`; a mention in the file's introduction is satisfied by the
    sentence anywhere in that file."""
    root = _stage(tmp_path, "clean")
    proceed = root / "proceed"
    proceed.mkdir()
    body = (
        "# /proceed — Phase 9\n\nDispatching task-implementer agents in tiers.\n\n"
        "### Phase 9\n\n- Tier 0: launch a **task-implementer** agent for each task.\n"
    )
    (proceed / "phase-9-test.md").write_text(body)
    found = _dispatch_findings(_run(root))
    assert [(p, n) for p, n, _ in found] == [
        ("proceed/phase-9-test.md", 3), ("proceed/phase-9-test.md", 7),
    ], found
    (proceed / "phase-9-test.md").write_text(body + "\n" + _wrap(_dispatch_sentence()) + "\n")
    assert _dispatch_findings(_run(root)) == []


def test_dispatch_fallback_walks_partials_md(tmp_path):
    """conventions.md says the check covers `partials/*.md`: a companion doc
    whose step dispatches a toolkit agent fires without the sentence and is
    clean with it, and a cross-reference there does not fire."""
    root = _stage(tmp_path, "clean")
    partials = root / "partials"
    partials.mkdir()
    body = "# partial\n\n## Step 1\n\nDispatch the **reflector** agent for a second look.\n"
    (partials / "companion.md").write_text(body)
    found = _dispatch_findings(_run(root))
    assert [(p, n) for p, n, _ in found] == [("partials/companion.md", 5)], found
    (partials / "companion.md").write_text(body + "\n" + _wrap(_dispatch_sentence()) + "\n")
    assert _dispatch_findings(_run(root)) == []
    (partials / "companion.md").write_text(
        "# partial\n\n## Step 1\n\nSee the reflector's checklist in `/reflect`.\n")
    assert _dispatch_findings(_run(root)) == []
    # The walk that carries it is the phase walk, which lists partials/*.md.
    assert partials / "companion.md" in _check.find_phase_files(root)


def test_dispatch_fallback_reads_the_scan_roots_conventions_copy(tmp_path):
    """The root's own conventions.md is the source of the sentence: a skill
    that carries a different text fires, the root's text passes."""
    root = _stage_dispatch(tmp_path, "dispatch-fallback-ok")
    conv = root / ".adlc" / "context" / "conventions.md"
    conv.parent.mkdir(parents=True)
    other = "Agents are dispatched by the name the Agent tool lists, or run inline."
    conv.write_text(
        "## Agent dispatch patterns\n\n<!-- dispatch-fallback-sentence -->\n"
        f"{other}\n<!-- /dispatch-fallback-sentence -->\n"
    )
    assert len(_dispatch_findings(_run(root))) == 2  # both steps carry the toolkit text
    shutil.rmtree(root / "dispatch-fallback-ok")
    _stage_dispatch(root, "dispatch-fallback-ok", sentence=other)
    assert _dispatch_findings(_run(root)) == []


@pytest.mark.parametrize("block", [
    "",  # markers removed entirely
    "<!-- dispatch-fallback-sentence -->\n<!-- /dispatch-fallback-sentence -->\n",  # emptied
    "<!-- dispatch-fallback-sentence -->\nAgent names are bare.\n",  # never closed
    "```markdown\n<!-- dispatch-fallback-sentence -->\nAgent names are bare.\n"
    "<!-- /dispatch-fallback-sentence -->\n```\n",  # only an example inside a fence
])
def test_dispatch_fallback_unreadable_sentence_block_fires(tmp_path, block):
    """LESSON-019: deleting, emptying or unclosing the block in the root's
    conventions.md must not disarm the check. A file that names a dispatch
    reports the missing source instead of passing unchecked."""
    root = _stage_dispatch(tmp_path, "dispatch-fallback-ok")
    conv = root / ".adlc" / "context" / "conventions.md"
    conv.parent.mkdir(parents=True)
    conv.write_text("## Agent dispatch patterns\n\n" + block)
    found = _dispatch_findings(_run(root))
    assert len(found) == 1, found
    assert "could not be read from .adlc/context/conventions.md" in found[0][2]


def test_dispatch_fallback_repo_clean():
    """BR-4/BR-9 on the real tree: zero findings, and not vacuously. The block
    parses, every dispatching file names at least one dispatched agent, and each
    of those files carries the sentence (LESSON-019: verify the real post-change
    tree, not only fixtures)."""
    result = _run(REPO_ROOT)
    assert _dispatch_findings(result) == [], result.stdout
    sentence = _dispatch_sentence()
    names = _check.load_agent_names(REPO_ROOT)
    assert len(names) >= 19, names
    for rel in DISPATCHING_FILES:
        text = (REPO_ROOT / rel).read_text()
        mentions, _ = _check.dispatch_mentions(text, names, sentence, _dispatch_stop())
        assert mentions, f"{rel}: the detector sees no dispatch, so the clean result proves nothing"
        assert _owed_block(rel) in " ".join(text.split()), rel
    # A skill that dispatches only a harness built-in has generic mentions alone,
    # each satisfied by the paragraph's leading clause (REQ-666 BR-3, BR-12).
    bugfix = (REPO_ROOT / "bugfix" / "SKILL.md").read_text()
    assert "If this harness can run subagents, launch Explore agents" in bugfix
    found = _check.dispatch_mentions(bugfix, names, sentence)[0]
    assert found and all(m.agent == "" for m in found), found


@pytest.mark.parametrize("rel", [r for r in DISPATCHING_FILES if r.endswith("/SKILL.md")])
def test_dispatch_fallback_fires_when_sentence_removed_from_real_skill(tmp_path, rel):
    """Mutation on the real corpus: removing every copy of the sentence from a
    shipped dispatching skill produces at least one finding for it."""
    sentence = _owed_block(rel)
    text = (REPO_ROOT / rel).read_text()
    assert sentence in text, rel
    sub = tmp_path / rel.split("/")[0]
    sub.mkdir()
    (sub / "SKILL.md").write_text(text.replace(sentence, ""))
    found = _dispatch_findings(_run(tmp_path))
    assert found and all(p == f"{sub.name}/SKILL.md" for p, _, _ in found), found
