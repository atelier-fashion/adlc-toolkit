"""Execution tests for the post-REQ-609 delegate call-site fences (BR-12, AC-8).

`tools/lint-skills/check.py`'s `read-bin-fallback` check is a *structural* guard:
it proves no fence contains `ADLC_READ_BIN:-`, that every invocation goes through
`command`, and that the absolute-path guard precedes it. That is not the same
claim as "an unusable `ADLC_READ_BIN` actually stops the corpus leaving the
machine" — a fence could satisfy every literal and still hand a temp file over.
So these tests take the real fences out of the real skill files and RUN them —
under `sh`, and under `zsh`/`bash` where the machine has them, because the Bash
tool that actually executes skill fences runs zsh on macOS (LESSON-329) —
against a fake gate partial that exports an unusable `ADLC_READ_BIN`, with a stub
`adlc-read` first on `$PATH` that records having been called. The assertion is
the outcome (LESSON-478): the fence refuses, names itself and the reason on
stderr, and the stub is never reached.

Three refusal/interception properties are covered, each with its own positive
control in the same run, because every refusal assertion here is negative ("the
stub was not called") and a completely broken harness produces the same thing
(LESSON-602):

1. **Empty** `ADLC_READ_BIN` — the resolver declined. Control: the RETIRED
   `${ADLC_READ_BIN:-adlc-read}` shape, same harness, must reach the stub.
2. **Bare name** `ADLC_READ_BIN=adlc-read` — what a consumer repo's *stale*
   vendored gate still exports on a `$PATH` hit. The retired `[ -n … ]` guard
   passes it straight through, so the guard is an absolute-path test. Control:
   a fence carrying that legacy `[ -n … ]` guard, same harness, must reach the
   stub — which is the defect stated as an executable fact.
3. **A function named with the resolved absolute path.** bash and zsh both
   permit `function /abs/path/adlc-read`, and a bare `"$ADLC_READ_BIN"` then
   runs the function instead of the file the resolver proved is there. Every
   invocation therefore goes through `command`, exactly as the gate's own probe
   does (REQ-609 ADR-3). Control: the same fence text without `command`, same
   planted function, must run the function and NOT the file.
"""
from __future__ import annotations

import importlib.util
import re
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
# grep test and by `test_analyze_prose_bullet_matches_the_fence_contract` below,
# both of which are text-based and see prose.
EXPECTED_FENCES = {
    "agents/delegate-pre-pass.md": 2,
    "analyze/SKILL.md": 1,
    "proceed/SKILL.md": 1,
    "spec/SKILL.md": 2,
    "wrapup/SKILL.md": 1,
}

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

# The stderr label each file's refusal must carry, so a copy-pasted message from
# a neighbouring skill is a failure rather than a pass.
EXPECTED_LABEL = {
    "agents/delegate-pre-pass.md": "delegate-pre-pass:",
    "analyze/SKILL.md": "/analyze:",
    "proceed/SKILL.md": "/proceed:",
    "spec/SKILL.md": "/spec:",
    "wrapup/SKILL.md": "/wrapup:",
}

# The three literals the call-site contract is written in. Pinned here and in
# `check.py`; the linter's own tests pin the linter's copy.
GUARD_LITERAL = 'case "$ADLC_READ_BIN" in /*)'
INVOKE_LITERAL = 'command "$ADLC_READ_BIN" --'
# The refusal message's stable half. Not "is empty" any more: the same guard now
# refuses a bare name, so the message names the condition (`is not an absolute
# path`) and quotes the offending value.
REFUSAL_SUBSTRING = "ADLC_READ_BIN is"

# Fences in the shapes this REQ retired. They live here, in a `.py` file, on
# purpose: the AC-8 grep covers `*.md` and `*.sh` only, so a control cannot
# pollute the surface it is controlling for.
POSITIVE_CONTROL_FENCE = (
    ". .adlc/partials/delegate-gate.sh 2>/dev/null"
    " || . ~/.claude/skills/partials/delegate-gate.sh\n"
    '"${ADLC_READ_BIN:-adlc-read}" --no-warn --paths ./corpus.txt'
    ' --question "summarize"\n'
)
# The REQ-609-as-landed guard, before this pass strengthened it: `[ -n … ]` is
# satisfied by ANY non-empty value, including the bare name a stale vendored
# gate exports on a `$PATH` hit.
LEGACY_NONEMPTY_GUARD_FENCE = (
    ". .adlc/partials/delegate-gate.sh 2>/dev/null"
    " || . ~/.claude/skills/partials/delegate-gate.sh\n"
    '[ -n "$ADLC_READ_BIN" ] || { echo "/control: ADLC_READ_BIN is empty" >&2;'
    " exit 1; }\n"
    'command "$ADLC_READ_BIN" --no-warn --paths ./corpus.txt'
    ' --question "summarize"\n'
)
# The invocation without `command`, which is what a function named with the
# resolved absolute path intercepts.
NO_COMMAND_PREFIX_FENCE = (
    '"$ADLC_READ_BIN" --no-warn --paths ./corpus.txt --question "summarize"\n'
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
# EMPTY, and it stays empty. TASK-098 landed with one residual here —
# `partials/delegate-gate.md`, whose call-site contract paragraph still
# prescribed the retired spelling and which TASK-098 was not allowed to edit.
# TASK-099 rewrote that paragraph (REQ-609 BR-15), so the waiver was deleted with
# the reason for it. The assertion below is an exact match, not a subset,
# precisely so that a waiver cannot outlive its reason — an allowlist that
# survives the thing it excused is the guard-rot class LESSON-019 is about.
AC8_TASK_099_RESIDUALS = set()

# Skill fences are executed by Claude's Bash tool, whose shell on macOS is zsh —
# not the `sh` the fence is written against (LESSON-329: lint checks structure,
# only execution catches shell-semantics divergence). `/bin/sh` is the contract
# and is always required; the others are asserted where the machine has them, so
# a Linux CI box without zsh does not fail and a developer machine still gets the
# real executor shell covered. REQ-609 BR-16.
SHELLS = ["/bin/sh"] + [
    sh for sh in ("/bin/zsh", "/bin/bash") if Path(sh).is_file()
]

# The shells that can define a function whose name is an absolute path. bash and
# zsh both accept it; `/bin/sh` (bash in POSIX mode) rejects the definition with
# "not a valid identifier", so there is nothing to intercept with and the
# interception test would be vacuous there rather than meaningful.
FN_SHELLS = [sh for sh in ("/bin/zsh", "/bin/bash") if Path(sh).is_file()]

# Placeholders a fence writes where a real run would carry paths. They are
# unquoted, so a shell reads `<file1>` as a redirection and the invocation never
# runs — which is harmless for the refusal tests (nothing gets that far) but
# would make the `command`-interception test vacuous, since "the stub was not
# reached" is exactly what it asserts against. Substituted for a real path so
# the invocation actually executes.
PLACEHOLDER_PATHS = {
    "<file1> <file2> ...": "./corpus.txt",
    "<INTAKE_CORPUS literal>": "./corpus.txt",
    "<top-15 paths>": "./corpus.txt",
}


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


def _runnable(body: str) -> str:
    """A fence body with its unquoted `<placeholder>` paths made real."""
    for placeholder, real in PLACEHOLDER_PATHS.items():
        body = body.replace(placeholder, real)
    assert "--paths <" not in body, (
        "a fence still carries an unquoted <placeholder> after --paths; add it "
        "to PLACEHOLDER_PATHS, or the interception test cannot reach the "
        "invocation and proves nothing"
    )
    return body


def _first_line_with(lines: list[str], needle: str) -> int:
    """Index of the first line containing `needle`; asserts rather than raising
    StopIteration, so a missing anchor reads as a failure and not an error."""
    for i, line in enumerate(lines):
        if needle in line:
            return i
    raise AssertionError(f"no line contains {needle!r}")


def _stage_harness(tmp_path: Path, read_bin: str = "", jsonl: str | None = None):
    """Build the temp cwd a fence runs in.

    Provides the two partials a fence sources (the gate exporting `read_bin` as
    `ADLC_READ_BIN` and a permissive `adlc_delegate_gate_check`, plus the
    tools-path resolver pointing at no-op sidecar tools), and a stub `adlc-read`
    first on `$PATH` that touches a marker file when run. `$HOME` is an empty
    directory so the `|| . ~/.claude/skills/partials/…` half of each source line
    can never reach the real machine's partials.

    `skill-flag.sh` answers `read <flag> jsonl` with a real path and
    `extract-chat` produces a real file, because `wrapup`'s fence delegates only
    inside the `[ -n "$JSONL" ]` branch: without both stubs the fence would take
    its no-candidates fallback, never reach the guard, and every assertion below
    would pass against a fence that had simply stopped delegating.
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
    fn_marker = tmp_path / "function-was-called"
    (cwd / "corpus.txt").write_text("corpus\n")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("{}\n")

    (cwd / ".adlc" / "partials" / "delegate-gate.sh").write_text(
        f'export ADLC_READ_BIN="{read_bin}"\n'
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
    flag_sh.write_text(
        "#!/bin/sh\n"
        "# mark → no-op. read <flag> jsonl → whatever $ADLC_FAKE_JSONL holds, so\n"
        "# a test can put wrapup's fence on its DELEGATING branch (a transcript\n"
        "# was found) or on its no-candidates branch (empty).\n"
        'if [ "$1" = "read" ] && [ "$3" = "jsonl" ]; then\n'
        '  printf \'%s\\n\' "${ADLC_FAKE_JSONL}"\n'
        "fi\n"
        "exit 0\n"
    )
    flag_sh.chmod(0o755)
    # The pre-pass agent's refusal path emits a telemetry record (REQ-609 AC-8,
    # second clause); a no-op keeps that branch runnable here.
    emit_sh = tools / "emit-telemetry.sh"
    emit_sh.write_text("#!/bin/sh\nexit 0\n")
    emit_sh.chmod(0o755)
    # `wrapup` extracts the transcript before delegating; without this the
    # extract failure branch swallows the run before the guard.
    extract = bindir / "extract-chat"
    extract.write_text('#!/bin/sh\n: > "$3"\nexit 0\n')
    extract.chmod(0o755)
    stub = bindir / "adlc-read"
    stub.write_text('#!/bin/sh\n: > "$ADLC_STUB_MARKER"\nexit 0\n')
    stub.chmod(0o755)

    env = {
        "PATH": f"{bindir}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(home),
        "ADLC_STUB_MARKER": str(marker),
        "ADLC_FN_MARKER": str(fn_marker),
        "ADLC_FAKE_JSONL": str(transcript) if jsonl is None else jsonl,
    }
    return cwd, env, marker, fn_marker


def _run_fence(
    tmp_path: Path,
    body: str,
    shell: str = "/bin/sh",
    read_bin: str = "",
    plant_function: bool = False,
    jsonl: str | None = None,
):
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

    `plant_function` defines a shell function whose NAME is the resolved
    absolute path, which is what `command` exists to bypass (REQ-609 ADR-3).
    """
    cwd, env, marker, fn_marker = _stage_harness(tmp_path, read_bin, jsonl)
    prelude = ""
    if plant_function:
        prelude = 'eval "$ADLC_READ_BIN() { : > \\"$ADLC_FN_MARKER\\"; }"\n'
    script = cwd / "fence.sh"
    script.write_text(
        ". ./.adlc/partials/delegate-gate.sh\n"
        ". ./.adlc/partials/delegate-tools-path.sh\n" + prelude + body + "\n"
    )
    proc = subprocess.run(
        [shell, str(script)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc, marker, fn_marker


def _assert_fence_shape(rel: str, n: int, body: str) -> None:
    """The structural half of the call-site contract, asserted on the text.

    Runtime alone cannot see it: with an unusable `ADLC_READ_BIN` the invocation
    fails on its own, so a guard placed AFTER the invocation — or dropped
    entirely — satisfies every runtime assertion while breaking the actual
    contract (refuse BEFORE the corpus is handed over, and before
    `mark invoked 1`, so a refusal is recorded as not invoked).
    """
    assert "ADLC_READ_BIN:-" not in body, (rel, n)
    assert GUARD_LITERAL in body, (rel, n)
    assert INVOKE_LITERAL in body, (rel, n)
    # No invocation may skip `command`. Every `"$ADLC_READ_BIN"` followed by a
    # flag must carry the prefix — a second, unprefixed invocation elsewhere in
    # the fence would be the whole defect, re-introduced.
    for line in body.splitlines():
        if '"$ADLC_READ_BIN" -' in line:
            assert INVOKE_LITERAL in line, (
                f"{rel} fence #{n}: `{line.strip()}` invokes ADLC_READ_BIN "
                "without the `command` prefix — a function named with the "
                "resolved absolute path would intercept it (REQ-609 ADR-3)"
            )

    lines = body.splitlines()
    guard_at = _first_line_with(lines, GUARD_LITERAL)
    invoke_at = _first_line_with(lines, INVOKE_LITERAL)
    assert guard_at < invoke_at, (
        f"{rel} fence #{n}: the refusal is at line {guard_at + 1} of the fence "
        f"but the invocation is at line {invoke_at + 1} — the refusal must "
        "come first"
    )
    if 'mark "$flag" invoked 1' in body:
        mark_at = _first_line_with(lines, 'mark "$flag" invoked 1')
        assert guard_at < mark_at, (
            f"{rel} fence #{n}: the refusal must precede the `invoked 1` "
            "telemetry mark, so a refusal is recorded as not invoked"
        )


def _assert_refuses(rel: str, n: int, body: str, tmp_path: Path, read_bin: str):
    """Every shell refuses `read_bin`, names itself, and never reaches the stub."""
    ran = 0
    for shell in SHELLS:
        proc, marker, _fn = _run_fence(
            tmp_path / f"{shell.replace('/', '_')}-{ran}", body, shell, read_bin
        )
        where = (rel, n, shell, read_bin)
        # The security property first: whatever else a weakened fence does, the
        # finding that matters is that the corpus reached a binary the resolver
        # never vouched for. Asserted ahead of the exit code so a regression
        # reports the handover rather than the status it happened to exit with.
        assert not marker.exists(), (
            f"{rel} fence #{n} under {shell} reached adlc-read with "
            f"ADLC_READ_BIN={read_bin!r}",
            proc.stdout,
            proc.stderr,
        )
        if EXPECTED_NONZERO_EXIT[rel]:
            assert proc.returncode != 0, (where, proc.stdout, proc.stderr)
        else:
            assert proc.returncode == 0, (where, proc.stdout, proc.stderr)
        assert REFUSAL_SUBSTRING in proc.stderr, (where, proc.stderr)
        assert EXPECTED_LABEL[rel] in proc.stderr, (where, proc.stderr)
        ran += 1
    return ran


def test_each_fence_refuses_when_empty(tmp_path):
    """REQ-609 BR-12 / AC-8: every executable call-site fence, run with an empty
    `ADLC_READ_BIN`, refuses, names itself and the reason on stderr, and never
    reaches `adlc-read` — under every shell in `SHELLS`.

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
            _assert_fence_shape(rel, n, body)
            ran += _assert_refuses(rel, n, body, tmp_path / f"case-{ran}", "")

    assert ran == sum(EXPECTED_FENCES.values()) * len(SHELLS)

    # Positive control — same harness, same empty ADLC_READ_BIN, retired shape.
    for shell in SHELLS:
        proc, marker, _fn = _run_fence(
            tmp_path / f"control-{ran}", POSITIVE_CONTROL_FENCE, shell
        )
        ran += 1
        assert marker.exists(), (
            f"positive control under {shell} did not reach the stub adlc-read — "
            "the harness cannot distinguish a refusal from an unreachable stub, "
            "so the assertions above prove nothing",
            proc.stdout,
            proc.stderr,
        )
        assert proc.returncode == 0, (shell, proc.stdout, proc.stderr)
        assert REFUSAL_SUBSTRING not in proc.stderr


def test_each_fence_refuses_a_bare_name(tmp_path):
    """REQ-609 BR-12: a BARE `ADLC_READ_BIN=adlc-read` is refused too.

    The canonical gate exports an absolute path or empty and nothing else — but
    a consumer repo whose `.adlc/partials/delegate-gate.sh` predates REQ-609
    still exports the bare name on a `$PATH` hit, and `/init` is what re-vendors
    it. A `[ -n … ]` guard passes that value straight through to the shell's
    lookup machinery, which is the resolution the gate walks `$PATH` precisely to
    avoid (BUG-209). So the guard tests for an absolute path, not for non-empty.

    Positive control: the LEGACY `[ -n … ]` guard, identical harness and value,
    must reach the stub. That is the defect stated as an executable fact rather
    than as a claim — and it is what fails if the guard is ever weakened back.
    """
    ran = 0
    for rel, expected_count in EXPECTED_FENCES.items():
        bodies = _fences_referencing_read_bin(rel)
        assert len(bodies) == expected_count, (rel, len(bodies))
        for n, body in enumerate(bodies):
            ran += _assert_refuses(
                rel, n, body, tmp_path / f"bare-{ran}", "adlc-read"
            )

    assert ran == sum(EXPECTED_FENCES.values()) * len(SHELLS)

    for shell in SHELLS:
        proc, marker, _fn = _run_fence(
            tmp_path / f"legacy-{ran}",
            LEGACY_NONEMPTY_GUARD_FENCE,
            shell,
            read_bin="adlc-read",
        )
        ran += 1
        assert marker.exists(), (
            f"the legacy `[ -n \"$ADLC_READ_BIN\" ]` guard under {shell} did "
            "NOT hand the corpus to a bare name — the harness is not "
            "reproducing the defect, so the refusals above prove nothing",
            proc.stdout,
            proc.stderr,
        )
        assert proc.returncode == 0, (shell, proc.stdout, proc.stderr)


def test_wrapup_no_candidates_branch_is_not_a_hard_error(tmp_path):
    """REQ-609 (verify C5): `wrapup`'s refusal lives in the branch that DELEGATES.

    Step 2's fence delegates only when step 1 found a transcript. Hoisted above
    the `[ -z "$JSONL" ]` test, the guard turned "no candidate transcript" — an
    ordinary non-delegating fallback that BR-9 routes to Fallback drafting — into
    a hard `exit 1` on every machine that has not opted into delegation, which is
    every fresh install.

    So: with no transcript AND an unusable resolver, the fence exits 0 and says
    nothing about `ADLC_READ_BIN`. The positive control is the same fence, same
    unusable resolver, WITH a transcript: it must refuse — otherwise "no refusal
    was printed" would also be produced by a fence that had stopped guarding.
    """
    bodies = _fences_referencing_read_bin("wrapup/SKILL.md")
    assert len(bodies) == 1
    body = bodies[0]

    for shell in SHELLS:
        proc, marker, _fn = _run_fence(
            tmp_path / f"nojsonl-{shell.replace('/', '_')}",
            body, shell, read_bin="", jsonl="",
        )
        assert proc.returncode == 0, (shell, proc.stdout, proc.stderr)
        assert REFUSAL_SUBSTRING not in proc.stderr, (shell, proc.stderr)
        assert not marker.exists(), (shell, proc.stdout, proc.stderr)

        proc, marker, _fn = _run_fence(
            tmp_path / f"withjsonl-{shell.replace('/', '_')}",
            body, shell, read_bin="",
        )
        assert proc.returncode != 0, (
            f"the wrapup fence under {shell} did NOT refuse an unusable "
            "ADLC_READ_BIN on its delegating branch — the no-candidates "
            "assertion above is then satisfied by a fence that guards nothing",
            proc.stdout,
            proc.stderr,
        )
        assert REFUSAL_SUBSTRING in proc.stderr, (shell, proc.stderr)
        assert not marker.exists(), (shell, proc.stdout, proc.stderr)


def test_command_prefix_defeats_an_absolute_path_function(tmp_path):
    """REQ-609 ADR-3: every invocation goes through `command`.

    bash and zsh both permit a function whose NAME is an absolute path, and a
    bare `"$ADLC_READ_BIN"` then runs that function instead of the file the
    resolver proved is on disk — so a planted function receives the corpus even
    though the resolver never consulted shell state. `command` bypasses function
    and alias lookup, which is exactly why the gate's own probe uses it.

    Both directions are asserted in the same run: the real fences (with
    `command`) must run the FILE, and the identical invocation without `command`
    must run the FUNCTION. The second half is the positive control — without it,
    "the function did not run" would also be produced by a shell that never
    accepted the definition, or a marker path nothing could write (LESSON-602).

    `/bin/sh` is excluded on purpose: bash in POSIX mode rejects the definition
    with "not a valid identifier", so there would be nothing to intercept with.
    """
    if not FN_SHELLS:  # pragma: no cover - developer machines all have one
        import pytest

        pytest.skip("no bash or zsh on this machine")

    ran = 0
    for rel, expected_count in EXPECTED_FENCES.items():
        bodies = _fences_referencing_read_bin(rel)
        assert len(bodies) == expected_count, (rel, len(bodies))
        for n, body in enumerate(bodies):
            runnable = _runnable(body)
            for shell in FN_SHELLS:
                case = tmp_path / f"fn-{ran}"
                # The resolved value has to be the stub's real absolute path, so
                # the guard passes and the function's name collides with it.
                stub_path = str(case / "bin" / "adlc-read")
                proc, marker, fn_marker = _run_fence(
                    case, runnable, shell, read_bin=stub_path,
                    plant_function=True,
                )
                where = (rel, n, shell)
                # Contract first, vacuity guard second. Reversed, a fence that
                # lost its `command` prefix fails on "the real binary did not
                # run", which is true but describes the symptom rather than the
                # defect — the interception is what happened.
                assert not fn_marker.exists(), (
                    f"{rel} fence #{n} under {shell} ran a FUNCTION named "
                    f"{stub_path} instead of the file — the invocation is "
                    "missing its `command` prefix (REQ-609 ADR-3)",
                    where,
                    proc.stdout,
                    proc.stderr,
                )
                assert marker.exists(), (
                    f"{rel} fence #{n} under {shell} did not run the real "
                    "adlc-read — the invocation never happened, so the "
                    "interception assertion above is vacuous",
                    proc.stdout,
                    proc.stderr,
                )
                ran += 1

    assert ran == sum(EXPECTED_FENCES.values()) * len(FN_SHELLS)

    # Positive control: the same invocation WITHOUT `command` is intercepted.
    for shell in FN_SHELLS:
        case = tmp_path / f"fn-control-{ran}"
        stub_path = str(case / "bin" / "adlc-read")
        proc, marker, fn_marker = _run_fence(
            case, NO_COMMAND_PREFIX_FENCE, shell, read_bin=stub_path,
            plant_function=True,
        )
        ran += 1
        assert fn_marker.exists(), (
            f"the unprefixed invocation under {shell} was NOT intercepted by a "
            f"function named {stub_path} — the harness is not reproducing the "
            "hazard, so the `command` assertions above prove nothing",
            proc.stdout,
            proc.stderr,
        )
        assert not marker.exists(), (shell, proc.stdout, proc.stderr)


def test_analyze_prose_bullet_matches_the_fence_contract():
    """`analyze/SKILL.md` Step 1.5 is a call site written as PROSE, so neither
    the linter (fences only) nor the execution tests above can see it.

    It carries the same three obligations as every fence — the absolute-path
    guard, the `command` prefix, and the guard BEFORE `mark invoked 1` — and the
    ordering is the one that was wrong: the bullet told an author to mark the
    call as invoked and only then refuse, so a refusal would have been recorded
    as a delegated call that produced nothing.
    """
    text = (REPO_ROOT / "analyze" / "SKILL.md").read_text(encoding="utf-8")
    bullets = [
        line for line in text.splitlines()
        if "ADLC_READ_BIN" in line and line.lstrip().startswith("- ")
    ]
    assert len(bullets) == 1, bullets
    bullet = bullets[0]

    assert "ADLC_READ_BIN:-" not in bullet
    assert GUARD_LITERAL in bullet
    assert INVOKE_LITERAL in bullet
    assert bullet.index(GUARD_LITERAL) < bullet.index(INVOKE_LITERAL), bullet
    mark_at = bullet.index('mark "$flag" invoked 1')
    assert bullet.index(GUARD_LITERAL) < mark_at, (
        "Step 1.5's bullet still orders `mark invoked 1` before the refusal — "
        "a refusal would be recorded as an invoked call (REQ-609 BR-12)"
    )


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
        "The expected set is EMPTY since TASK-099. A call site has "
        "re-introduced `${ADLC_READ_BIN:-…}`; source the gate and refuse on "
        "a non-absolute value instead (REQ-609 BR-12). Do not widen this set to "
        "make the failure go away — that is the guard rot LESSON-019 names."
    )


def test_control_fences_are_the_retired_shapes():
    """Pin each control to the shape it is controlling for.

    If a control drifted to the post-REQ-609 spelling it would refuse like
    everything else, its `marker.exists()` assertion would fail, and the suite
    would look broken rather than silently weak — but this states the
    requirement directly rather than relying on that.
    """
    assert "ADLC_READ_BIN:-adlc-read" in POSITIVE_CONTROL_FENCE
    assert GUARD_LITERAL not in POSITIVE_CONTROL_FENCE

    assert '[ -n "$ADLC_READ_BIN" ]' in LEGACY_NONEMPTY_GUARD_FENCE
    assert GUARD_LITERAL not in LEGACY_NONEMPTY_GUARD_FENCE

    assert INVOKE_LITERAL not in NO_COMMAND_PREFIX_FENCE
    assert '"$ADLC_READ_BIN" --' in NO_COMMAND_PREFIX_FENCE


def test_pre_pass_miss_reason_is_derived_in_the_fence_that_emits_it():
    """Step D finding: the pre-pass agent's miss record read `read_bin_missing`
    from a different fenced block, and fenced blocks share no shell state, so
    it always defaulted to key-absent. The reason must be derived from the
    exported ADLC_READ_BIN in the same fence that emits the record, and no
    fence may read the cross-fence variable."""
    text = (REPO_ROOT / "agents" / "delegate-pre-pass.md").read_text(encoding="utf-8")
    fences = re.findall(r"```(?:sh|bash)\n(.*?)```", text, re.S)
    # A `:-` default on that variable is the cross-fence read; comments may explain it.
    live = [l for f in fences for l in f.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert not [l for l in live if "${read_bin_missing:-" in l], [l for l in live if "read_bin_missing:-" in l]
    emitting = [f for f in fences if "emit-telemetry.sh delegate-pre-pass" in f and "key-absent" in f]
    assert emitting, "no fence emits the key-absent/no-binary miss record"
    for body in emitting:
        assert 'case "$ADLC_READ_BIN" in' in body, body
        assert "no-binary" in body and "key-absent" in body, body
    # Nothing may record the delegate as invoked without a call: the only
    # gate=pass fallback reason is api-error, and it appears only after a real
    # invocation line.
    def _live(body):
        return [l for l in body.splitlines() if l.strip() and not l.strip().startswith("#")]
    api_error = [i for i, f in enumerate(fences) if any("reason=api-error" in l for l in _live(f))]
    invoking = [i for i, f in enumerate(fences) if 'command "$ADLC_READ_BIN" --no-warn' in f]
    assert len(api_error) == 1, api_error          # exactly one sanctioned record
    assert invoking, "no fence invokes the delegate"
    assert api_error[0] > invoking[0], (api_error, invoking)   # and it follows the real call
