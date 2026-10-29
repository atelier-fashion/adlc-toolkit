"""REQ-664 BR-14 / AC-12: the fake harness and every shell the probe writes into a
throwaway repository parse and run under /bin/bash (3.2 on macOS), zsh and
/bin/sh. Nothing in partials/ changes, so partials/tests/run.sh is untouched; this
is where those scripts meet the shell matrix (LESSON-582)."""

import glob
import os
import re
import shutil
import subprocess
import sys

import pytest

import harness_probe as hp
from probe_helpers import IMPL, WRAPPER, Sandbox

SHELLS = [s for s in ("/bin/bash", shutil.which("zsh"), "/bin/sh") if s and os.path.exists(s)]


@pytest.fixture(scope="module")
def kept_run(tmp_path_factory):
    """One kept claude run: its hooks dir holds every hook script it wrote."""
    root = tmp_path_factory.mktemp("kept")
    sb = Sandbox(root)
    out = sb.run("claude", "--keep")
    assert out.returncode == 0, out.stderr[-2000:]
    run_dir = re.search(r"kept the run directory: (\S+)", out.stdout).group(1)
    yield sb, run_dir
    shutil.rmtree(run_dir, ignore_errors=True)


@pytest.mark.parametrize("shell", SHELLS)
def test_fake_and_fixtures_under_each_shell(shell, kept_run, tmp_path):
    sb, run_dir = kept_run
    # The fake wrapper: parses, and runs as `claude --version`.
    assert subprocess.run([shell, "-n", WRAPPER]).returncode == 0
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy2(WRAPPER, str(bindir / "claude"))
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "FAKE_HARNESS_IMPL": IMPL,
           "FAKE_HARNESS_PYTHON": sys.executable, "FAKE_HARNESS_VERSION": "9.9 (fake)"}
    out = subprocess.run([shell, str(bindir / "claude"), "--version"], env=env,
                         capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip() == "9.9 (fake)", out.stderr
    # Every hook script and the transcript recorder: parse, then run.
    scripts = sorted(glob.glob(os.path.join(run_dir, "hooks", "**", "*.sh"), recursive=True))
    assert len(scripts) >= 3
    for script in scripts:
        assert subprocess.run([shell, "-n", script]).returncode == 0, script
        text = open(script).read()
        assert "local " not in text and "[[" not in text
        run = subprocess.run([shell, script], input="{}", capture_output=True, text=True,
                             cwd=str(tmp_path))
        assert run.returncode == 0, (script, run.stderr)
    # The partial the fence sources, and the fence itself, executed.
    work = tmp_path / "work"
    (work / ".adlc" / "partials").mkdir(parents=True)
    sentinel = tmp_path / "fence-sentinel"
    (work / ".adlc" / "partials" / "probe.sh").write_text(
        "adlc_probe_function() {\n    touch %s\n}\n" % sentinel)
    assert subprocess.run([shell, "-n", str(work / ".adlc" / "partials" / "probe.sh")]
                          ).returncode == 0
    run = subprocess.run([shell, "-c", hp.FENCE], cwd=str(work), capture_output=True,
                         text=True, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert run.returncode == 0, run.stderr
    assert sentinel.exists()
