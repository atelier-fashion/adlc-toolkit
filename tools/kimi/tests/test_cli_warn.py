"""Suppression coverage for --no-warn / KIMI_NO_WARN in ask-kimi and kimi-write.

These tests deliberately run with ``MOONSHOT_API_KEY`` unset and a real input
file. The notice fires BEFORE ``get_client()``, so we observe whether the
notice appears on stderr before the missing-key SystemExit kills the process.
All three suppression states (no flag/env, --no-warn flag, KIMI_NO_WARN=1) are
exercised without ever touching the live API.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ASK_KIMI = os.path.join(TOOLS, "ask-kimi")
KIMI_WRITE = os.path.join(TOOLS, "kimi-write")

_NOTICE_SUBSTR = "kimi: sending file contents to Moonshot"


def _env_without_key(home_override=None, **extra):
    """Build an env with MOONSHOT_API_KEY removed.

    Since REQ-422 added an rc-fallback in `_common.get_client()`, removing the
    env var alone is not enough — the fallback will find the key in the real
    user's ~/.zshrc. Pass a `home_override` (tmp path with no rc files
    containing the key) to suppress the fallback as well.
    """
    env = {k: v for k, v in os.environ.items() if k != "MOONSHOT_API_KEY"}
    env.pop("KIMI_NO_WARN", None)
    if home_override is not None:
        env["HOME"] = str(home_override)
    env.update(extra)
    return env


def _run(argv, env):
    return subprocess.run(
        [sys.executable, *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


# --- ask-kimi ---

def test_ask_kimi_notice_fires_by_default(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("hello\n")
    r = _run([ASK_KIMI, "--paths", str(src), "--question", "q"], env=_env_without_key(home_override=tmp_path))
    assert _NOTICE_SUBSTR in r.stderr
    assert r.returncode != 0  # missing key still exits non-zero after the notice


def test_ask_kimi_notice_suppressed_by_flag(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("hello\n")
    r = _run([ASK_KIMI, "--paths", str(src), "--question", "q", "--no-warn"], env=_env_without_key(home_override=tmp_path))
    assert _NOTICE_SUBSTR not in r.stderr
    assert r.returncode != 0


def test_ask_kimi_notice_suppressed_by_env(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("hello\n")
    r = _run([ASK_KIMI, "--paths", str(src), "--question", "q"], env=_env_without_key(home_override=tmp_path, KIMI_NO_WARN="1"))
    assert _NOTICE_SUBSTR not in r.stderr
    assert r.returncode != 0


def test_ask_kimi_dry_run_does_not_emit_notice(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("hello\n")
    r = _run([ASK_KIMI, "--paths", str(src), "--question", "q", "--dry-run"], env=_env_without_key(home_override=tmp_path))
    assert _NOTICE_SUBSTR not in r.stderr
    assert r.returncode == 0  # dry-run exits cleanly without needing a key


# --- kimi-write ---

def test_kimi_write_notice_fires_by_default(tmp_path):
    target = tmp_path / "out.py"
    r = _run([KIMI_WRITE, "--spec", "anything", "--target", str(target)], env=_env_without_key(home_override=tmp_path))
    assert _NOTICE_SUBSTR in r.stderr
    assert r.returncode != 0


def test_kimi_write_notice_suppressed_by_flag(tmp_path):
    target = tmp_path / "out.py"
    r = _run([KIMI_WRITE, "--spec", "anything", "--target", str(target), "--no-warn"], env=_env_without_key(home_override=tmp_path))
    assert _NOTICE_SUBSTR not in r.stderr
    assert r.returncode != 0


def test_kimi_write_notice_suppressed_by_env(tmp_path):
    target = tmp_path / "out.py"
    r = _run([KIMI_WRITE, "--spec", "anything", "--target", str(target)], env=_env_without_key(home_override=tmp_path, KIMI_NO_WARN="1"))
    assert _NOTICE_SUBSTR not in r.stderr
    assert r.returncode != 0


def test_kimi_write_clobber_guard_fires_before_notice(tmp_path):
    target = tmp_path / "exists.txt"
    target.write_text("already here\n")
    r = _run([KIMI_WRITE, "--spec", "anything", "--target", str(target)], env=_env_without_key(home_override=tmp_path))
    # Clobber guard fires before the notice, so the notice MUST NOT appear.
    assert _NOTICE_SUBSTR not in r.stderr
    assert "target already exists" in r.stderr or "target already exists" in r.stdout
    assert r.returncode != 0
