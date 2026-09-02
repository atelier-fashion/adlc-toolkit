"""Per-check tests (TASK-003 / BR-4, BR-5, BR-6) — offline, tmp_path-driven."""
import os
import stat
import subprocess
import sys

import pytest

import checks
from doctor import Profile, Result


def _profile(tmp_path, os_name="Darwin"):
    return Profile(os=os_name, login_shell="/bin/zsh", repo_root=str(tmp_path))


def _home(tmp_path, monkeypatch):
    """Point `~` at a sandbox HOME and return it (nothing installed in it)."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setattr(os.path, "expanduser",
                        lambda p: p.replace("~", str(home)))
    return home


def _script(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def _poisoned_yaml(tmp_path):
    """A dir that, first on PYTHONPATH, makes ``import yaml`` raise ImportError."""
    pkg = tmp_path / "poison" / "yaml"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(
        "raise ImportError('no module named yaml (test poison)')\n")
    return str(tmp_path / "poison")


def _interpreter_without_pyyaml(tmp_path):
    """A REAL interpreter that genuinely cannot import yaml.

    Not a stub that exits 1: the check's claim is about an interpreter, so the
    probe must be answered by one — this is the machine with no PyYAML, built
    out of the machine that has it.
    """
    return _script(tmp_path / "nopyyaml" / "python3",
                   '#!/bin/sh\nPYTHONPATH="%s" exec "%s" "$@"\n'
                   % (_poisoned_yaml(tmp_path), sys.executable))


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


# --- interpreter selection + the pyyaml check (REQ-609 BR-8, ADR-2) --------

def test_delegate_interpreter_prefers_venv(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    venv = _script(home / ".claude" / "delegate-venv" / "bin" / "python3",
                   '#!/bin/sh\nexec "%s" "$@"\n' % sys.executable)
    assert checks._delegate_interpreter() == venv


def test_delegate_interpreter_falls_back_when_venv_absent(tmp_path, monkeypatch):
    """No venv (the default machine) -> the interpreter adlc is running under.

    A shim that `exec`s a missing interpreter would break doctor on exactly the
    machine that most needs it (LESSON-395), so absence is a fallback, never an
    error.
    """
    _home(tmp_path, monkeypatch)
    assert checks._delegate_interpreter() == sys.executable


def test_delegate_interpreter_ignores_non_executable_venv(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    target = home / ".claude" / "delegate-venv" / "bin" / "python3"
    target.parent.mkdir(parents=True)
    target.write_text("not executable\n")
    target.chmod(0o644)
    assert checks._delegate_interpreter() == sys.executable


@pytest.mark.parametrize("probe", ["_config_enabled", "_forge_pat_status"])
def test_config_probes_run_in_the_selected_interpreter(tmp_path, monkeypatch, probe):
    """Both config probes read with the interpreter the real call uses (BR-8).

    Probing with a bare `python3` from $PATH answers for an interpreter nobody
    runs `adlc` under — the shape LESSON-392 names: an "is it enabled?" probe
    must share the real call's resolution path.
    """
    (tmp_path / "tools" / "delegate").mkdir(parents=True)
    (tmp_path / "tools" / "delegate" / "_common.py").write_text("")
    (tmp_path / "tools" / "adlc").mkdir(parents=True)
    (tmp_path / "tools" / "adlc" / "forge_config.py").write_text("")
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: "/sentinel/python3")
    seen = []

    def fake_run(argv, *a, **k):
        seen.append(argv)
        return _fake_proc(1)

    monkeypatch.setattr(checks.subprocess, "run", fake_run)
    getattr(checks, probe)(_profile(tmp_path))
    assert seen and seen[0][0] == "/sentinel/python3", seen


def test_pyyaml_check_reports_fix_when_missing(tmp_path, monkeypatch):
    """No PyYAML in the interpreter adlc runs under -> FAIL with the fix.

    The detail names the interpreter, because the failure is per-interpreter:
    the venv may have PyYAML while $PATH's python3 does not, and "PyYAML is
    missing" without saying *where* sends the operator to install it into the
    wrong one.
    """
    interp = _interpreter_without_pyyaml(tmp_path)
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: interp)
    result, detail, remediation = checks.check_pyyaml(_profile(tmp_path))
    assert result is Result.FAIL
    assert interp in detail and "PyYAML" in detail
    assert "install.sh --with-delegation" in remediation
    assert "pyyaml>=6.0" in remediation


def test_pyyaml_check_passes_naming_the_interpreter(tmp_path, monkeypatch):
    """Benign twin: an interpreter that HAS PyYAML passes, with the version."""
    yaml = pytest.importorskip("yaml")
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: sys.executable)
    result, detail, remediation = checks.check_pyyaml(_profile(tmp_path))
    assert result is Result.PASS
    assert yaml.__version__ in detail and sys.executable in detail
    assert remediation == ""


def test_pyyaml_check_never_skips_and_never_crashes(tmp_path, monkeypatch):
    """SKIP is not a valid outcome, and an unrunnable interpreter still reports.

    Every machine parses the config, delegation opted into or not, so there is
    no "not applicable" branch to hide behind.
    """
    monkeypatch.setattr(checks, "_delegate_interpreter",
                        lambda: str(tmp_path / "no-such-python3"))
    result, detail, remediation = checks.check_pyyaml(_profile(tmp_path))
    assert result is Result.FAIL
    assert remediation and "no-such-python3" in detail


def test_checks_import_pulls_in_no_yaml(repo_root):
    """`import checks` must not import PyYAML — transitively (LESSON-395).

    The `pyyaml` check reports on machines that do not have it; a registry that
    cannot be built without PyYAML could never report its absence. The probe is
    a subprocess for exactly this reason.
    """
    adlc_dir = os.path.join(repo_root, "tools", "adlc")
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import checks, doctor; "
         "print('yaml' in sys.modules, len(checks.REGISTRY) > 0)", adlc_dir],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False True"


def test_pyyaml_check_registered():
    ids = [c.id for c in checks.REGISTRY]
    assert "pyyaml" in ids
    # Registered next to the delegation check it explains.
    assert ids.index("pyyaml") == ids.index("delegate-gate") + 1


def test_doctor_reports_pyyaml_fail_on_a_bare_machine(tmp_path, repo_root):
    """LESSON-395: run doctor with NOTHING installed and assert it reports.

    Sandbox `HOME` (so there is no delegate venv, no skills symlink, no
    counters) and an interpreter whose `import yaml` raises. Doctor must print
    the `pyyaml` row as FAIL with the fix and exit non-zero — not traceback,
    which is the failure mode this lesson exists for.

    The subset is deliberate: `reservations` pushes a probe ref to `origin`, so
    it is excluded to keep the suite offline. The included checks cover the
    symlink, config, forge and counter paths, all of which run without PyYAML.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    workdir = tmp_path / "elsewhere"          # not a git repo -> forge SKIPs
    workdir.mkdir()
    env = dict(os.environ, HOME=str(home), PYTHONPATH=_poisoned_yaml(tmp_path))
    env.pop("ADLC_CONFIG", None)
    out = subprocess.run(
        [sys.executable, os.path.join(repo_root, "tools", "adlc", "adlc.py"),
         "doctor", "--checks",
         "pyyaml,skills-symlink,forge,counters,template-version,claude-code"],
        capture_output=True, text=True, cwd=str(workdir), env=env,
    )
    assert "Traceback" not in out.stderr, out.stderr
    assert "check raised" not in out.stdout, out.stdout
    pyyaml_rows = [ln for ln in out.stdout.splitlines() if " pyyaml " in ln]
    assert len(pyyaml_rows) == 1, out.stdout
    assert pyyaml_rows[0].startswith("[FAIL] pyyaml"), out.stdout
    assert "PyYAML is not importable" in pyyaml_rows[0], out.stdout
    assert "install.sh --with-delegation" in out.stdout
    assert "verdict: FAILED" in out.stdout
    assert out.returncode == 1


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


# --- reservations pushability check (REQ-546 BR-13) ------------------------

def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True)


def _repo_with_remote(tmp_path, name, reject=False):
    """A clone whose origin is a local bare remote. reject=True installs a
    pre-receive hook that declines every push (server-policy failure)."""
    bare = tmp_path / f"{name}.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    if reject:
        hook = bare / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho 'namespace forbidden' >&2\nexit 1\n")
        hook.chmod(0o755)
    repo = tmp_path / name
    subprocess.run(["git", "clone", "-q", str(bare), str(repo)], check=True)
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    if not reject:
        _git(repo, "push", "-q", "origin", "HEAD:main")
    return repo


def test_reservations_pass_writable_remote(tmp_path, monkeypatch):
    repo = _repo_with_remote(tmp_path, "good")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    result, detail, _rem = checks.check_reservations(_profile(tmp_path))
    assert result is Result.PASS, detail
    # The ephemeral probe ref must be gone afterward (the one sanctioned deletion).
    left = _git(repo, "ls-remote", "origin", "refs/adlc/ids/_probe/*").stdout.strip()
    assert left == "", f"probe ref left behind: {left!r}"


def test_reservations_fail_names_server_policy_layer(tmp_path, monkeypatch):
    repo = _repo_with_remote(tmp_path, "ro", reject=True)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    result, detail, remediation = checks.check_reservations(_profile(tmp_path))
    assert result is Result.FAIL
    assert "server policy" in detail
    assert remediation  # copy-pasteable remediation present (BR-5 of REQ-519)


def test_reservations_skip_when_no_remote(tmp_path, monkeypatch):
    repo = tmp_path / "norem"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    monkeypatch.chdir(repo)
    result, detail, _rem = checks.check_reservations(_profile(tmp_path))
    assert result is Result.SKIP
    assert "no git remote" in detail


def test_reservations_registered_after_forge():
    names = [c.id for c in checks.REGISTRY]
    assert "reservations" in names
    assert names.index("reservations") == names.index("forge") + 1


def test_classify_git_failure_layers():
    assert checks._classify_git_failure("fatal: Authentication failed") == "auth"
    assert checks._classify_git_failure("! [remote rejected] (pre-receive hook declined)") == "server policy"
    assert checks._classify_git_failure("fatal: Could not read from remote repository") == "transport"
    assert checks._classify_git_failure("something odd") == "unknown"
