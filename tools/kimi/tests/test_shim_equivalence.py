"""REQ-515 BR-1: the legacy ask-kimi / kimi-write names are exec-shims for
adlc-read / adlc-write and must behave identically.

We compare --help and --dry-run / usage-error output. The shims are POSIX
/bin/sh scripts (`exec "$(dirname "$0")/adlc-read" "$@"`), so they are invoked
directly (kernel honors the shebang), while the new commands are python.
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)

ADLC_READ = os.path.join(TOOLS, "adlc-read")
ADLC_WRITE = os.path.join(TOOLS, "adlc-write")
ASK_KIMI = os.path.join(TOOLS, "ask-kimi")
KIMI_WRITE = os.path.join(TOOLS, "kimi-write")


def _run(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def test_read_dry_run_identical(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("hello world\n")
    base = ["--paths", str(f), "--question", "summarize", "--dry-run"]
    a = _run([ADLC_READ, *base])
    b = _run([ASK_KIMI, *base])
    assert a.returncode == 0 and b.returncode == 0, (a.stderr, b.stderr)
    assert a.stdout == b.stdout


def test_read_help_routes_to_new_command():
    """The shim execs adlc-read, so its --help shows the adlc-read prog name."""
    a = _run([ADLC_READ, "--help"])
    b = _run([ASK_KIMI, "--help"])
    assert a.returncode == 0 and b.returncode == 0
    assert "adlc-read" in a.stdout
    assert "adlc-read" in b.stdout  # shim forwarded to the new command


def test_write_usage_error_identical():
    """Missing required args → argparse exit 2; shim and new command agree."""
    a = _run([ADLC_WRITE])
    b = _run([KIMI_WRITE])
    assert a.returncode == 2 and b.returncode == 2
    assert a.stderr == b.stderr


def test_write_help_routes_to_new_command():
    a = _run([ADLC_WRITE, "--help"])
    b = _run([KIMI_WRITE, "--help"])
    assert a.returncode == 0 and b.returncode == 0
    assert "adlc-write" in a.stdout
    assert "adlc-write" in b.stdout
