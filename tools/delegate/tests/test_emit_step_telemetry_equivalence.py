"""AC-7 telemetry-equivalence harness for `partials/emit-step-telemetry.sh`.

REQ-436 relocated `_adlc_emit_step_telemetry` from `analyze/SKILL.md`'s inline
Step-1.5 helper into this sourceable POSIX partial (ADR-1/ADR-2/ADR-3),
removing the non-POSIX `local`s (Defect-2). BR-4 / AC-7 require the relocated
helper to emit a **byte-equivalent** telemetry record and perform the **same
`skill-flag.sh clear` call sequence** as the pre-change behavior, for every
one of the four delegation modes.

Mechanism (mirrors `test_partials.py` / `test_kimi_tools_path.py`): per mode,
stub `$KIMI_TOOLS/emit-telemetry.sh` + `$KIMI_TOOLS/skill-flag.sh` as POSIX
scripts that append their tab-joined `"$@"` to a capture file, set the
caller-env that drives that mode, source the partial under POSIX `sh` and call
`_adlc_emit_step_telemetry Step-1.5`, then assert the captured argv.

`$KIMI_TOOLS` resolution: the partial self-sources `kimi-tools-path.sh` with
the canonical two-level fallback. Sourcing a *missing* file via `.` is fatal
in POSIX `sh`, so the real `kimi-tools-path.sh` is staged at the consumer
layout `<tmp>/.adlc/partials/kimi-tools-path.sh` (the first fallback branch,
guarded by `2>/dev/null`). That resolver's branch 1 — `[ -x
tools/kimi/emit-telemetry.sh ]`, evaluated relative to cwd — then resolves
`KIMI_TOOLS=tools/kimi`, i.e. the stub dir created at `<tmp>/tools/kimi/`
(cwd is `<tmp>`). POSIX `sh` only throughout (LESSON-013): no bashisms in any
scaffold this test authors.

`duration_ms` is `(($(date -u +%s) - $start_s) * 1000)` — wall-clock derived,
so arg 7 cannot be pinned to a literal; the test asserts the first six fixed
args byte-for-byte and that arg 7 is a non-negative integer (and a multiple of
1000 — the documented whole-second resolution).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# <repo>/tools/kimi/tests/ → parents[3] == <repo> (mirrors test_kimi_tools_path.py).
REPO_ROOT = Path(__file__).resolve().parents[3]
PARTIAL = REPO_ROOT / "partials" / "emit-step-telemetry.sh"
KIMI_TOOLS_PATH_PARTIAL = REPO_ROOT / "partials" / "kimi-tools-path.sh"

_BASE_PATH = "/usr/bin:/bin"

# A capture stub: append a tab-joined record of argv to $CAPTURE. `skill-flag.sh`
# additionally exits `$1 == check` with a mode-driving status. POSIX sh only.
_EMIT_STUB = """#!/bin/sh
{ printf 'EMIT'; for a in "$@"; do printf '\\t%s' "$a"; done; printf '\\n'; } >> "$CAPTURE"
exit 0
"""


def _flag_stub(check_rc: int) -> str:
    return (
        "#!/bin/sh\n"
        '{ printf \'FLAG\'; for a in "$@"; do printf \'\\t%s\' "$a"; done; '
        "printf '\\n'; } >> \"$CAPTURE\"\n"
        f'if [ "$1" = check ]; then exit {check_rc}; fi\n'
        "exit 0\n"
    )


def _write_exec(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _run_mode(tmp_path: Path, *, check_rc: int, ask_invoked: str, kimi_exit: str):
    """Drive one mode; return the list of captured records (split on tabs)."""
    kimi = tmp_path / "tools" / "kimi"
    kimi.mkdir(parents=True)
    capture = tmp_path / "capture.txt"

    # Stage the real kimi-tools-path resolver at the consumer layout so the
    # partial's `. .adlc/partials/kimi-tools-path.sh 2>/dev/null || …`
    # self-source succeeds (a missing `.` target is fatal in POSIX sh).
    adlc_partials = tmp_path / ".adlc" / "partials"
    adlc_partials.mkdir(parents=True)
    (adlc_partials / "kimi-tools-path.sh").write_text(
        KIMI_TOOLS_PATH_PARTIAL.read_text()
    )

    _write_exec(kimi / "emit-telemetry.sh", _EMIT_STUB)
    _write_exec(kimi / "skill-flag.sh", _flag_stub(check_rc))

    fake_home = tmp_path / "home"
    fake_home.mkdir()

    env = {
        "PATH": _BASE_PATH,
        "HOME": str(fake_home),
        "CAPTURE": str(capture),
        "ASK_KIMI_INVOKED": ask_invoked,
        "KIMI_EXIT": kimi_exit,
        "flag": "FLAG123",
        "ADLC_KIMI_GATE_REASON": "gate-reason-x",
        "start_s": "100",
    }
    script = f". '{PARTIAL}'; _adlc_emit_step_telemetry Step-1.5"
    r = subprocess.run(
        ["sh", "-c", script],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert capture.is_file(), (
        "capture file never created — the stubs never ran; "
        f"stdout={r.stdout!r} stderr={r.stderr!r}"
    )
    records = [
        line.split("\t")
        for line in capture.read_text().splitlines()
        if line
    ]
    return records


def _assert_emit_argv(record, expected_first_six):
    """A captured EMIT record == ['EMIT', <8 argv>]: skill, step, req,
    gate_result, mode, reason, duration_ms. Assert the 6 fixed args exactly;
    assert duration_ms (arg 7) is a non-negative, whole-second-resolution int.
    """
    assert record[0] == "EMIT", record
    argv = record[1:]
    assert len(argv) == 7, argv  # skill..reason (6) + duration_ms (1)
    assert argv[:6] == list(expected_first_six), (argv[:6], expected_first_six)
    duration = argv[6]
    assert duration.isdigit(), duration
    assert int(duration) >= 0
    assert int(duration) % 1000 == 0, duration  # documented whole-second res.


# ---------------------------------------------------------------------------
# Mode 1 — fallback: ASK_KIMI_INVOKED empty.
#   clear (pre-emit) → emit(...fail fallback $ADLC_KIMI_GATE_REASON...) → clear
#   No `check` call. Two `clear`s total.
# ---------------------------------------------------------------------------
def test_mode_fallback(tmp_path):
    records = _run_mode(tmp_path, check_rc=1, ask_invoked="", kimi_exit="0")
    flags = [r for r in records if r[0] == "FLAG"]
    emits = [r for r in records if r[0] == "EMIT"]

    assert [r[1:] for r in flags] == [
        ["clear", "FLAG123"],
        ["clear", "FLAG123"],
    ], records
    assert len(emits) == 1, records
    _assert_emit_argv(
        emits[0],
        ["analyze", "Step-1.5", "unknown", "fail", "fallback", "gate-reason-x"],
    )
    # Ordering: clear precedes the emit which precedes the trailing clear.
    assert records[0][0] == "FLAG" and records[0][1] == "clear"
    assert records[1][0] == "EMIT"
    assert records[2][0] == "FLAG" and records[2][1] == "clear"


# ---------------------------------------------------------------------------
# Mode 2 — ghost-skip: ASK_KIMI_INVOKED set, `skill-flag.sh check` succeeds.
#   check → clear → emit(...pass ghost-skip gate-passed-no-call...) → clear
#   One `check` + two `clear`s.
# ---------------------------------------------------------------------------
def test_mode_ghost_skip(tmp_path):
    records = _run_mode(tmp_path, check_rc=0, ask_invoked="yes", kimi_exit="0")
    flags = [r for r in records if r[0] == "FLAG"]
    emits = [r for r in records if r[0] == "EMIT"]

    assert [r[1:] for r in flags] == [
        ["check", "FLAG123"],
        ["clear", "FLAG123"],
        ["clear", "FLAG123"],
    ], records
    assert len(emits) == 1, records
    _assert_emit_argv(
        emits[0],
        [
            "analyze",
            "Step-1.5",
            "unknown",
            "pass",
            "ghost-skip",
            "gate-passed-no-call",
        ],
    )
    assert records[0][:2] == ["FLAG", "check"]
    assert records[1][:2] == ["FLAG", "clear"]
    assert records[2][0] == "EMIT"
    assert records[3][:2] == ["FLAG", "clear"]


# ---------------------------------------------------------------------------
# Mode 3 — delegated: ASK_KIMI_INVOKED set, check FAILS, KIMI_EXIT == 0.
#   check (fails) → emit(...pass delegated ok...) → clear
#   One `check` + ONE `clear` (no pre-emit clear on this branch).
# ---------------------------------------------------------------------------
def test_mode_delegated(tmp_path):
    records = _run_mode(tmp_path, check_rc=9, ask_invoked="yes", kimi_exit="0")
    flags = [r for r in records if r[0] == "FLAG"]
    emits = [r for r in records if r[0] == "EMIT"]

    assert [r[1:] for r in flags] == [
        ["check", "FLAG123"],
        ["clear", "FLAG123"],
    ], records
    assert len(emits) == 1, records
    _assert_emit_argv(
        emits[0],
        ["analyze", "Step-1.5", "unknown", "pass", "delegated", "ok"],
    )
    assert records[0][:2] == ["FLAG", "check"]
    assert records[1][0] == "EMIT"
    assert records[2][:2] == ["FLAG", "clear"]


# ---------------------------------------------------------------------------
# Mode 4 — api-error: ASK_KIMI_INVOKED set, check FAILS, KIMI_EXIT != 0.
#   check (fails) → emit(...pass fallback api-error...) → clear
#   One `check` + ONE `clear`. Same call shape as delegated; mode/reason differ.
# ---------------------------------------------------------------------------
def test_mode_api_error(tmp_path):
    records = _run_mode(tmp_path, check_rc=9, ask_invoked="yes", kimi_exit="7")
    flags = [r for r in records if r[0] == "FLAG"]
    emits = [r for r in records if r[0] == "EMIT"]

    assert [r[1:] for r in flags] == [
        ["check", "FLAG123"],
        ["clear", "FLAG123"],
    ], records
    assert len(emits) == 1, records
    _assert_emit_argv(
        emits[0],
        ["analyze", "Step-1.5", "unknown", "pass", "fallback", "api-error"],
    )
    assert records[0][:2] == ["FLAG", "check"]
    assert records[1][0] == "EMIT"
    assert records[2][:2] == ["FLAG", "clear"]


# ---------------------------------------------------------------------------
# The step label is passed straight through as the `step` field (arg 2).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("step", ["Step-1.5", "Step-1.6"])
def test_step_label_passthrough(tmp_path, step):
    kimi = tmp_path / "tools" / "kimi"
    kimi.mkdir(parents=True)
    capture = tmp_path / "capture.txt"
    adlc_partials = tmp_path / ".adlc" / "partials"
    adlc_partials.mkdir(parents=True)
    (adlc_partials / "kimi-tools-path.sh").write_text(
        KIMI_TOOLS_PATH_PARTIAL.read_text()
    )
    _write_exec(kimi / "emit-telemetry.sh", _EMIT_STUB)
    _write_exec(kimi / "skill-flag.sh", _flag_stub(1))
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = {
        "PATH": _BASE_PATH,
        "HOME": str(fake_home),
        "CAPTURE": str(capture),
        "ASK_KIMI_INVOKED": "",
        "KIMI_EXIT": "0",
        "flag": "F",
        "ADLC_KIMI_GATE_REASON": "r",
        "start_s": "100",
        "STEP": step,
    }
    # Pass the step label via the environment, not f-string interpolation, so a
    # future parametrize value containing shell metacharacters cannot inject.
    r = subprocess.run(
        ["sh", "-c", f'. \'{PARTIAL}\'; _adlc_emit_step_telemetry "$STEP"'],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    emits = [
        line.split("\t")
        for line in capture.read_text().splitlines()
        if line.startswith("EMIT")
    ]
    assert len(emits) == 1
    assert emits[0][2] == step, emits[0]


# ---------------------------------------------------------------------------
# BR-4 / LESSON-008: telemetry never blocks. Even with NO `tools/kimi` and no
# resolver staged, sourcing the partial + calling the function must not abort
# the caller (exit 0). The defensive `KIMI_TOOLS=tools/kimi` default + the
# `2>/dev/null || …` self-source degrade keep it a silent no-op.
# ---------------------------------------------------------------------------
def test_telemetry_never_blocks_when_tools_absent(tmp_path):
    # Stage the resolver (its `.` target must exist — fatal otherwise) but NO
    # tools/kimi anywhere, so KIMI_TOOLS degrades to a non-existent tools/kimi
    # and the skill-flag/emit calls fail silently without aborting the shell.
    adlc_partials = tmp_path / ".adlc" / "partials"
    adlc_partials.mkdir(parents=True)
    (adlc_partials / "kimi-tools-path.sh").write_text(
        KIMI_TOOLS_PATH_PARTIAL.read_text()
    )
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = {
        "PATH": _BASE_PATH,
        "HOME": str(fake_home),
        "ASK_KIMI_INVOKED": "",
        "KIMI_EXIT": "0",
        "flag": "F",
        "ADLC_KIMI_GATE_REASON": "r",
        "start_s": "100",
    }
    r = subprocess.run(
        ["sh", "-c", f". '{PARTIAL}'; _adlc_emit_step_telemetry Step-1.5; echo DONE"],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "DONE" in r.stdout, (r.stdout, r.stderr)
