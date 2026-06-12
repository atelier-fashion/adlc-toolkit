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


def _stub_adlc_read_on_path(tmp_path):
    """Drop a no-op `adlc-read` stub into a tmp bin dir and return a PATH
    that prepends it. The new gate (REQ-515) probes `command -v adlc-read`,
    so a no-op script is sufficient. The stub also handles `--print-enabled`
    (prints 0 by default; tests that need config opt-in are separate) so the
    gate's config-probe branch does not error."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "adlc-read"
    stub.write_text('#!/bin/sh\n[ "$1" = "--print-enabled" ] && { echo 0; exit 0; }\nexit 0\n')
    stub.chmod(0o755)
    return f"{bindir}:/usr/bin:/bin"


def test_kimi_gate_available(tmp_path, partials_dir):
    """Gate returns 0 / REASON=ok when adlc-read is on PATH AND opted in.

    REQ-515 adds the BR-11 opt-in requirement, so availability alone is no
    longer enough — ADLC_DELEGATE_ENABLED=1 (or a legacy key) is required.
    Self-contained: stubs a no-op adlc-read in tmp_path.
    """
    path = _stub_adlc_read_on_path(tmp_path)
    env = {"PATH": path, "HOME": str(tmp_path), "ADLC_DELEGATE_ENABLED": "1"}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=0" in r.stdout, r.stdout + r.stderr
    assert "REASON=ok" in r.stdout, r.stdout


def test_kimi_gate_available_via_legacy_key(tmp_path, partials_dir):
    """Continuity: a legacy MOONSHOT_API_KEY in env opts in (return 0)."""
    path = _stub_adlc_read_on_path(tmp_path)
    env = {"PATH": path, "HOME": str(tmp_path), "MOONSHOT_API_KEY": "sk-x"}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=0" in r.stdout, r.stdout + r.stderr
    assert "REASON=ok" in r.stdout, r.stdout


def test_kimi_gate_not_opted_in(tmp_path, partials_dir):
    """BR-11 fresh-install posture: available but no opt-in → return 1,
    surfaced as the legacy REASON=disabled-via-env (so callers' disabled
    branch runs the fallback)."""
    path = _stub_adlc_read_on_path(tmp_path)
    env = {"PATH": path, "HOME": str(tmp_path)}  # no opt-in signal
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=1" in r.stdout, r.stdout + r.stderr
    assert "REASON=disabled-via-env" in r.stdout, r.stdout


def test_kimi_gate_disabled(tmp_path, partials_dir):
    """ADLC_DISABLE_KIMI=1 → return 1, REASON=disabled-via-env (even when
    otherwise opted in)."""
    path = _stub_adlc_read_on_path(tmp_path)
    env = {"PATH": path, "HOME": str(tmp_path),
           "ADLC_DELEGATE_ENABLED": "1", "ADLC_DISABLE_KIMI": "1"}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=1" in r.stdout, r.stdout + r.stderr
    assert "REASON=disabled-via-env" in r.stdout, r.stdout


def test_kimi_gate_disabled_via_new_flag(tmp_path, partials_dir):
    """ADLC_DISABLE_DELEGATE=1 (new flag) also disables → return 1."""
    path = _stub_adlc_read_on_path(tmp_path)
    env = {"PATH": path, "HOME": str(tmp_path),
           "ADLC_DELEGATE_ENABLED": "1", "ADLC_DISABLE_DELEGATE": "1"}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=1" in r.stdout, r.stdout + r.stderr
    assert "REASON=disabled-via-env" in r.stdout, r.stdout


def test_kimi_gate_unavailable(tmp_path, partials_dir):
    """adlc-read absent from PATH → return 2, REASON=no-binary."""
    # Restrict PATH to system dirs that don't contain adlc-read.
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=2" in r.stdout, r.stdout + r.stderr
    assert "REASON=no-binary" in r.stdout, r.stdout
