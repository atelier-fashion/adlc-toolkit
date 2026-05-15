"""Subprocess-based regression tests for `partials/*.sh`.

Replaces the one-shot manual checks from REQ-416 verification with a
reproducible harness (REQ-426 BR-4..BR-6, ADR-4).
"""

import os
import shutil
import subprocess

import pytest


def _run(script, env, cwd):
    return subprocess.run(
        ["sh", "-c", script],
        env=env, cwd=str(cwd),
        capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# ethos-include.sh
# ---------------------------------------------------------------------------

def test_ethos_consumer_precedence(tmp_path, partials_dir):
    """A non-empty consumer `.adlc/ETHOS.md` wins over the toolkit copy."""
    adlc = tmp_path / ".adlc"
    adlc.mkdir()
    (adlc / "ETHOS.md").write_text("LOCAL ETHOS\n")

    fake_home = tmp_path / "home"
    (fake_home / ".claude" / "skills").mkdir(parents=True)
    (fake_home / ".claude" / "skills" / "ETHOS.md").write_text("TOOLKIT ETHOS\n")

    env = {"HOME": str(fake_home), "PATH": "/usr/bin:/bin"}
    r = _run(f". {partials_dir}/ethos-include.sh", env, tmp_path)
    assert r.returncode == 0
    assert "LOCAL ETHOS" in r.stdout
    assert "TOOLKIT ETHOS" not in r.stdout


def test_ethos_toolkit_fallback(tmp_path, partials_dir):
    """With no consumer copy, the toolkit copy under $HOME is emitted."""
    fake_home = tmp_path / "home"
    (fake_home / ".claude" / "skills").mkdir(parents=True)
    (fake_home / ".claude" / "skills" / "ETHOS.md").write_text("TOOLKIT ETHOS\n")

    env = {"HOME": str(fake_home), "PATH": "/usr/bin:/bin"}
    r = _run(f". {partials_dir}/ethos-include.sh", env, tmp_path)
    assert r.returncode == 0
    assert "TOOLKIT ETHOS" in r.stdout


def test_ethos_empty_consumer_falls_back(tmp_path, partials_dir):
    """REQ-416 H1 regression: an empty `.adlc/ETHOS.md` MUST fall back.

    Without `[ -s file ]`, `cat` would silently succeed on the empty file
    and swallow the ethos block.
    """
    adlc = tmp_path / ".adlc"
    adlc.mkdir()
    (adlc / "ETHOS.md").write_text("")  # empty file

    fake_home = tmp_path / "home"
    (fake_home / ".claude" / "skills").mkdir(parents=True)
    (fake_home / ".claude" / "skills" / "ETHOS.md").write_text("TOOLKIT ETHOS\n")

    env = {"HOME": str(fake_home), "PATH": "/usr/bin:/bin"}
    r = _run(f". {partials_dir}/ethos-include.sh", env, tmp_path)
    assert r.returncode == 0
    assert "TOOLKIT ETHOS" in r.stdout


def test_ethos_no_source(tmp_path, partials_dir):
    """Both consumer and toolkit copies absent → emit 'No ethos found'."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    env = {"HOME": str(fake_home), "PATH": "/usr/bin:/bin"}
    r = _run(f". {partials_dir}/ethos-include.sh", env, tmp_path)
    assert r.returncode == 0
    assert "No ethos found" in r.stdout


# ---------------------------------------------------------------------------
# kimi-gate.sh
# ---------------------------------------------------------------------------

_GATE_PROBE = (
    ". {partials}/kimi-gate.sh; "
    'adlc_kimi_gate_check; rc=$?; '
    'echo "RC=$rc"; echo "REASON=$ADLC_KIMI_GATE_REASON"'
)


def test_kimi_gate_available(tmp_path, partials_dir):
    """Gate returns 0 / REASON=ok when ask-kimi is on PATH.

    Soft prereq: requires `ask-kimi` on the host PATH. Skipped if absent
    (the assertions assert RC=0, which is only achievable with the binary).
    """
    ask_kimi = shutil.which("ask-kimi")
    if not ask_kimi:
        pytest.skip("ask-kimi not on host PATH; can't verify the 'available' branch")

    # Provide a PATH that includes the dir holding ask-kimi.
    path = f"{os.path.dirname(ask_kimi)}:/usr/bin:/bin"
    env = {"PATH": path, "HOME": str(tmp_path)}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=0" in r.stdout, r.stdout + r.stderr
    assert "REASON=ok" in r.stdout, r.stdout


def test_kimi_gate_disabled(tmp_path, partials_dir):
    """ADLC_DISABLE_KIMI=1 → return 1, REASON=disabled-via-env."""
    ask_kimi = shutil.which("ask-kimi")
    if not ask_kimi:
        pytest.skip("ask-kimi not on host PATH; needed to reach the disabled branch")

    path = f"{os.path.dirname(ask_kimi)}:/usr/bin:/bin"
    env = {"PATH": path, "HOME": str(tmp_path), "ADLC_DISABLE_KIMI": "1"}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=1" in r.stdout, r.stdout + r.stderr
    assert "REASON=disabled-via-env" in r.stdout, r.stdout


def test_kimi_gate_unavailable(tmp_path, partials_dir):
    """ask-kimi absent from PATH → return 2, REASON=no-binary."""
    # Restrict PATH to system dirs that don't contain ask-kimi.
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=2" in r.stdout, r.stdout + r.stderr
    assert "REASON=no-binary" in r.stdout, r.stdout
