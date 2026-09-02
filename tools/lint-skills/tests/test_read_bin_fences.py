"""Execution tests for the post-REQ-609 delegate call-site fences (BR-12, AC-8).

`tools/lint-skills/check.py`'s `read-bin-fallback` check is a *structural* guard:
it proves no fence contains `ADLC_READ_BIN:-`. That is not the same claim as "an
empty `ADLC_READ_BIN` actually stops the corpus leaving the machine" — a fence
could drop the fallback and still hand a temp file to an empty command name, or
put the refusal after the invocation. So these tests take the real fences out of
the real skill files and RUN them — under `sh`, and under `zsh`/`bash` where the
machine has them, because the Bash tool that actually executes skill fences runs
zsh on macOS (LESSON-329) — against a fake gate partial that exports an empty
`ADLC_READ_BIN`, with a stub `adlc-read` first on `$PATH` that records having
been called. The assertion is the outcome (LESSON-478): the fence exits
non-zero, names itself and the reason on stderr, and the stub is never reached.

Every refusal assertion here is negative ("the stub was not called"), which is
also what a completely broken harness produces — a `$PATH` the stub is not on, a
runner that never executes the body, a marker path nothing could ever write. So
each test carries a positive control in the same run: a synthetic fence written
in the RETIRED shape, run through the identical harness with the identical empty
`ADLC_READ_BIN`, must reach the stub. That control is also the demonstration of
why the fallback was removed — with an empty resolver, `${ADLC_READ_BIN:-adlc-read}`
hands the corpus to whatever `adlc-read` the shell finds (LESSON-602, BUG-209).
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK_PY = REPO_ROOT / "tools" / "lint-skills" / "check.py"

# The call-site surfaces REQ-609 BR-12 names, and how many shell fences in each
# reference `ADLC_READ_BIN`. Pinned per file so a fence that silently loses its
# reference (or a file that stops being extracted at all) fails loudly instead
# of shrinking this suite into a vacuous pass.
#
# `analyze/SKILL.md` carries TWO call sites but only ONE fence: Step 1.5's
# invocation is written as an inline-code instruction inside a prose bullet, not
# as a fenced block, so it cannot be executed here. It is covered by the AC-8
# grep test below, which is text-based and sees prose.
EXPECTED_FENCES = {
    "agents/delegate-pre-pass.md": 2,
    "analyze/SKILL.md": 1,
    "proceed/SKILL.md": 1,
    "spec/SKILL.md": 2,
    "wrapup/SKILL.md": 1,
}

# The stderr label each file's refusal must carry, so a copy-pasted message from
# a neighbouring skill is a failure rather than a pass.
# Whether the refusal exits non-zero. Skills do (REQ-609 AC-8). The pre-pass
# agent does NOT: its contract forbids a non-zero exit as a signal, so its two
# fences refuse into the degraded object — same stderr line, nothing
# transmitted, exit 0 (REQ-609 AC-8, second clause).
EXPECTED_NONZERO_EXIT = {
    "agents/delegate-pre-pass.md": False,
    "analyze/SKILL.md": True,
    "proceed/SKILL.md": True,
    "spec/SKILL.md": True,
    "wrapup/SKILL.md": True,
}

EXPECTED_LABEL = {
    "agents/delegate-pre-pass.md": "delegate-pre-pass:",
    "analyze/SKILL.md": "/analyze:",
    "proceed/SKILL.md": "/proceed:",
    "spec/SKILL.md": "/spec:",
    "wrapup/SKILL.md": "/wrapup:",
}

# A fence in the shape this REQ retired. Lives here, in a `.py` file, on purpose:
# the AC-8 grep covers `*.md` and `*.sh` only, so the control cannot pollute the
# surface it is controlling for.
POSITIVE_CONTROL_FENCE = (
    ". .adlc/partials/delegate-gate.sh 2>/dev/null"
    " || . ~/.claude/skills/partials/delegate-gate.sh\n"
    '"${ADLC_READ_BIN:-adlc-read}" --no-warn --paths ./corpus.txt'
    ' --question "summarize"\n'
)

# REQ-609 AC-8. The three surfaces that legitimately still carry the retired
# spelling: the frozen pre-REQ-603 gate fixture (a parity baseline that must not
# change), this REQ's own spec files (they quote the shape they retire), and the
# changelog (it records the change).
AC8_LITERAL = "ADLC_READ_BIN:-adlc-read"
AC8_EXCLUDED_PREFIXES = (
    ".adlc/specs/",
    "partials/tests/fixtures/",
    "CHANGELOG.md",
)
# One residual outside those prefixes, owned by a LATER task. REQ-609 BR-15 /
# TASK-099 rewrites `partials/delegate-gate.md`'s call-site contract paragraph,
# which today still prescribes `"${ADLC_READ_BIN:-adlc-read}"` and describes the
# pre-REQ-609 resolver ("the bare name, when it is on PATH"). TASK-098 must not
# edit that file, so the residual is named here rather than hidden by a widened
# exclusion.
#
# DELETE THIS ENTRY WHEN TASK-099 LANDS. The assertion below is an exact match,
# not a subset, precisely so that a waiver cannot outlive its reason — an
# allowlist that survives the thing it excused is the guard-rot class LESSON-019
# is about.
AC8_TASK_099_RESIDUALS = {"partials/delegate-gate.md"}

# Skill fences are executed by Claude's Bash tool, whose shell on macOS is zsh —
# not the `sh` the fence is written against (LESSON-329: lint checks structure,
# only execution catches shell-semantics divergence). `/bin/sh` is the contract
# and is always required; the others are asserted where the machine has them, so
# a Linux CI box without zsh does not fail and a developer machine still gets the
# real executor shell covered. REQ-609 BR-16.
SHELLS = ["/bin/sh"] + [
    sh for sh in ("/bin/zsh", "/bin/bash") if Path(sh).is_file()
]


def _load_check_module():
    """Import `check.py` by path so the fence extractor is the linter's own.

    Two definitions of "a shell fence" — one in the linter, one here — would
    drift, and this suite's whole value is that it runs the same fences the
    `read-bin-fallback` check inspects.
    """
    spec = importlib.util.spec_from_file_location("_lint_check", CHECK_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_check = _load_check_module()


def _fences_referencing_read_bin(rel: str) -> list[str]:
    """Bodies of every shell fence in `rel` that mentions `ADLC_READ_BIN`."""
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    out = []
    for _lang, _idx, _start, body in _check._iter_fences(text):
        joined = "\n".join(line for _lineno, line in body)
        if "ADLC_READ_BIN" in joined:
            out.append(joined)
    return out


def _first_line_with(lines: list[str], needle: str) -> int:
    """Index of the first line containing `needle`; asserts rather than raising
    StopIteration, so a missing anchor reads as a failure and not an error."""
    for i, line in enumerate(lines):
        if needle in line:
            return i
    raise AssertionError(f"no line contains {needle!r}")


def _stage_harness(tmp_path: Path):
    """Build the temp cwd a fence runs in.

    Provides the two partials a fence sources (the gate exporting an EMPTY
    `ADLC_READ_BIN` and a permissive `adlc_delegate_gate_check`, plus the
    tools-path resolver pointing at a no-op `skill-flag.sh`), and a stub
    `adlc-read` first on `$PATH` that touches a marker file when run. `$HOME` is
    an empty directory so the `|| . ~/.claude/skills/partials/…` half of each
    source line can never reach the real machine's partials.
    """
    cwd = tmp_path / "cwd"
    (cwd / ".adlc" / "partials").mkdir(parents=True)
    tools = tmp_path / "tools"
    tools.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    marker = tmp_path / "stub-was-called"

    (cwd / ".adlc" / "partials" / "delegate-gate.sh").write_text(
        'export ADLC_READ_BIN=""\n'
        "adlc_delegate_gate_check() {\n"
        "  ADLC_DELEGATE_GATE_REASON=ok\n"
        "  export ADLC_DELEGATE_GATE_REASON\n"
        "  return 0\n"
        "}\n"
    )
    (cwd / ".adlc" / "partials" / "delegate-tools-path.sh").write_text(
        f'export DELEGATE_TOOLS="{tools}"\n'
    )
    flag_sh = tools / "skill-flag.sh"
    flag_sh.write_text("#!/bin/sh\nexit 0\n")
    flag_sh.chmod(0o755)
    # The pre-pass agent's refusal path emits the sanctioned fallback record
    # (REQ-609 AC-8, second clause); a no-op keeps that branch runnable here.
    emit_sh = tools / "emit-telemetry.sh"
    emit_sh.write_text("#!/bin/sh\nexit 0\n")
    emit_sh.chmod(0o755)
    stub = bindir / "adlc-read"
    stub.write_text('#!/bin/sh\n: > "$ADLC_STUB_MARKER"\nexit 0\n')
    stub.chmod(0o755)

    env = {
        "PATH": f"{bindir}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(home),
        "ADLC_STUB_MARKER": str(marker),
    }
    return cwd, env, marker


def _run_fence(tmp_path: Path, body: str, shell: str = "/bin/sh"):
    """Run one fence body under `shell` in a fresh harness.

    The body is written to a FILE rather than passed with `-c`: `sh` reads a
    script incrementally, so a refusal that exits early is never troubled by the
    `<placeholder>` words further down a fence (which the shell would read as
    redirections). That is also the real failure mode being asserted — the
    refusal must land before anything else in the fence runs.

    The two partials are sourced by the runner before the body because
    `agents/delegate-pre-pass.md` sources them once in its step-0 fence and runs
    the whole protocol in ONE Bash invocation; its later fences legitimately
    inherit that state. Fences that source the gate themselves simply re-source
    the same fake.
    """
    cwd, env, marker = _stage_harness(tmp_path)
    script = cwd / "fence.sh"
    script.write_text(
        ". ./.adlc/partials/delegate-gate.sh\n"
        ". ./.adlc/partials/delegate-tools-path.sh\n" + body + "\n"
    )
    proc = subprocess.run(
        [shell, str(script)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc, marker


def test_each_fence_refuses_when_empty(tmp_path):
    """REQ-609 BR-12 / AC-8: every executable call-site fence, run with an empty
    `ADLC_READ_BIN`, exits non-zero, names itself and the reason on stderr, and
    never reaches `adlc-read` — under every shell in `SHELLS`.

    The positive control at the end runs the RETIRED fence shape through the
    same harness and the same empty `ADLC_READ_BIN`, and must reach the stub —
    without it, "the stub was not called" would be satisfied by a harness whose
    stub was unreachable in the first place (LESSON-602).
    """
    ran = 0
    for rel, expected_count in EXPECTED_FENCES.items():
        bodies = _fences_referencing_read_bin(rel)
        assert len(bodies) == expected_count, (
            f"{rel}: expected {expected_count} shell fence(s) referencing "
            f"ADLC_READ_BIN, found {len(bodies)}"
        )
        for n, body in enumerate(bodies):
            # Structural pins, so a fence cannot pass by having quietly lost the
            # invocation it is supposed to be guarding.
            assert 'ADLC_READ_BIN:-' not in body, (rel, n)
            assert '[ -n "$ADLC_READ_BIN" ]' in body, (rel, n)
            assert '"$ADLC_READ_BIN"' in body, (rel, n)

            # ORDER, not just presence. With an empty `ADLC_READ_BIN` the
            # invocation is an empty command word, so it fails on its own and
            # the stub is never reached — which means a guard placed AFTER the
            # invocation satisfies every runtime assertion below while breaking
            # the actual contract: refuse BEFORE the corpus is handed over
            # (BR-12), and before `mark invoked 1`, so a refusal is recorded as
            # not invoked (task AC-5). Only the text can distinguish the two.
            lines = body.splitlines()
            guard_at = _first_line_with(lines, '[ -n "$ADLC_READ_BIN" ]')
            invoke_at = _first_line_with(lines, '"$ADLC_READ_BIN" --')
            assert guard_at < invoke_at, (
                f"{rel} fence #{n}: the empty-resolver refusal is at line "
                f"{guard_at + 1} of the fence but the invocation is at line "
                f"{invoke_at + 1} — the refusal must come first"
            )
            if 'mark "$flag" invoked 1' in body:
                mark_at = _first_line_with(lines, 'mark "$flag" invoked 1')
                assert guard_at < mark_at, (
                    f"{rel} fence #{n}: the refusal must precede the "
                    "`invoked 1` telemetry mark, so a refusal is recorded as "
                    "not invoked"
                )

            for shell in SHELLS:
                proc, marker = _run_fence(tmp_path / f"case-{ran}", body, shell)
                where = (rel, n, shell)
                if EXPECTED_NONZERO_EXIT[rel]:
                    assert proc.returncode != 0, (where, proc.stdout, proc.stderr)
                else:
                    assert proc.returncode == 0, (where, proc.stdout, proc.stderr)
                assert "ADLC_READ_BIN is empty" in proc.stderr, (where, proc.stderr)
                assert EXPECTED_LABEL[rel] in proc.stderr, (where, proc.stderr)
                assert not marker.exists(), (
                    f"{rel} fence #{n} under {shell} reached adlc-read with an "
                    "empty ADLC_READ_BIN"
                )
                ran += 1

    assert ran == sum(EXPECTED_FENCES.values()) * len(SHELLS)

    # Positive control — same harness, same empty ADLC_READ_BIN, retired shape.
    for shell in SHELLS:
        proc, marker = _run_fence(tmp_path / f"control-{ran}", POSITIVE_CONTROL_FENCE, shell)
        ran += 1
        assert marker.exists(), (
            f"positive control under {shell} did not reach the stub adlc-read — "
            "the harness cannot distinguish a refusal from an unreachable stub, "
            "so the assertions above prove nothing",
            proc.stdout,
            proc.stderr,
        )
        assert proc.returncode == 0, (shell, proc.stdout, proc.stderr)
        assert "ADLC_READ_BIN is empty" not in proc.stderr


def _ac8_matches(root: Path) -> list[str]:
    """REQ-609 AC-8's grep, as `path:line:text` rows with the `./` normalised off.

    `-F` rather than a bare pattern: the literal has no metacharacters, so the
    two are equivalent, and a fixed string cannot be re-read as a regex by a
    future edit (LESSON-013's habit). The AC writes the exclusions as a second
    `grep -vE '^\\./…'`, which is a no-op on BSD grep — macOS `grep -r … .`
    prints `partials/x.md`, not `./partials/x.md`, so an anchored `^\\./` never
    matches and nothing is excluded. The prefix is stripped here and the
    exclusion applied in Python, which is the AC's intent on both greps.
    """
    proc = subprocess.run(
        ["grep", "-rn", "-F", AC8_LITERAL, "--include=*.md", "--include=*.sh", "."],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode in (0, 1), proc.stderr
    rows = []
    for line in proc.stdout.splitlines():
        if line.startswith("./"):
            line = line[2:]
        rows.append(line)
    return rows


def _ac8_excluded(row: str) -> bool:
    return row.startswith(AC8_EXCLUDED_PREFIXES)


def test_no_bare_name_fallback_outside_fixtures_and_specs(tmp_path):
    """REQ-609 AC-8: the retired bare-name fallback survives only in the frozen
    parity fixture, this REQ's own spec files, and the changelog.

    Positive control (LESSON-602): the same grep, run over a temp tree holding
    one planted `.md` and one planted `.sh` carrying the literal, must find both
    — otherwise an empty result over the repo would equally be produced by a
    wrong cwd, a typo'd pattern, or `--include` filters that match nothing. The
    exclusion predicate is pinned in the same way: it must reject a real skill
    path and accept an excluded one, so a predicate that returns True for
    everything cannot pass.
    """
    planted = tmp_path / "planted"
    (planted / "sub").mkdir(parents=True)
    (planted / "sub" / "doc.md").write_text(f'invoke "${{{AC8_LITERAL}}}" here\n')
    (planted / "sub" / "script.sh").write_text(f'"${{{AC8_LITERAL}}}" --version\n')
    (planted / "sub" / "ignored.txt").write_text(f"${{{AC8_LITERAL}}}\n")
    control = _ac8_matches(planted)
    assert sorted(row.split(":")[0] for row in control) == [
        "sub/doc.md",
        "sub/script.sh",
    ], control

    assert not _ac8_excluded("spec/SKILL.md:1:x")
    assert not _ac8_excluded("partials/delegate-gate.md:1:x")
    for prefix in AC8_EXCLUDED_PREFIXES:
        assert _ac8_excluded(f"{prefix}:1:x") or _ac8_excluded(f"{prefix}x:1:x")

    rows = _ac8_matches(REPO_ROOT)
    residual_files = {
        row.split(":")[0] for row in rows if not _ac8_excluded(row)
    }
    assert residual_files == AC8_TASK_099_RESIDUALS, (
        "REQ-609 AC-8: unexpected bare-name fallback outside the excluded "
        "surfaces.\n"
        f"  found:    {sorted(residual_files)}\n"
        f"  expected: {sorted(AC8_TASK_099_RESIDUALS)}\n"
        "If this set SHRANK, TASK-099 has rewritten the doc it names — delete "
        "the matching entry from AC8_TASK_099_RESIDUALS in this file. If it "
        "GREW, a call site has re-introduced `${ADLC_READ_BIN:-…}`; source the "
        "gate and refuse on empty instead (REQ-609 BR-12)."
    )


def test_positive_control_fence_is_the_retired_shape():
    """Pin the control to the shape the REQ retired.

    If the control drifted to the post-REQ-609 spelling it would refuse like
    everything else, the `marker.exists()` assertion above would fail, and the
    suite would look broken rather than silently weak — but this states the
    requirement directly rather than relying on that.
    """
    assert "ADLC_READ_BIN:-adlc-read" in POSITIVE_CONTROL_FENCE
    assert '[ -n "$ADLC_READ_BIN" ]' not in POSITIVE_CONTROL_FENCE
