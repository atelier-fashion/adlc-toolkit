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


def _venv(tmp_path, monkeypatch, with_pyyaml):
    """A sandbox HOME carrying a delegate venv; returns (home, interpreter path).

    ``with_pyyaml`` creates the ``lib/python*/site-packages/yaml`` package
    directory the ONE interpreter rule tests for (REQ-609 BR-8, ADR-2). The
    directory is the whole signal on purpose: the rule must be answerable
    without spawning an interpreter, because the two other sites that carry it
    are shell (`install.sh`'s shim text and `partials/forge.sh`).
    """
    home = _home(tmp_path, monkeypatch)
    exe = _script(home / ".claude" / "delegate-venv" / "bin" / "python3",
                  '#!/bin/sh\nexec "%s" "$@"\n' % sys.executable)
    if with_pyyaml:
        (home / ".claude" / "delegate-venv" / "lib" / "python3.9"
         / "site-packages" / "yaml").mkdir(parents=True)
    return home, exe


def _machine_cfg(home, monkeypatch, text="delegate:\n  enabled: false\n"):
    """Write a machine config into the sandbox HOME and clear $ADLC_CONFIG.

    The `pyyaml` check SKIPs when there is nothing to parse, so every case that
    asserts PASS/FAIL has to put a config on the machine first.
    """
    monkeypatch.delenv("ADLC_CONFIG", raising=False)
    p = home / ".claude" / "adlc" / "config.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


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
    """A venv that actually carries PyYAML is the interpreter (the ONE rule)."""
    _home_dir, exe = _venv(tmp_path, monkeypatch, with_pyyaml=True)
    assert checks._delegate_interpreter() == exe


def test_delegate_interpreter_falls_back_when_venv_lacks_pyyaml(tmp_path, monkeypatch):
    """A venv WITHOUT PyYAML is NOT preferred — the half the rule was missing.

    A venv created before REQ-609 carries `openai` and no PyYAML. Preferring it
    on the strength of `bin/python3` alone points every config read at the one
    interpreter on the machine that cannot parse the file: the loader answers
    `dependency-missing`, the forge consumer takes its ADR-2 carve-out, and a
    written `forge.provider` is silently overridden by origin-URL auto-detection.
    """
    _home_dir, exe = _venv(tmp_path, monkeypatch, with_pyyaml=False)
    assert os.access(exe, os.X_OK)   # non-vacuity: the venv IS runnable
    assert checks._delegate_interpreter() == sys.executable


def test_delegate_interpreter_falls_back_when_venv_absent(tmp_path, monkeypatch):
    """No venv (the default machine) -> the interpreter adlc is running under.

    A shim that `exec`s a missing interpreter would break doctor on exactly the
    machine that most needs it (LESSON-395), so absence is a fallback, never an
    error. `sys.executable` IS `python3` from `$PATH` when `adlc` was started by
    the shim's fallback arm — the shell sites spell the same rule as `python3`
    because a shell cannot ask "the interpreter running us".
    """
    _home(tmp_path, monkeypatch)
    assert checks._delegate_interpreter() == sys.executable


def test_delegate_interpreter_ignores_non_executable_venv(tmp_path, monkeypatch):
    """The executable half of the rule still bites, PyYAML present or not."""
    home = _home(tmp_path, monkeypatch)
    target = home / ".claude" / "delegate-venv" / "bin" / "python3"
    target.parent.mkdir(parents=True)
    target.write_text("not executable\n")
    target.chmod(0o644)
    (home / ".claude" / "delegate-venv" / "lib" / "python3.9"
     / "site-packages" / "yaml").mkdir(parents=True)
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


def test_every_config_probe_is_bounded_by_a_timeout(tmp_path, monkeypatch):
    """Nothing doctor runs to read the config may hang it (REQ-609 verify B4).

    A venv on a stalled network mount, or an interpreter whose site
    customization blocks, would otherwise hang `adlc doctor` with no output —
    the one thing a bootstrap diagnostic may never do.
    """
    home, _exe = _venv(tmp_path, monkeypatch, with_pyyaml=True)
    _machine_cfg(home, monkeypatch)
    (tmp_path / "tools" / "delegate").mkdir(parents=True)
    (tmp_path / "tools" / "delegate" / "_common.py").write_text("")
    (tmp_path / "tools" / "adlc").mkdir(parents=True)
    (tmp_path / "tools" / "adlc" / "forge_config.py").write_text("")
    seen = []

    def fake_run(argv, *a, **k):
        seen.append(k.get("timeout"))
        return _fake_proc(1)

    monkeypatch.setattr(checks.subprocess, "run", fake_run)
    checks._config_enabled(_profile(tmp_path))
    checks._forge_pat_status(_profile(tmp_path))
    checks.check_pyyaml(_profile(tmp_path))
    assert len(seen) == 3, seen
    assert all(isinstance(t, (int, float)) and t > 0 for t in seen), seen


def test_pyyaml_check_reports_fix_when_missing(tmp_path, monkeypatch):
    """No PyYAML in the interpreter adlc runs under -> FAIL with the fix.

    The detail names the interpreter, because the failure is per-interpreter:
    the venv may have PyYAML while $PATH's python3 does not, and "PyYAML is
    missing" without saying *where* sends the operator to install it into the
    wrong one.

    The fix is the installer, and ONLY the installer: `pip install --user
    'pyyaml>=6.0'` was refused outright inside a venv and, outside one, bypassed
    the `==6.0.3` pin `install.sh` writes — a remediation that either errors or
    installs a different version than the toolkit tests against is not
    copy-pasteable (BR-5).
    """
    home, _exe = _venv(tmp_path, monkeypatch, with_pyyaml=True)
    _machine_cfg(home, monkeypatch)
    interp = _interpreter_without_pyyaml(tmp_path)
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: interp)
    result, detail, remediation = checks.check_pyyaml(_profile(tmp_path))
    assert result is Result.FAIL
    assert interp in detail and "PyYAML is not importable" in detail
    assert remediation == "%s --with-delegation" % os.path.join(str(tmp_path), "install.sh")
    assert "--user" not in remediation and "pyyaml>=6.0" not in remediation


def test_pyyaml_check_offers_the_venv_pip_when_the_venv_lacks_it(tmp_path, monkeypatch):
    """A venv that exists without PyYAML gets the fix for THAT machine.

    `install.sh --with-delegation` also fixes it, but the narrow one names the
    venv the operator already has and the pinned requirements file, so the
    version that lands is the version the toolkit tests against.
    """
    home, _exe = _venv(tmp_path, monkeypatch, with_pyyaml=False)
    _machine_cfg(home, monkeypatch)
    interp = _interpreter_without_pyyaml(tmp_path)
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: interp)
    result, detail, remediation = checks.check_pyyaml(_profile(tmp_path))
    assert result is Result.FAIL
    venv = str(home / ".claude" / "delegate-venv")
    assert os.path.join(venv, "bin", "pip") in remediation
    assert os.path.join(str(tmp_path), "tools", "delegate", "requirements.txt") in remediation
    # And the detail says WHY a venv is installed yet not being used.
    assert venv in detail and "no PyYAML" in detail


def test_pyyaml_check_notes_the_fallback_on_pass(tmp_path, monkeypatch):
    """PASS, but the operator is told the venv is being bypassed and why.

    Silence here is how "adlc quietly runs a different python3 than you think"
    survives: the config parses fine under $PATH's python3 while every delegate
    CLI, which `exec`s the venv unconditionally, cannot parse it at all.
    """
    pytest.importorskip("yaml")
    home, _exe = _venv(tmp_path, monkeypatch, with_pyyaml=False)
    _machine_cfg(home, monkeypatch)
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: sys.executable)
    result, detail, remediation = checks.check_pyyaml(_profile(tmp_path))
    assert result is Result.PASS
    venv = str(home / ".claude" / "delegate-venv")
    assert venv in detail and "no PyYAML" in detail
    # `format_report` prints `remediation` only on FAIL, so a PASS that still
    # needs an action has to carry it in the DETAIL or the operator never sees it.
    assert os.path.join(venv, "bin", "pip") in detail
    assert remediation != ""


def test_pyyaml_check_passes_naming_the_interpreter(tmp_path, monkeypatch):
    """Benign twin: an interpreter that HAS PyYAML passes, with the version."""
    yaml = pytest.importorskip("yaml")
    home, _exe = _venv(tmp_path, monkeypatch, with_pyyaml=True)
    _machine_cfg(home, monkeypatch)
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: sys.executable)
    result, detail, remediation = checks.check_pyyaml(_profile(tmp_path))
    assert result is Result.PASS
    assert yaml.__version__ in detail and sys.executable in detail
    assert remediation == ""


def test_pyyaml_check_skips_when_there_is_nothing_to_parse(tmp_path, monkeypatch):
    """No venv and no config anywhere -> SKIP with a notice, not FAIL.

    A machine that has never opted into delegation and has never written a
    config has nothing for PyYAML to read. FAILing it makes `adlc doctor` red
    on a correctly installed machine, which trains operators to ignore the
    verdict — and the check's own remediation would install a parser for a file
    that does not exist.
    """
    _home(tmp_path, monkeypatch)
    monkeypatch.delenv("ADLC_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    result, detail, remediation = checks.check_pyyaml(_profile(tmp_path))
    assert result is Result.SKIP
    assert detail and "config" in detail
    assert remediation == ""


def test_pyyaml_check_does_not_skip_once_a_config_exists(tmp_path, monkeypatch):
    """The SKIP is about "nothing to parse", so a written config ends it.

    Either config path counts — the machine one and the project one — because
    either is a file whose contents the operator expects to be honoured.
    """
    home = _home(tmp_path, monkeypatch)
    monkeypatch.delenv("ADLC_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    interp = _interpreter_without_pyyaml(tmp_path)
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: interp)
    assert checks.check_pyyaml(_profile(tmp_path))[0] is Result.SKIP

    proj = tmp_path / ".adlc" / "config.yml"
    proj.parent.mkdir(parents=True, exist_ok=True)
    proj.write_text("forge:\n  provider: github\n")
    assert checks.check_pyyaml(_profile(tmp_path))[0] is Result.FAIL

    proj.unlink()
    assert checks.check_pyyaml(_profile(tmp_path))[0] is Result.SKIP
    _machine_cfg(home, monkeypatch)
    assert checks.check_pyyaml(_profile(tmp_path))[0] is Result.FAIL


def test_pyyaml_check_never_crashes_on_an_unrunnable_interpreter(tmp_path, monkeypatch):
    """An interpreter that cannot be executed still REPORTS (LESSON-395)."""
    home, _exe = _venv(tmp_path, monkeypatch, with_pyyaml=True)
    _machine_cfg(home, monkeypatch)
    monkeypatch.setattr(checks, "_delegate_interpreter",
                        lambda: str(tmp_path / "no-such-python3"))
    result, detail, remediation = checks.check_pyyaml(_profile(tmp_path))
    assert result is Result.FAIL
    assert remediation and "no-such-python3" in detail


def test_pyyaml_check_reports_a_hung_interpreter_instead_of_hanging(tmp_path, monkeypatch):
    """A probe that times out is a FAIL, not a doctor that never returns."""
    home, _exe = _venv(tmp_path, monkeypatch, with_pyyaml=True)
    _machine_cfg(home, monkeypatch)
    hung = _script(tmp_path / "hung" / "python3", "#!/bin/sh\nsleep 120\n")
    monkeypatch.setattr(checks, "_delegate_interpreter", lambda: hung)

    def fake_run(argv, *a, **k):
        raise subprocess.TimeoutExpired(argv, k.get("timeout", 1))

    monkeypatch.setattr(checks.subprocess, "run", fake_run)
    result, detail, remediation = checks.check_pyyaml(_profile(tmp_path))
    assert result is Result.FAIL
    assert hung in detail and remediation


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
    (home / ".claude" / "adlc").mkdir(parents=True)
    # A written config is what makes the missing parser a defect rather than a
    # non-event: the operator has said something the machine cannot read.
    (home / ".claude" / "adlc" / "config.yml").write_text("delegate:\n  enabled: false\n")
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


def test_doctor_skips_pyyaml_when_there_is_no_config_and_no_venv(tmp_path, repo_root):
    """The same bare machine with NOTHING written: pyyaml SKIPs, doctor is calm.

    Benign twin of the test above, and the reason the SKIP exists: a fresh
    machine that never opted into delegation and never wrote a config has no
    file for PyYAML to read, so a red row there is noise that teaches operators
    to ignore the verdict.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    env = dict(os.environ, HOME=str(home), PYTHONPATH=_poisoned_yaml(tmp_path))
    env.pop("ADLC_CONFIG", None)
    out = subprocess.run(
        [sys.executable, os.path.join(repo_root, "tools", "adlc", "adlc.py"),
         "doctor", "--checks", "pyyaml"],
        capture_output=True, text=True, cwd=str(workdir), env=env,
    )
    assert "Traceback" not in out.stderr, out.stderr
    rows = [ln for ln in out.stdout.splitlines() if " pyyaml " in ln]
    assert len(rows) == 1, out.stdout
    assert rows[0].startswith("[SKIP] pyyaml"), out.stdout
    assert out.returncode == 0, out.stdout


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
