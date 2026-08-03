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
# delegate-gate.sh
# ---------------------------------------------------------------------------

_GATE_PROBE = (
    ". {partials}/delegate-gate.sh; "
    'adlc_delegate_gate_check; rc=$?; '
    'echo "RC=$rc"; echo "REASON=$ADLC_DELEGATE_GATE_REASON"'
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


def test_delegate_gate_available(tmp_path, partials_dir):
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


def test_delegate_gate_available_via_legacy_key(tmp_path, partials_dir):
    """Continuity: a legacy MOONSHOT_API_KEY in env opts in (return 0)."""
    path = _stub_adlc_read_on_path(tmp_path)
    env = {"PATH": path, "HOME": str(tmp_path), "MOONSHOT_API_KEY": "sk-x"}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=0" in r.stdout, r.stdout + r.stderr
    assert "REASON=ok" in r.stdout, r.stdout


def test_delegate_gate_not_opted_in(tmp_path, partials_dir):
    """BR-11 fresh-install posture: available but no opt-in → return 1,
    REASON=not-opted-in (the canonical de-branded gate reason; REQ-522 retired
    the legacy disabled-via-env alias for this case)."""
    path = _stub_adlc_read_on_path(tmp_path)
    env = {"PATH": path, "HOME": str(tmp_path)}  # no opt-in signal
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=1" in r.stdout, r.stdout + r.stderr
    assert "REASON=not-opted-in" in r.stdout, r.stdout


def test_legacy_disable_kimi_flag_is_ignored(tmp_path, partials_dir):
    """REQ-522 BR-3: ADLC_DISABLE_KIMI is no longer an accepted disable flag —
    only ADLC_DISABLE_DELEGATE disables. An opted-in run with the legacy flag set
    must still gate OPEN (RC=0)."""
    path = _stub_adlc_read_on_path(tmp_path)
    env = {"PATH": path, "HOME": str(tmp_path),
           "ADLC_DELEGATE_ENABLED": "1", "ADLC_DISABLE_KIMI": "1"}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=0" in r.stdout, r.stdout + r.stderr
    assert "REASON=ok" in r.stdout, r.stdout


def test_delegate_gate_disabled_via_flag(tmp_path, partials_dir):
    """ADLC_DISABLE_DELEGATE=1 disables → return 1, REASON=disabled-via-env."""
    path = _stub_adlc_read_on_path(tmp_path)
    env = {"PATH": path, "HOME": str(tmp_path),
           "ADLC_DELEGATE_ENABLED": "1", "ADLC_DISABLE_DELEGATE": "1"}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=1" in r.stdout, r.stdout + r.stderr
    assert "REASON=disabled-via-env" in r.stdout, r.stdout


def test_delegate_gate_unavailable(tmp_path, partials_dir):
    """adlc-read absent from PATH → return 2, REASON=no-binary."""
    # Restrict PATH to system dirs that don't contain adlc-read.
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    r = _run(_GATE_PROBE.format(partials=partials_dir), env, tmp_path)
    assert "RC=2" in r.stdout, r.stdout + r.stderr
    assert "REASON=no-binary" in r.stdout, r.stdout


# ---------------------------------------------------------------------------
# delegate-gate.sh — $HOME/bin fallback resolution (ADLC_READ_BIN)
# ---------------------------------------------------------------------------
# GUI-launched Claude Code sessions may run with a PATH that lacks ~/bin (only
# .zshrc adds it). The gate must then fall back to an executable
# $HOME/bin/adlc-read instead of returning 2/no-binary.

_GATE_PROBE_BIN = (
    ". {partials}/delegate-gate.sh; "
    'adlc_delegate_gate_check; rc=$?; '
    'echo "RC=$rc"; echo "REASON=$ADLC_DELEGATE_GATE_REASON"; '
    'echo "READBIN=$ADLC_READ_BIN"'
)


def _stub_adlc_read_in_home_bin(home, enabled="0"):
    """Drop an `adlc-read` stub into <home>/bin (NOT on PATH) and return its
    path. Mirrors _stub_adlc_read_on_path, including the `--print-enabled`
    handling (parameterized so the config-probe branch can be exercised)."""
    bindir = home / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "adlc-read"
    stub.write_text(
        f'#!/bin/sh\n[ "$1" = "--print-enabled" ] && {{ echo {enabled}; exit 0; }}\nexit 0\n'
    )
    stub.chmod(0o755)
    return stub


def test_delegate_gate_home_bin_fallback(tmp_path, partials_dir):
    """adlc-read off PATH but executable at $HOME/bin/adlc-read → the gate
    resolves it (RC=0 when opted in) and exports the absolute path."""
    stub = _stub_adlc_read_in_home_bin(tmp_path)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
           "ADLC_DELEGATE_ENABLED": "1"}
    r = _run(_GATE_PROBE_BIN.format(partials=partials_dir), env, tmp_path)
    assert "RC=0" in r.stdout, r.stdout + r.stderr
    assert "REASON=ok" in r.stdout, r.stdout
    assert f"READBIN={stub}" in r.stdout, r.stdout


def test_delegate_gate_home_bin_not_executable(tmp_path, partials_dir):
    """A NON-executable $HOME/bin/adlc-read must NOT rescue the gate —
    still RC=2 / no-binary, and ADLC_READ_BIN stays empty."""
    stub = _stub_adlc_read_in_home_bin(tmp_path)
    stub.chmod(0o644)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
           "ADLC_DELEGATE_ENABLED": "1"}
    r = _run(_GATE_PROBE_BIN.format(partials=partials_dir), env, tmp_path)
    assert "RC=2" in r.stdout, r.stdout + r.stderr
    assert "REASON=no-binary" in r.stdout, r.stdout
    assert "READBIN=\n" in r.stdout, r.stdout


def test_delegate_gate_path_wins_over_home_bin(tmp_path, partials_dir):
    """When adlc-read is BOTH on PATH and at $HOME/bin, PATH wins and
    ADLC_READ_BIN is the bare name (today's behavior, unchanged)."""
    path = _stub_adlc_read_on_path(tmp_path)
    _stub_adlc_read_in_home_bin(tmp_path)
    env = {"PATH": path, "HOME": str(tmp_path), "ADLC_DELEGATE_ENABLED": "1"}
    r = _run(_GATE_PROBE_BIN.format(partials=partials_dir), env, tmp_path)
    assert "RC=0" in r.stdout, r.stdout + r.stderr
    assert "READBIN=adlc-read" in r.stdout, r.stdout


def test_delegate_gate_read_bin_resolved_at_source_time(tmp_path, partials_dir):
    """Merely SOURCING the partial exports ADLC_READ_BIN — the delegated-
    invocation fences re-source the gate without calling the gate function
    (fenced blocks do not share shell state — REQ-522 BR-4)."""
    stub = _stub_adlc_read_in_home_bin(tmp_path)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    script = f'. {partials_dir}/delegate-gate.sh; echo "READBIN=$ADLC_READ_BIN"'
    r = _run(script, env, tmp_path)
    assert f"READBIN={stub}" in r.stdout, r.stdout + r.stderr


def test_delegate_gate_config_probe_uses_resolved_bin(tmp_path, partials_dir):
    """The config-file opt-in probe must invoke the RESOLVED binary: with no
    env opt-in, a config file present, and a $HOME/bin-only stub whose
    --print-enabled prints 1, the gate opens (RC=0). Before the ADLC_READ_BIN
    fix this branch re-ran `command -v adlc-read` and could never fire off-PATH."""
    _stub_adlc_read_in_home_bin(tmp_path, enabled="1")
    cfg = tmp_path / "config.yml"
    cfg.write_text("enabled: true\n")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
           "ADLC_CONFIG": str(cfg)}
    r = _run(_GATE_PROBE_BIN.format(partials=partials_dir), env, tmp_path)
    assert "RC=0" in r.stdout, r.stdout + r.stderr
    assert "REASON=ok" in r.stdout, r.stdout
