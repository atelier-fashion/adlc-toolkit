"""Suppression coverage for --no-warn / ADLC_DELEGATE_NO_WARN in adlc-read and
adlc-write (provider-neutral CLIs; REQ-515).

These tests deliberately run with the provider key unset and a real input
file. The notice fires BEFORE ``get_client()``, so we observe whether the
notice appears on stderr before the missing-key SystemExit kills the process.
The suppression states (no flag/env, --no-warn flag, ADLC_DELEGATE_NO_WARN=1)
are exercised without ever touching the live API. The legacy KIMI_NO_WARN env
is no longer honored (REQ-522 ADR-5) — it is only cleared from the test env for
hygiene, never asserted to suppress.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ADLC_READ = os.path.join(TOOLS, "adlc-read")
ADLC_WRITE = os.path.join(TOOLS, "adlc-write")

_NOTICE_SUBSTR = "delegate: sending file contents to the configured endpoint"
_SKIP_SUBSTR = "adlc-read: skipping unreadable path:"
_NO_READABLE_SUBSTR = "no readable files among --paths"


def _env_without_key(home_override=None, **extra):
    """Build an env with MOONSHOT_API_KEY removed.

    Since REQ-422 added an rc-fallback in `_common.get_client()`, removing the
    env var alone is not enough — the fallback will find the key in the real
    user's ~/.zshrc. Pass a `home_override` (tmp path with no rc files
    containing the key) to suppress the fallback as well.
    """
    env = {k: v for k, v in os.environ.items() if k != "MOONSHOT_API_KEY"}
    for v in ("KIMI_NO_WARN", "ADLC_DELEGATE_NO_WARN", "KIMI_API_KEY",
              "ADLC_DELEGATE_API_KEY_ENV", "ADLC_DELEGATE_BASE_URL",
              "ADLC_DELEGATE_MODEL", "ADLC_CONFIG"):
        env.pop(v, None)
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


# --- adlc-read ---

def test_adlc_read_notice_fires_by_default(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("hello\n")
    r = _run([ADLC_READ, "--paths", str(src), "--question", "q"], env=_env_without_key(home_override=tmp_path))
    assert _NOTICE_SUBSTR in r.stderr
    assert r.returncode != 0  # missing key still exits non-zero after the notice


def test_adlc_read_notice_suppressed_by_flag(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("hello\n")
    r = _run([ADLC_READ, "--paths", str(src), "--question", "q", "--no-warn"], env=_env_without_key(home_override=tmp_path))
    assert _NOTICE_SUBSTR not in r.stderr
    assert r.returncode != 0


def test_adlc_read_notice_suppressed_by_env(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("hello\n")
    r = _run([ADLC_READ, "--paths", str(src), "--question", "q"], env=_env_without_key(home_override=tmp_path, ADLC_DELEGATE_NO_WARN="1"))
    assert _NOTICE_SUBSTR not in r.stderr
    assert r.returncode != 0


def test_adlc_read_dry_run_does_not_emit_notice(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("hello\n")
    r = _run([ADLC_READ, "--paths", str(src), "--question", "q", "--dry-run"], env=_env_without_key(home_override=tmp_path))
    assert _NOTICE_SUBSTR not in r.stderr
    assert r.returncode == 0  # dry-run exits cleanly without needing a key


# --- adlc-read: unreadable-path handling (BUG-080) ---

def test_adlc_read_skips_unreadable_path_and_continues(tmp_path):
    """A missing path among readable ones is skipped (warned), not fatal.

    The notice fires AFTER path validation and BEFORE get_client(), so its
    presence proves execution continued past validation with the readable
    remainder rather than aborting on the missing path.
    """
    good = tmp_path / "good.txt"
    good.write_text("hello\n")
    missing = tmp_path / "nope.txt"  # never created
    r = _run(
        [ADLC_READ, "--paths", str(good), str(missing), "--question", "q"],
        env=_env_without_key(home_override=tmp_path),
    )
    assert _SKIP_SUBSTR in r.stderr
    assert str(missing) in r.stderr
    assert _NOTICE_SUBSTR in r.stderr  # reached the notice => did not abort on the bad path
    assert r.returncode != 0  # missing key still exits non-zero, after proceeding


def test_adlc_read_skip_warning_not_suppressed_by_no_warn(tmp_path):
    """--no-warn silences only the exfiltration notice, not the skip diagnostic.

    The skip warning is operational signal (a doc was dropped), not a privacy
    notice — suppressing it would re-hide the very thing BUG-080 surfaces.
    """
    good = tmp_path / "good.txt"
    good.write_text("hello\n")
    missing = tmp_path / "nope.txt"
    r = _run(
        [ADLC_READ, "--paths", str(good), str(missing), "--question", "q", "--no-warn"],
        env=_env_without_key(home_override=tmp_path),
    )
    assert _NOTICE_SUBSTR not in r.stderr  # exfil notice suppressed
    assert _SKIP_SUBSTR in r.stderr        # skip diagnostic still printed


def test_adlc_read_all_unreadable_fails_loud_without_notice(tmp_path):
    """When NO path is readable, exit non-zero before packing/sending anything."""
    miss1 = tmp_path / "a.txt"  # never created
    miss2 = tmp_path / "b.txt"  # never created
    r = _run(
        [ADLC_READ, "--paths", str(miss1), str(miss2), "--question", "q"],
        env=_env_without_key(home_override=tmp_path),
    )
    assert _NO_READABLE_SUBSTR in r.stderr
    assert _NOTICE_SUBSTR not in r.stderr  # aborted before get_client()/notice
    assert r.returncode != 0


# --- adlc-write ---

def test_adlc_write_notice_fires_by_default(tmp_path):
    target = tmp_path / "out.py"
    r = _run([ADLC_WRITE, "--spec", "anything", "--target", str(target)], env=_env_without_key(home_override=tmp_path))
    assert _NOTICE_SUBSTR in r.stderr
    assert r.returncode != 0


def test_adlc_write_notice_suppressed_by_flag(tmp_path):
    target = tmp_path / "out.py"
    r = _run([ADLC_WRITE, "--spec", "anything", "--target", str(target), "--no-warn"], env=_env_without_key(home_override=tmp_path))
    assert _NOTICE_SUBSTR not in r.stderr
    assert r.returncode != 0


def test_adlc_write_notice_suppressed_by_env(tmp_path):
    target = tmp_path / "out.py"
    r = _run([ADLC_WRITE, "--spec", "anything", "--target", str(target)], env=_env_without_key(home_override=tmp_path, ADLC_DELEGATE_NO_WARN="1"))
    assert _NOTICE_SUBSTR not in r.stderr
    assert r.returncode != 0


def test_adlc_write_clobber_guard_fires_before_notice(tmp_path):
    target = tmp_path / "exists.txt"
    target.write_text("already here\n")
    r = _run([ADLC_WRITE, "--spec", "anything", "--target", str(target)], env=_env_without_key(home_override=tmp_path))
    # Clobber guard fires before the notice, so the notice MUST NOT appear.
    assert _NOTICE_SUBSTR not in r.stderr
    assert "target already exists" in r.stderr or "target already exists" in r.stdout
    assert r.returncode != 0
