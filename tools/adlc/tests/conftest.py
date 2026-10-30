"""Test fixtures for tools/adlc — mirrors tools/delegate/tests/conftest.py.

Inserts the parent dir (tools/adlc) onto sys.path so `import adlc`,
`import doctor`, `import checks` resolve regardless of cwd.
"""
import os
import shutil
import site
import subprocess
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: The runner's user site, resolved before any test moves ``HOME``.
_USER_BASE = site.getuserbase()


@pytest.fixture(autouse=True)
def _sandbox_home(monkeypatch, tmp_path_factory):
    """Point ``HOME`` at a throwaway directory for every test (BUG-256).

    Code under test reaches machine state through ``~`` in-process and through
    the shell partials it runs, so a test that forgets its own sandbox writes to
    the real home: ``test_reserve_new_id_won_pushes_ref`` appended to the real
    ``.adlc-own-reservations`` on every run (LESSON-758). A test that needs a
    particular home sets ``HOME`` itself, and that wins.

    Moving ``HOME`` also moves the user site a child ``python3`` searches, which
    hides a PyYAML installed there, so the child keeps the runner's: read only.
    """
    monkeypatch.setenv("PYTHONUSERBASE", _USER_BASE)
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("sandbox-home")))


@pytest.fixture(autouse=True)
def _no_inherited_toolkit_env(monkeypatch):
    """Keep the runner's own install out of every test.

    The doctor reads plugins from ``$CLAUDE_CONFIG_DIR`` when it is set, the
    config readers take a loader from ``$ADLC_TOOLKIT_ROOT``, and machine state
    resolves through ``$ADLC_HOME`` (REQ-654). Either one,
    inherited from the shell running pytest, would point a sandboxed case at the
    real machine. A test that needs one sets it itself.
    """
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("ADLC_TOOLKIT_ROOT", raising=False)
    # REQ-654: the machine-state home, the config override and the repos root
    # each redirect what a sandboxed case reads; none may come from the runner.
    monkeypatch.delenv("ADLC_HOME", raising=False)
    monkeypatch.delenv("ADLC_CONFIG", raising=False)
    monkeypatch.delenv("ADLC_REPOS_ROOT", raising=False)


@pytest.fixture(scope="session")
def repo_root():
    """Absolute path to the toolkit checkout root via git, SKIP if unavailable."""
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.skip(f"git rev-parse failed — adlc tests need a git repo: {e}")
    return root


#: The toolkit tree these tests belong to, from this file's real location.
TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__)))))


def _copy_file(rel, dest_root):
    src = os.path.join(TOOLKIT, *rel.split("/"))
    dest = os.path.join(dest_root, *rel.split("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)


@pytest.fixture
def cache_shaped_tree(tmp_path):
    """A plugin-cache-shaped copy of the Python tools, under a sandbox HOME.

    Shaped like REQ-669's verified install: ``~/.claude/plugins/cache/
    <marketplace>/<plugin>/<version>/``, with no ``.git`` in the copy
    (verification.md row 11) and no ``~/.claude/skills`` anywhere. The sandbox
    HOME is itself a git repo, standing in for a dotfiles repo that encloses
    ``~/.claude``: ``git rev-parse --show-toplevel`` from inside the copy names
    HOME, so anything that trusts git for the toolkit root gets it wrong here.
    """
    home = tmp_path / "home"
    root = home / ".claude" / "plugins" / "cache" / "adlc-toolkit" / "adlc" / "0.0.0-test"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(home)], check=True)
    for name in os.listdir(os.path.join(TOOLKIT, "tools", "adlc")):
        if name.endswith(".py"):
            _copy_file("tools/adlc/" + name, str(root))
    for rel in ("tools/delegate/_machine_config.py", "partials/id-recheck.sh",
                "VERSION"):
        _copy_file(rel, str(root))
    assert not (root / ".git").exists()
    assert not (home / ".claude" / "skills").exists()
    # A scrubbed child environment: HOME is the sandbox, nothing else leaks in.
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    for key in ("LANG", "LC_ALL", "TMPDIR"):
        if key in os.environ:
            env[key] = os.environ[key]
    return types.SimpleNamespace(home=str(home), root=str(root), env=env)
