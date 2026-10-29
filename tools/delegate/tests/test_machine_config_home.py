"""REQ-654 BR-1/BR-2: the ``_machine_config`` mirror of the ADLC_HOME rule.

The rule itself is pinned across all three implementations by
``tools/adlc/tests/test_adlc_home.py``; this file covers what only the delegation
side does with it: ``default_config_path`` builds on the home, and an unusable
home is a ``home-invalid`` refusal that fails closed, through the loader and
through ``parse_delegate_config``, instead of raising or falling through to the
default.
"""

import os

import pytest

import _common
import _machine_config


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    for var in ("ADLC_HOME", "ADLC_CONFIG", "ADLC_DELEGATE_ENABLED",
                "ADLC_DISABLE_DELEGATE", "KIMI_API_KEY", "MOONSHOT_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_default_home_is_todays_path(sandbox):
    assert _machine_config.adlc_home() == os.path.join(str(sandbox), ".claude")
    assert _machine_config.default_config_path() == os.path.join(
        str(sandbox), ".claude", "adlc", "config.yml")


def test_override_home_moves_the_config(sandbox, monkeypatch):
    alt = sandbox / "alt home"
    monkeypatch.setenv("ADLC_HOME", str(alt))
    assert _machine_config.default_config_path() == os.path.join(
        str(alt), "adlc", "config.yml")
    (alt / "adlc").mkdir(parents=True)
    (alt / "adlc" / "config.yml").write_text("delegate:\n  enabled: false\n")
    outcome = _machine_config.load_machine_config()
    assert outcome.kind == _machine_config.KIND_PARSED
    assert outcome.path == os.path.join(str(alt), "adlc", "config.yml")


def test_adlc_config_outranks_an_invalid_home(sandbox, monkeypatch):
    cfg = sandbox / "explicit.yml"
    cfg.write_text("delegate:\n  enabled: false\n")
    monkeypatch.setenv("ADLC_HOME", "relative/home")
    monkeypatch.setenv("ADLC_CONFIG", str(cfg))
    assert _machine_config.default_config_path() == str(cfg)
    assert _machine_config.load_machine_config().kind == _machine_config.KIND_PARSED


@pytest.mark.parametrize("bad", ["", "relative/home", "./x", "~/x"])
def test_invalid_home_is_a_home_invalid_refusal(sandbox, monkeypatch, bad):
    monkeypatch.setenv("ADLC_HOME", bad)
    with pytest.raises(_machine_config.AdlcHomeError, match="ADLC_HOME"):
        _machine_config.default_config_path()
    outcome = _machine_config.load_machine_config()
    assert outcome.kind == _machine_config.KIND_MALFORMED
    assert outcome.reason_class == "home-invalid"
    assert outcome.reason_class in _machine_config.REASON_CLASSES
    assert "ADLC_HOME" in outcome.reason
    assert outcome.path == _machine_config.HOME_INVALID_PATH


def test_invalid_home_never_reads_the_default_file(sandbox, monkeypatch):
    """The benign default file exists and says enabled: true; an invalid home
    must still refuse rather than fall through to it (BR-2)."""
    default = sandbox / ".claude" / "adlc"
    default.mkdir(parents=True)
    (default / "config.yml").write_text("delegate:\n  enabled: true\n")
    monkeypatch.setenv("ADLC_HOME", "relative/home")
    cfg = _common.parse_delegate_config()
    assert cfg.get(_common._MALFORMED) is True
    assert cfg.get(_common._MALFORMED_REASON, "").startswith("home-invalid:")


def test_refusal_message_names_the_variable_not_the_default(sandbox, monkeypatch):
    monkeypatch.setenv("ADLC_HOME", "relative/home")
    assert _common._config_path_label() == "$ADLC_HOME/adlc/config.yml"
    monkeypatch.delenv("ADLC_HOME")
    assert _common._config_path_label() == os.path.join(
        str(sandbox), ".claude", "adlc", "config.yml")


# --- tools/delegate/install.sh (REQ-654 BR-1, BR-2) -------------------------

_INSTALL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "install.sh")


@pytest.mark.parametrize("bad", ["", "relative/home"])
def test_installer_refuses_an_unusable_home_before_any_change(tmp_path, bad):
    """The delegation installer resolves ADLC_HOME before its first mutation
    (LESSON-017): an unusable value exits non-zero, names it, and creates
    nothing under HOME — no venv, no CLAUDE.md, no settings.json."""
    import subprocess
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "ADLC_HOME": bad}
    out = subprocess.run(["sh", _INSTALL], env=env, capture_output=True, text=True,
                         timeout=60)
    assert out.returncode != 0
    assert "ADLC_HOME" in out.stderr
    assert os.listdir(home) == []


def test_launchctl_helper_path_is_under_adlc_home():
    """The LaunchAgent template names the helper through __ADLC_HOME__, and the
    installer substitutes it with the resolved home (the helper is written there)."""
    here = os.path.dirname(_INSTALL)
    with open(os.path.join(here, "com.adlc-toolkit.delegate-setenv.plist.in")) as fh:
        plist = fh.read()
    assert "__ADLC_HOME__/delegate-launchctl-setenv.sh" in plist
    assert "__HOME__/.claude" not in plist
    with open(_INSTALL) as fh:
        text = fh.read()
    assert 'AGENT_HELPER="$ADLC_HOME_DIR/delegate-launchctl-setenv.sh"' in text
    assert 's|__ADLC_HOME__|$ADLC_HOME_DIR|g' in text
