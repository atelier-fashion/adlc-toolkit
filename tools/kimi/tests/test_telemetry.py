"""Tests for the POSIX shell telemetry helpers under tools/kimi/.

All tests redirect $ADLC_TELEMETRY_LOG into tmp_path so they never touch the
real on-disk log under ~/Library/Logs/.
"""

import json
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
KIMI_DIR = REPO_ROOT / "tools" / "kimi"
EMIT = str(KIMI_DIR / "emit-telemetry.sh")
FLAG = str(KIMI_DIR / "skill-flag.sh")
CHECK = str(KIMI_DIR / "check-delegation.sh")


def _run(cmd, env=None, check=True):
    result = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed (exit {result.returncode}): {cmd}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def _env_with_log(tmp_path):
    env = os.environ.copy()
    env["ADLC_TELEMETRY_LOG"] = str(tmp_path / "telemetry.log")
    return env


def test_emit_produces_valid_json_line_with_9_keys_and_mode_600(tmp_path):
    env = _env_with_log(tmp_path)
    log_path = Path(env["ADLC_TELEMETRY_LOG"])
    _run(
        [EMIT, "wrapup", "draft-lesson", "REQ-424", "pass", "delegated", "ok reason", "1234"],
        env=env,
    )
    assert log_path.exists()
    # File mode is 0600
    mode = stat.S_IMODE(log_path.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"
    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    expected = {"timestamp", "skill", "step", "req", "gate", "mode", "reason", "duration_ms", "repo"}
    assert set(obj.keys()) == expected
    assert obj["skill"] == "wrapup"
    assert obj["mode"] == "delegated"


def test_skill_flag_create_check_clear_lifecycle(tmp_path):
    # create
    r = _run([FLAG, "create"])
    path = r.stdout.strip()
    assert path and Path(path).exists()
    try:
        # check exits 0 while present
        r = _run([FLAG, "check", path], check=False)
        assert r.returncode == 0
        # clear removes it
        _run([FLAG, "clear", path])
        assert not Path(path).exists()
        # check exits 1 after
        r = _run([FLAG, "check", path], check=False)
        assert r.returncode == 1
    finally:
        if Path(path).exists():
            Path(path).unlink()


def test_check_delegation_three_event_fixture(tmp_path):
    env = _env_with_log(tmp_path)
    _run([EMIT, "test-skill", "s1", "REQ-1", "pass", "delegated", "ok", "100"], env=env)
    _run([EMIT, "test-skill", "s2", "REQ-1", "fail", "fallback", "fb", "200"], env=env)
    _run([EMIT, "test-skill", "s3", "REQ-1", "n/a", "ghost-skip", "gs", "-"], env=env)
    r = _run([CHECK], env=env)
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "skill\tdelegated\tfallback\tghost_skip\ttotal"
    assert lines[1] == "test-skill\t1\t1\t1\t3"
    assert lines[-1] == "TOTAL\t1\t1\t1\t3"


def test_check_delegation_empty_log_emits_zero_total(tmp_path):
    env = _env_with_log(tmp_path)
    # No log file yet
    r = _run([CHECK], env=env)
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "skill\tdelegated\tfallback\tghost_skip\ttotal"
    assert lines[-1] == "TOTAL\t0\t0\t0\t0"


def test_check_delegation_window_excludes_old_events(tmp_path):
    log_path = tmp_path / "telemetry.log"
    env = _env_with_log(tmp_path)
    # Synthesize one old event (10 days ago) and one fresh event manually.
    old_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 10 * 86400))
    new_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    old_line = (
        f'{{"timestamp":"{old_ts}","skill":"old-skill","step":"s","req":"-",'
        f'"gate":"pass","mode":"delegated","reason":"old","duration_ms":"-","repo":"r"}}'
    )
    new_line = (
        f'{{"timestamp":"{new_ts}","skill":"new-skill","step":"s","req":"-",'
        f'"gate":"pass","mode":"delegated","reason":"new","duration_ms":"-","repo":"r"}}'
    )
    log_path.write_text(old_line + "\n" + new_line + "\n")
    os.chmod(log_path, 0o600)
    r = _run([CHECK, "--window", "1d"], env=env)
    out = r.stdout
    assert "old-skill" not in out
    assert "new-skill" in out
    assert "TOTAL\t1\t0\t0\t1" in out


def test_emit_redacts_sk_secret_in_reason(tmp_path):
    env = _env_with_log(tmp_path)
    log_path = Path(env["ADLC_TELEMETRY_LOG"])
    secret = "sk-AbCdEf1234567890123456"
    _run(
        [EMIT, "wrapup", "s", "-", "pass", "delegated", f"leaked {secret} here", "-"],
        env=env,
    )
    content = log_path.read_text()
    assert secret not in content
    assert "[REDACTED]" in content


# --- REQ-424 verify-pass additions: all-one-mode + two-skill coverage ---

def test_check_delegation_all_delegated(tmp_path):
    env = _env_with_log(tmp_path)
    for i in range(3):
        _run([EMIT, "one-skill", f"s{i}", "REQ-9", "pass", "delegated", "ok", "10"], env=env)
    r = _run([CHECK], env=env)
    lines = r.stdout.strip().splitlines()
    assert lines[1] == "one-skill\t3\t0\t0\t3"
    assert lines[-1] == "TOTAL\t3\t0\t0\t3"


def test_check_delegation_all_fallback(tmp_path):
    env = _env_with_log(tmp_path)
    for i in range(2):
        _run([EMIT, "one-skill", f"s{i}", "REQ-9", "fail", "fallback", "no-binary", "0"], env=env)
    r = _run([CHECK], env=env)
    lines = r.stdout.strip().splitlines()
    assert lines[1] == "one-skill\t0\t2\t0\t2"
    assert lines[-1] == "TOTAL\t0\t2\t0\t2"


def test_check_delegation_all_ghost_skip(tmp_path):
    env = _env_with_log(tmp_path)
    for i in range(4):
        _run([EMIT, "one-skill", f"s{i}", "REQ-9", "pass", "ghost-skip", "gate-passed-no-call", "0"], env=env)
    r = _run([CHECK], env=env)
    lines = r.stdout.strip().splitlines()
    assert lines[1] == "one-skill\t0\t0\t4\t4"
    assert lines[-1] == "TOTAL\t0\t0\t4\t4"


def test_check_delegation_two_skills_separate_rows(tmp_path):
    env = _env_with_log(tmp_path)
    _run([EMIT, "alpha", "s1", "REQ-1", "pass", "delegated", "ok", "10"], env=env)
    _run([EMIT, "alpha", "s2", "REQ-1", "pass", "ghost-skip", "gs", "0"], env=env)
    _run([EMIT, "beta", "s1", "REQ-2", "fail", "fallback", "no-binary", "0"], env=env)
    r = _run([CHECK], env=env)
    lines = r.stdout.strip().splitlines()
    # Header, two skill rows (any order), TOTAL footer = 4 lines minimum
    assert lines[0] == "skill\tdelegated\tfallback\tghost_skip\ttotal"
    skill_rows = [l for l in lines[1:-1]]
    assert len(skill_rows) == 2
    assert any(l == "alpha\t1\t0\t1\t2" for l in skill_rows), f"alpha row missing in: {skill_rows}"
    assert any(l == "beta\t0\t1\t0\t1" for l in skill_rows), f"beta row missing in: {skill_rows}"
    assert lines[-1] == "TOTAL\t1\t1\t1\t3"
