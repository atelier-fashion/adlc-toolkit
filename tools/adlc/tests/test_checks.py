"""Per-check tests (TASK-003 / BR-4, BR-5, BR-6) — offline, tmp_path-driven."""
import os
import subprocess

import pytest

import checks
from doctor import Profile, Result


def _profile(tmp_path, os_name="Darwin"):
    return Profile(os=os_name, login_shell="/bin/zsh", repo_root=str(tmp_path))


# --- symlink checks --------------------------------------------------------

def test_skills_symlink_pass(tmp_path, monkeypatch):
    # A real git checkout to point at.
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(["git", "-C", str(checkout), "init", "-q"], check=True)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    link = home / ".claude" / "skills"
    link.symlink_to(checkout)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    result, _detail, _rem = checks.check_skills_symlink(_profile(tmp_path))
    assert result is Result.PASS


def test_skills_symlink_fail_when_missing(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    result, _detail, remediation = checks.check_skills_symlink(_profile(tmp_path))
    assert result is Result.FAIL
    assert "ln -sfn" in remediation  # copy-pasteable fix (BR-5)


# --- counters --------------------------------------------------------------

def test_counters_pass_numeric(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    for name in checks._COUNTERS:
        (home / ".claude" / name).write_text("42\n")
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    result, _detail, _rem = checks.check_counters(_profile(tmp_path))
    assert result is Result.PASS


def test_counters_fail_non_numeric(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".global-next-req").write_text("not-a-number\n")
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    result, detail, remediation = checks.check_counters(_profile(tmp_path))
    assert result is Result.FAIL
    assert "not numeric" in detail
    assert "printf" in remediation


def test_counters_absent_is_not_a_failure(tmp_path, monkeypatch):
    # First-run: no counters yet — must NOT fail (BR-4 skip-absent semantics).
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    result, _detail, _rem = checks.check_counters(_profile(tmp_path))
    assert result is Result.PASS


def test_counters_stale_lock_flagged(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".global-next-req").write_text("7\n")
    lock = home / ".claude" / ".global-next-req.lock.d"
    lock.mkdir()
    old = __import__("time").time() - checks._STALE_LOCK_SECONDS - 60
    os.utime(lock, (old, old))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    result, detail, remediation = checks.check_counters(_profile(tmp_path))
    assert result is Result.FAIL
    assert "stale lock" in detail
    assert "rmdir" in remediation


# --- gh checks (PATH-driven) -----------------------------------------------

def test_gh_present_fail_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    result, _detail, remediation = checks.check_gh_present(_profile(tmp_path))
    assert result is Result.FAIL
    assert remediation  # an install line, not "see docs"


def test_gh_auth_skips_when_gh_absent(tmp_path, monkeypatch):
    # check_gh_auth is retained as a helper (folded into check_forge) but is no
    # longer in REGISTRY (REQ-520 ADR-4); the helper still behaves the same.
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    result, _detail, _rem = checks.check_gh_auth(_profile(tmp_path))
    assert result is Result.SKIP


def test_gh_auth_not_in_registry():
    # REQ-520: the standalone gh-auth check is superseded by `forge`.
    ids = {c.id for c in checks.REGISTRY}
    assert "gh-auth" not in ids
    assert "forge" in ids


# --- forge check (REQ-520 BR-7): PASS/FAIL/SKIP matrix ---------------------

def test_forge_skips_when_no_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_has_remote", lambda p: False)
    result, detail, _rem = checks.check_forge(_profile(tmp_path))
    assert result is Result.SKIP
    assert "no git remote" in detail


def test_forge_github_pass_when_authed(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_has_remote", lambda p: True)
    monkeypatch.setattr(checks, "_forge_provider_verdict", lambda p: ("github", "resolved"))
    monkeypatch.setattr(checks.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(checks.subprocess, "run",
                        lambda *a, **k: _fake_proc(0))
    result, _detail, _rem = checks.check_forge(_profile(tmp_path))
    assert result is Result.PASS


def test_forge_github_fail_when_unauthed(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_has_remote", lambda p: True)
    monkeypatch.setattr(checks, "_forge_provider_verdict", lambda p: ("github", "resolved"))
    monkeypatch.setattr(checks.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **k: _fake_proc(1))
    result, _detail, remediation = checks.check_forge(_profile(tmp_path))
    assert result is Result.FAIL
    assert "gh auth login" in remediation


def test_forge_ado_pass_with_pat(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_has_remote", lambda p: True)
    monkeypatch.setattr(checks, "_forge_provider_verdict",
                        lambda p: ("azure-devops", "resolved"))
    monkeypatch.setattr(checks.shutil, "which", lambda name: "/usr/bin/az")
    # az account show fails (no login) but the PAT env var IS set -> PASS.
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **k: _fake_proc(1))
    monkeypatch.setattr(checks, "_forge_pat_status", lambda p: ("ADO_PAT", True))
    result, detail, _rem = checks.check_forge(_profile(tmp_path))
    assert result is Result.PASS
    assert "PAT env var ADO_PAT" in detail


def test_forge_ado_fail_no_pat_no_login(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_has_remote", lambda p: True)
    monkeypatch.setattr(checks, "_forge_provider_verdict",
                        lambda p: ("azure-devops", "resolved"))
    monkeypatch.setattr(checks.shutil, "which", lambda name: "/usr/bin/az")
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **k: _fake_proc(1))
    monkeypatch.setattr(checks, "_forge_pat_status", lambda p: ("ADO_PAT", False))
    result, _detail, remediation = checks.check_forge(_profile(tmp_path))
    assert result is Result.FAIL
    assert "ADO_PAT" in remediation


def test_forge_ado_fail_when_az_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_has_remote", lambda p: True)
    monkeypatch.setattr(checks, "_forge_provider_verdict",
                        lambda p: ("azure-devops", "resolved"))
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    result, detail, remediation = checks.check_forge(_profile(tmp_path))
    assert result is Result.FAIL
    assert "az" in detail and remediation


def test_forge_unresolved_fails_loud(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_has_remote", lambda p: True)
    monkeypatch.setattr(checks, "_forge_provider_verdict", lambda p: (None, "unresolved"))
    result, _detail, remediation = checks.check_forge(_profile(tmp_path))
    assert result is Result.FAIL
    assert "forge.provider" in remediation


class _FakeProc:
    def __init__(self, rc):
        self.returncode = rc
        self.stdout = ""
        self.stderr = ""


def _fake_proc(rc):
    return _FakeProc(rc)


# --- path-shims ------------------------------------------------------------

def test_path_shims_fail_when_adlc_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    result, _detail, remediation = checks.check_path_shims(_profile(tmp_path))
    assert result is Result.FAIL
    assert "install.sh --repair" in remediation


# --- delegate-gate mapping (REUSES REQ-515; map rc -> Result) --------------

@pytest.mark.parametrize("rc,expected", [
    (0, Result.PASS),   # delegated
    (1, Result.SKIP),   # not opted in / disabled
])
def test_delegate_gate_rc_mapping_pass_skip(tmp_path, monkeypatch, rc, expected):
    monkeypatch.setattr(checks, "_gate_verdict", lambda p: (rc, "reason"))
    result, _detail, _rem = checks.check_delegate_gate(_profile(tmp_path))
    assert result is expected


def test_delegate_gate_rc2_skip_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_gate_verdict", lambda p: (2, "no-binary"))
    monkeypatch.setattr(checks, "_config_enabled", lambda p: False)
    result, _detail, _rem = checks.check_delegate_gate(_profile(tmp_path))
    assert result is Result.SKIP


def test_delegate_gate_rc2_fail_when_misconfigured(tmp_path, monkeypatch):
    # config enabled:true but binary missing == misconfigured -> FAIL.
    monkeypatch.setattr(checks, "_gate_verdict", lambda p: (2, "no-binary"))
    monkeypatch.setattr(checks, "_config_enabled", lambda p: True)
    result, detail, remediation = checks.check_delegate_gate(_profile(tmp_path))
    assert result is Result.FAIL
    assert "enabled: true" in detail
    assert remediation


def test_delegate_gate_probe_failure_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_gate_verdict", lambda p: (None, "gate-probe-failed"))
    result, _detail, _rem = checks.check_delegate_gate(_profile(tmp_path))
    assert result is Result.FAIL


# --- claude-code is report-only (never FAIL) -------------------------------

def test_claude_code_never_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    result, _detail, _rem = checks.check_claude_code(_profile(tmp_path))
    assert result in (Result.PASS, Result.SKIP)
    assert result is not Result.FAIL


# --- launchctl gated off when delegation inactive --------------------------

def test_launchctl_skips_when_delegation_inactive(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_gate_verdict", lambda p: (1, "not-opted-in"))
    result, _detail, _rem = checks.check_launchctl(_profile(tmp_path, os_name="Darwin"))
    assert result is Result.SKIP
