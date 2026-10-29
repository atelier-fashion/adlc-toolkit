"""The plugin hook scaffolds install.sh's config, byte for byte (REQ-669 ADR-4, BR-6, BR-7).

Two writers create ``~/.claude/adlc/config.yml`` when it is absent: the root
``install.sh`` (``ensure_config``) and the plugin's SessionStart hook
(``scripts/session-start.sh``). Both must write the same delegation-off file, so
installing the plugin never enables delegation and never differs from what a
clone install writes (the BUG-205 class).

Each side's bytes come from RUNNING that side's own text in a sandbox HOME, not
from a copy of the scaffold kept here (LESSON-478: the artifact is the
evidence). ``install.sh`` is evaluated as a slice, as in ``test_install_shim.py``,
because the whole installer ends with an ``adlc doctor`` that pushes to
``origin``. The two mutation tests prove the comparison can fail: a change to
either copy alone breaks parity.

The doctor's `pyyaml` check reads the same bytes off the hook's text, to tell
an unedited scaffold from a config PyYAML must read. The last two tests pin
that reading to the writers, so it cannot become a third copy that drifts.
"""

import os
import shutil
import subprocess

TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__)))))
INSTALL_SH = os.path.join(TOOLKIT, "install.sh")
HOOK_SH = os.path.join(TOOLKIT, "scripts", "session-start.sh")
PLUGIN_JSON = os.path.join(TOOLKIT, ".claude-plugin", "plugin.json")

# install.sh's helpers, atomic_write and every mutator up to the main body.
_SLICE_START = "note()"
_SLICE_END = "# --- run ---"
# A phrase in the scaffold text both copies carry exactly once.
_PHRASE = "(scaffolded by install.sh, REQ-519)"
_CONFIG = os.path.join(".claude", "adlc", "config.yml")


def _sandbox_env(home, **extra):
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    env.update(extra)
    return env


def _install_sh_scaffold(install_sh, tmp_path):
    """The bytes install.sh's own ``ensure_config`` writes into an empty HOME."""
    with open(install_sh, encoding="utf-8") as fh:
        text = fh.read()
    assert "\nensure_config\n" in text, \
        "install.sh no longer calls ensure_config — this test drives a dead function"
    assert text.count(_SLICE_START) == 1 and text.count(_SLICE_END) == 1, \
        "install.sh restructured: the slice anchors moved"
    block = text[text.index(_SLICE_START):text.index(_SLICE_END)]
    for needed in ("atomic_write() {", "ensure_config() {"):
        assert needed in block, f"install.sh restructured: '{needed}' left the slice"
    home = tmp_path / "install-home"
    home.mkdir(parents=True)
    # The globals the slice reads, as install.sh sets them above it.
    script = ("set -euo pipefail\nDRY=0\nACTIONS=0\nCLAUDE_DIR=\"$HOME/.claude\"\n"
              # REQ-654: the config is machine state, under ADLC_HOME_DIR, which
              # install.sh resolves to $HOME/.claude when ADLC_HOME is unset.
              "ADLC_HOME_DIR=\"$HOME/.claude\"\n"
              + block + "\nensure_config\n")
    proc = subprocess.run(["bash", "-c", script], env=_sandbox_env(home),
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"ensure_config failed: {proc.stderr}"
    with open(home / _CONFIG, "rb") as fh:
        return fh.read()


def _hook_scaffold(hook_sh, tmp_path):
    """The bytes the hook writes into an empty HOME, run as hooks.json runs it."""
    root = tmp_path / "plugin-root"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / "partials").mkdir()
    (root / "scripts").mkdir()
    shutil.copy2(PLUGIN_JSON, root / ".claude-plugin" / "plugin.json")
    shutil.copy2(hook_sh, root / "scripts" / "session-start.sh")
    home = tmp_path / "hook-home"
    home.mkdir(parents=True)
    proc = subprocess.run(
        ["sh", str(root / "scripts" / "session-start.sh")],
        env=_sandbox_env(home, CLAUDE_PLUGIN_ROOT=str(root)),
        stdin=subprocess.DEVNULL, capture_output=True,
    )
    assert proc.returncode == 0
    assert proc.stdout == b"" and proc.stderr == b"", \
        f"the hook reported a problem: {proc.stderr!r}"
    with open(home / _CONFIG, "rb") as fh:
        return fh.read()


def _mutated_copy(src, dest):
    """A copy of <src> with the scaffold phrase changed, asserted to have applied."""
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert text.count(_PHRASE) == 1, f"{os.path.basename(src)} no longer carries '{_PHRASE}' once"
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text.replace(_PHRASE, "(scaffolded by a drifted copy)"))
    return dest


def test_scaffold_bytes_match_install_sh(tmp_path):
    ours = _hook_scaffold(HOOK_SH, tmp_path / "hook")
    theirs = _install_sh_scaffold(INSTALL_SH, tmp_path / "install")
    assert ours == theirs
    # And the shared bytes are the delegation-off scaffold, newline-terminated.
    assert b"\ndelegate:\n  enabled: false\n" in ours
    assert ours.endswith(b"\n") and not ours.endswith(b"\n\n")


def test_parity_fails_when_the_hook_copy_changes_alone(tmp_path):
    drifted = _mutated_copy(HOOK_SH, str(tmp_path / "session-start.sh"))
    ours = _hook_scaffold(drifted, tmp_path / "hook")
    theirs = _install_sh_scaffold(INSTALL_SH, tmp_path / "install")
    assert ours != theirs


def test_parity_fails_when_install_sh_changes_alone(tmp_path):
    drifted = _mutated_copy(INSTALL_SH, str(tmp_path / "install.sh"))
    ours = _hook_scaffold(HOOK_SH, tmp_path / "hook")
    theirs = _install_sh_scaffold(drifted, tmp_path / "install")
    assert ours != theirs


# --- the doctor's reading is the same source (REQ-669 AC-1) -------------------

def _doctor_scaffold(root):
    """What the `pyyaml` check compares a machine config against, for ``root``."""
    import checks   # tools/adlc on sys.path via conftest
    return checks._config_scaffold(str(root))


def test_doctor_reads_the_bytes_both_writers_write(tmp_path):
    """The doctor's scaffold is not a third copy: it is read off the hook's text.

    So the three agree byte for byte, and the `pyyaml` check's SKIP on an
    unedited scaffold matches exactly the file a fresh plugin machine has.
    """
    ours = _doctor_scaffold(TOOLKIT)
    assert ours is not None
    assert ours == _hook_scaffold(HOOK_SH, tmp_path / "hook")
    assert ours == _install_sh_scaffold(INSTALL_SH, tmp_path / "install")


def test_doctor_follows_the_hook_text_when_it_changes(tmp_path):
    """A changed hook copy changes what the doctor reads, in step with what it writes."""
    root = tmp_path / "drifted-root"
    (root / "scripts").mkdir(parents=True)
    drifted = _mutated_copy(HOOK_SH, str(root / "scripts" / "session-start.sh"))
    ours = _doctor_scaffold(root)
    assert ours == _hook_scaffold(drifted, tmp_path / "hook")
    assert ours != _doctor_scaffold(TOOLKIT)
