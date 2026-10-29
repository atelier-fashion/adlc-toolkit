"""REQ-654 BR-7 / AC-6: `adlc harness detect`.

Every case runs the real CLI with a sandbox PATH and HOME, so which harnesses
"exist" is decided by the fake binaries each case plants, never by the machine
running the suite.
"""

import json
import os
import subprocess
import sys
import time

import pytest

ADLC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adlc.py")
TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__)))))
#: Directories a fake binary may need (`/bin/sh`, `sleep`, `echo`).
SYSTEM_PATH = "/usr/bin:/bin"


def _fake(bindir, name, body):
    os.makedirs(bindir, exist_ok=True)
    path = os.path.join(bindir, name)
    with open(path, "w") as fh:
        fh.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, 0o755)
    return path


def _run(tmp_path, bindir, *args, home=None):
    home = home or str(tmp_path / "home")
    os.makedirs(home, exist_ok=True)
    env = {"HOME": home, "PATH": bindir + ":" + SYSTEM_PATH}
    # cwd outside any repository: the last_probe column (REQ-664) reads the
    # caller's repo, and this checkout carries committed probe results.
    return subprocess.run([sys.executable, ADLC, "harness"] + list(args),
                          env=env, capture_output=True, text=True, timeout=60,
                          cwd=str(tmp_path))


def _mounted_home(tmp_path):
    """A HOME whose ~/.claude/skills is this toolkit, as install.sh leaves it."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    os.symlink(TOOLKIT, str(home / ".claude" / "skills"))
    return str(home)


def test_only_claude_on_path(tmp_path):
    """Five rows; claude present with its version and mounted; the other four
    absent with mount n/a; exit 0."""
    bindir = str(tmp_path / "bin")
    _fake(bindir, "claude", "echo '2.1.258 (Claude Code)'")
    out = _run(tmp_path, bindir, "detect", home=_mounted_home(tmp_path))
    assert out.returncode == 0, out.stderr
    rows = [line.split() for line in out.stdout.splitlines()[1:]]
    assert [r[0] for r in rows] == ["claude", "copilot", "codex", "gemini", "cursor"]
    assert rows[0][2] == "present" and "2.1.258" in out.stdout.splitlines()[1]
    assert rows[0][-2] == "mounted"
    for row in rows[1:]:
        assert row[2] == "absent" and row[-2] == "n/a", row
    assert all(row[-1] == "never" for row in rows)        # REQ-664: no probe results


def test_json_round_trips(tmp_path):
    bindir = str(tmp_path / "bin")
    _fake(bindir, "claude", "echo '2.1.258 (Claude Code)'")
    out = _run(tmp_path, bindir, "detect", "--json", home=_mounted_home(tmp_path))
    assert out.returncode == 0, out.stderr
    tool = subprocess.run([sys.executable, "-m", "json.tool"], input=out.stdout,
                          capture_output=True, text=True)
    assert tool.returncode == 0, tool.stderr
    data = json.loads(out.stdout)
    assert [d["name"] for d in data] == ["claude", "copilot", "codex", "gemini", "cursor"]
    for d in data:
        assert set(d) == {"name", "binary", "state", "path", "version", "mount",
                          "last_probe", "probe_file"}
    assert data[0]["state"] == "present" and data[0]["mount"] == "mounted"
    assert data[4]["binary"] == "agent" and data[4]["state"] == "absent"


def test_hanging_version_is_unknown(tmp_path):
    """A codex that hangs on --version (and leaves a child behind) is reported
    present / unknown within the timeout, and the command still exits 0."""
    bindir = str(tmp_path / "bin")
    _fake(bindir, "codex", "sleep 60 &\nsleep 60")
    start = time.monotonic()
    out = _run(tmp_path, bindir, "detect", "--json")
    elapsed = time.monotonic() - start
    assert out.returncode == 0, out.stderr
    codex = next(d for d in json.loads(out.stdout) if d["name"] == "codex")
    assert codex["state"] == "present" and codex["version"] == "unknown"
    assert elapsed < 30, elapsed


def test_failing_version_and_cursor_alias(tmp_path):
    """A non-zero --version is unknown, never an error; Cursor's `cursor-agent`
    alias counts when `agent` is absent; a harness with a binary but no mount is
    not-mounted."""
    bindir = str(tmp_path / "bin")
    _fake(bindir, "gemini", "echo boom >&2; exit 3")
    _fake(bindir, "cursor-agent", "echo '2026.10.01'")
    out = _run(tmp_path, bindir, "detect", "--json")
    assert out.returncode == 0, out.stderr
    data = {d["name"]: d for d in json.loads(out.stdout)}
    assert data["gemini"]["version"] == "unknown"
    assert data["cursor"]["binary"] == "cursor-agent"
    assert data["cursor"]["version"] == "2026.10.01"
    assert data["cursor"]["mount"] == "not-mounted"


def test_agents_mount_is_read_through_the_view(tmp_path):
    """A non-Claude harness is mounted when ~/.agents/skills reaches this toolkit."""
    home = tmp_path / "home"
    view = home / ".claude" / "adlc" / "skills-view"
    view.mkdir(parents=True)
    os.symlink(os.path.join(TOOLKIT, "spec"), str(view / "spec"))
    (home / ".agents").mkdir()
    os.symlink(str(view), str(home / ".agents" / "skills"))
    bindir = str(tmp_path / "bin")
    _fake(bindir, "copilot", "echo 1.0")
    out = _run(tmp_path, bindir, "detect", "--json", home=str(home))
    data = {d["name"]: d for d in json.loads(out.stdout)}
    assert data["copilot"]["mount"] == "mounted"


@pytest.mark.parametrize("args", [[], ["probe"]])
def test_no_or_unknown_verb_is_usage(tmp_path, args):
    out = _run(tmp_path, str(tmp_path / "bin"), *args)
    assert out.returncode == 2
    assert "usage" in out.stderr.lower()


def test_agents_mount_counts_the_clone_claude_code_mounts(tmp_path):
    """Run from a worktree, the view still reaches the toolkit when it links into
    the clone ~/.claude/skills points at (install.sh builds it from that clone)."""
    clone = tmp_path / "clone"
    (clone / "partials").mkdir(parents=True)
    (clone / "spec").mkdir()
    (clone / "spec" / "SKILL.md").write_text("x\n")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    os.symlink(str(clone), str(home / ".claude" / "skills"))
    (home / ".agents").mkdir()
    view = home / "view"
    view.mkdir()
    os.symlink(str(clone / "spec"), str(view / "spec"))
    os.symlink(str(view), str(home / ".agents" / "skills"))
    bindir = str(tmp_path / "bin")
    _fake(bindir, "codex", "echo 1.0")
    out = _run(tmp_path, bindir, "detect", "--json", home=str(home))
    data = {d["name"]: d for d in json.loads(out.stdout)}
    assert data["codex"]["mount"] == "mounted"


# --- REQ-664 BR-13 / AC-11: the last_probe column ------------------------------

def _probe_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".adlc" / "research" / "harness-probes").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _run_in(cwd, tmp_path, *args):
    home = str(tmp_path / "home")
    os.makedirs(home, exist_ok=True)
    env = {"HOME": home, "PATH": str(tmp_path / "bin") + ":" + SYSTEM_PATH}
    return subprocess.run([sys.executable, ADLC, "harness"] + list(args), env=env,
                          cwd=str(cwd), capture_output=True, text=True, timeout=60)


def test_last_probe_column(tmp_path):
    """A codex.json dated 2026-10-27 shows on the codex row and `never` elsewhere;
    `{` shows `unreadable`; --json carries last_probe and probe_file; exit 0 in
    every case, and outside a repository every row is `never`."""
    repo = _probe_repo(tmp_path)
    result = repo / ".adlc" / "research" / "harness-probes" / "codex.json"
    result.write_text(json.dumps({"schema": 1, "harness": "codex", "date": "2026-10-27"}))
    out = _run_in(repo, tmp_path, "detect")
    assert out.returncode == 0, out.stderr
    rows = {line.split()[0]: line.split() for line in out.stdout.splitlines()[1:]}
    assert out.stdout.splitlines()[0].split()[-1] == "last_probe"
    assert rows["codex"][-1] == "2026-10-27"
    assert all(rows[h][-1] == "never" for h in ("claude", "copilot", "gemini", "cursor"))
    out = _run_in(repo, tmp_path, "detect", "--json")
    assert out.returncode == 0, out.stderr
    data = {d["name"]: d for d in json.loads(out.stdout)}
    assert data["codex"]["last_probe"] == "2026-10-27"
    assert os.path.realpath(data["codex"]["probe_file"]) == os.path.realpath(str(result))
    assert data["claude"]["last_probe"] == "never" and data["claude"]["probe_file"] is None
    result.write_text("{")
    out = _run_in(repo, tmp_path, "detect")
    assert out.returncode == 0, out.stderr
    rows = {line.split()[0]: line.split() for line in out.stdout.splitlines()[1:]}
    assert rows["codex"][-1] == "unreadable"
    out = _run_in(repo, tmp_path, "detect", "--json")
    assert json.loads(out.stdout)[2]["last_probe"] == "unreadable"
    # Benign path: outside any repository nothing is read and nothing fails.
    outside = tmp_path / "outside"
    outside.mkdir()
    out = _run_in(outside, tmp_path, "detect", "--json")
    assert out.returncode == 0, out.stderr
    assert {d["last_probe"] for d in json.loads(out.stdout)} == {"never"}
