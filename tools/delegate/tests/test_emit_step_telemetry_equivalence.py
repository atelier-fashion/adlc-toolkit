"""Telemetry resolution harness for `partials/emit-step-telemetry.sh` (REQ-522).

REQ-522 ADR-3/ADR-4 restructured the per-step telemetry to be **flag-file
derived**: the skill `mark`s start_s / invoked / exit / reason to the flag-file
sidecar (`skill-flag.sh mark`), and `_adlc_emit_step_telemetry <skill> <step>`
reads them back (`skill-flag.sh read`) instead of from caller shell vars. This
fixes the inert-telemetry bug (every run previously resolved to
`mode=fallback,gate=fail` because the caller vars were empty across the fence
boundary), and makes the `delegated` / `ghost-skip` branches reachable.

This harness uses the REAL `skill-flag.sh` (so the mark/read round-trip is
exercised end-to-end, AC-2/AC-3) and stubs only `emit-telemetry.sh` to capture
the resolved argv. Each mode marks the appropriate sidecar keys, calls the
partial, and asserts the emitted record + that no flag file remains afterward.

`duration_ms` is wall-clock derived (`(now - start_s) * 1000`), so it is
asserted to be a non-negative whole-second-resolution int, not a fixed literal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# <repo>/tools/delegate/tests/ → parents[3] == <repo>.
REPO_ROOT = Path(__file__).resolve().parents[3]
PARTIAL = REPO_ROOT / "partials" / "emit-step-telemetry.sh"
TOOLS_PATH_PARTIAL = REPO_ROOT / "partials" / "delegate-tools-path.sh"
REAL_SKILL_FLAG = REPO_ROOT / "tools" / "delegate" / "skill-flag.sh"

_BASE_PATH = "/usr/bin:/bin"

# A capture stub for emit-telemetry.sh: append a tab-joined record of argv to
# $CAPTURE. POSIX sh only.
_EMIT_STUB = """#!/bin/sh
{ printf 'EMIT'; for a in "$@"; do printf '\\t%s' "$a"; done; printf '\\n'; } >> "$CAPTURE"
exit 0
"""


def _write_exec(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _stage(tmp_path: Path):
    """Stage tools/delegate (real skill-flag.sh + emit stub) and the resolver.

    Returns (delegate_dir, capture_path). The partial self-sources
    `delegate-tools-path.sh` (a missing `.` target is fatal in POSIX sh), so the
    real resolver is staged at the consumer layout `<tmp>/.adlc/partials/`. The
    resolver's branch-1 `[ -x tools/delegate/emit-telemetry.sh ]` (relative to
    cwd=<tmp>) then resolves DELEGATE_TOOLS to the staged `<tmp>/tools/delegate`.
    """
    delegate = tmp_path / "tools" / "delegate"
    delegate.mkdir(parents=True)
    capture = tmp_path / "capture.txt"

    adlc_partials = tmp_path / ".adlc" / "partials"
    adlc_partials.mkdir(parents=True)
    (adlc_partials / "delegate-tools-path.sh").write_text(
        TOOLS_PATH_PARTIAL.read_text()
    )

    _write_exec(delegate / "emit-telemetry.sh", _EMIT_STUB)
    # Use the REAL skill-flag.sh so mark/read/clear are exercised for real.
    _write_exec(delegate / "skill-flag.sh", REAL_SKILL_FLAG.read_text())
    return delegate, capture


def _run_mode(tmp_path: Path, *, marks: dict):
    """Create a real flag, apply the given sidecar marks, run the resolver, and
    return (records, flag_path). `marks` maps key->value (omit a key to leave it
    unmarked — e.g. omit `invoked` for the not-invoked mode, omit `exit` for
    ghost-skip)."""
    delegate, capture = _stage(tmp_path)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    base_env = {"PATH": _BASE_PATH, "HOME": str(fake_home), "CAPTURE": str(capture)}

    sf = str(delegate / "skill-flag.sh")
    # Create a real flag file.
    flag = subprocess.run(
        ["sh", "-c", f"'{sf}' create"], env=base_env, cwd=str(tmp_path),
        capture_output=True, text=True,
    ).stdout.strip()
    assert flag, "skill-flag.sh create returned no path"

    for k, v in marks.items():
        subprocess.run(
            ["sh", "-c", f"'{sf}' mark '{flag}' {k} '{v}'"],
            env=base_env, cwd=str(tmp_path), check=True,
        )

    env = dict(base_env)
    env["flag"] = flag
    env["REQ_NUM"] = "REQ-522"
    script = f". '{PARTIAL}'; _adlc_emit_step_telemetry analyze Step-1.5"
    r = subprocess.run(
        ["sh", "-c", script], env=env, cwd=str(tmp_path),
        capture_output=True, text=True,
    )
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert capture.is_file(), (
        f"capture never created — stubs never ran; stdout={r.stdout!r} stderr={r.stderr!r}"
    )
    records = [
        line.split("\t") for line in capture.read_text().splitlines() if line
    ]
    return records, flag


def _assert_emit_argv(record, expected_first_six):
    """A captured EMIT record == ['EMIT', skill, step, req, gate, mode, reason,
    duration_ms]. Assert the 6 fixed args exactly; assert duration_ms is a
    non-negative whole-second-resolution int OR '-' (unmeasured)."""
    assert record[0] == "EMIT", record
    argv = record[1:]
    assert len(argv) == 7, argv
    assert argv[:6] == list(expected_first_six), (argv[:6], expected_first_six)
    duration = argv[6]
    if duration != "-":
        assert duration.isdigit(), duration
        assert int(duration) >= 0
        assert int(duration) % 1000 == 0, duration


def _now_minus(seconds: int) -> str:
    import time
    return str(int(time.time()) - seconds)


# --- Mode: not-invoked → fallback, gate=fail, reason=marked gate reason -------
def test_mode_fallback_not_invoked(tmp_path):
    records, flag = _run_mode(
        tmp_path, marks={"start_s": _now_minus(2), "reason": "gate-reason-x"}
    )
    emits = [r for r in records if r[0] == "EMIT"]
    assert len(emits) == 1, records
    _assert_emit_argv(
        emits[0],
        ["analyze", "Step-1.5", "REQ-522", "fail", "fallback", "gate-reason-x"],
    )
    # No flag file remains after a normal resolution (AC-3).
    assert not Path(flag).exists(), "flag leaked"
    assert not Path(flag + ".state").exists(), "sidecar leaked"


# --- Mode: invoked but no exit marked → ghost-skip ----------------------------
def test_mode_ghost_skip(tmp_path):
    records, flag = _run_mode(
        tmp_path,
        marks={"start_s": _now_minus(2), "reason": "ok", "invoked": "1"},
    )
    emits = [r for r in records if r[0] == "EMIT"]
    assert len(emits) == 1, records
    _assert_emit_argv(
        emits[0],
        ["analyze", "Step-1.5", "REQ-522", "pass", "ghost-skip",
         "gate-passed-no-call"],
    )
    assert not Path(flag).exists() and not Path(flag + ".state").exists()


# --- Mode: invoked + exit 0 → delegated ---------------------------------------
def test_mode_delegated(tmp_path):
    records, flag = _run_mode(
        tmp_path,
        marks={"start_s": _now_minus(2), "reason": "ok", "invoked": "1",
               "exit": "0"},
    )
    emits = [r for r in records if r[0] == "EMIT"]
    assert len(emits) == 1, records
    _assert_emit_argv(
        emits[0],
        ["analyze", "Step-1.5", "REQ-522", "pass", "delegated", "ok"],
    )
    # The delegated path must compute a real, positive duration (the bug fix).
    assert emits[0][7] != "-" and int(emits[0][7]) >= 1000, emits[0]
    assert not Path(flag).exists() and not Path(flag + ".state").exists()


# --- Mode: invoked + non-zero exit → fallback, api-error ----------------------
def test_mode_api_error(tmp_path):
    records, flag = _run_mode(
        tmp_path,
        marks={"start_s": _now_minus(2), "reason": "ok", "invoked": "1",
               "exit": "7"},
    )
    emits = [r for r in records if r[0] == "EMIT"]
    assert len(emits) == 1, records
    _assert_emit_argv(
        emits[0],
        ["analyze", "Step-1.5", "REQ-522", "pass", "fallback", "api-error"],
    )
    assert not Path(flag).exists() and not Path(flag + ".state").exists()


# --- The step label is passed straight through as the `step` field ------------
@pytest.mark.parametrize("step", ["Step-1.5", "Step-1.6", "Phase-5"])
def test_step_label_passthrough(tmp_path, step):
    delegate, capture = _stage(tmp_path)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    base_env = {"PATH": _BASE_PATH, "HOME": str(fake_home), "CAPTURE": str(capture)}
    sf = str(delegate / "skill-flag.sh")
    flag = subprocess.run(
        ["sh", "-c", f"'{sf}' create"], env=base_env, cwd=str(tmp_path),
        capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(["sh", "-c", f"'{sf}' mark '{flag}' start_s 100"],
                   env=base_env, cwd=str(tmp_path), check=True)
    env = dict(base_env)
    env["flag"] = flag
    env["STEP"] = step
    # Pass the step via env, not f-string, so a metacharacter value cannot inject.
    r = subprocess.run(
        ["sh", "-c", f'. \'{PARTIAL}\'; _adlc_emit_step_telemetry analyze "$STEP"'],
        env=env, cwd=str(tmp_path), capture_output=True, text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    emits = [
        line.split("\t") for line in capture.read_text().splitlines()
        if line.startswith("EMIT")
    ]
    assert len(emits) == 1
    assert emits[0][2] == step, emits[0]


# --- BR-4 / LESSON-008: telemetry never blocks even with tools absent ---------
def test_telemetry_never_blocks_when_tools_absent(tmp_path):
    # Stage the resolver (its `.` target must exist) but NO tools/delegate, so
    # DELEGATE_TOOLS degrades to a non-existent dir and the skill-flag/emit calls
    # fail silently without aborting the shell. Provide a flag whose sidecar does
    # not exist either (lost-path branch).
    adlc_partials = tmp_path / ".adlc" / "partials"
    adlc_partials.mkdir(parents=True)
    (adlc_partials / "delegate-tools-path.sh").write_text(
        TOOLS_PATH_PARTIAL.read_text()
    )
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = {"PATH": _BASE_PATH, "HOME": str(fake_home), "flag": "/nonexistent/flag"}
    r = subprocess.run(
        ["sh", "-c", f". '{PARTIAL}'; _adlc_emit_step_telemetry analyze Step-1.5; echo DONE"],
        env=env, cwd=str(tmp_path), capture_output=True, text=True,
    )
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "DONE" in r.stdout, (r.stdout, r.stderr)
