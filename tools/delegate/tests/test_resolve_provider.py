"""REQ-515: provider-resolution cascade, config parsing, key-in-config refusal,
and BR-11 opt-in posture in _common.resolve_provider / delegation_enabled.

These tests touch no network — resolve_provider() is pure resolution logic.
Each test isolates the environment (monkeypatch clears all delegate/legacy vars)
so a developer's real shell env cannot leak in.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import _common  # noqa: E402

_DELEGATE_VARS = (
    "MOONSHOT_API_KEY", "KIMI_API_KEY", "KIMI_MODEL",
    "ADLC_DELEGATE_MODEL", "ADLC_DELEGATE_BASE_URL", "ADLC_DELEGATE_API_KEY_ENV",
    "ADLC_DELEGATE_ENABLED", "ADLC_CONFIG",
)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Clear every delegate/legacy var and point HOME at an empty tmp dir
    (so the default ~/.claude/adlc/config.yml does not exist)."""
    for v in _DELEGATE_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _write_config(tmp_path, body):
    cfg = tmp_path / "config.yml"
    cfg.write_text(body, encoding="utf-8")
    return str(cfg)


# --- defaults / byte-identical legacy behavior -----------------------------

def test_defaults_match_shipped_moonshot(clean_env):
    p = _common.resolve_provider()
    assert p.base_url == "https://api.moonshot.ai/v1"
    assert p.model == "kimi-k2.5"
    assert p.api_key_env == "MOONSHOT_API_KEY"


def test_no_config_legacy_key_is_enabled(clean_env, monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    p = _common.resolve_provider()
    assert p.enabled is True
    assert p.model == "kimi-k2.5"


# --- BR-2 precedence cascade ------------------------------------------------

def test_precedence_flag_beats_env_beats_config(clean_env, monkeypatch):
    cfg = _write_config(clean_env, "delegate:\n  enabled: true\n  model: cfg-model\n")
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    assert _common.resolve_provider().model == "cfg-model"
    monkeypatch.setenv("ADLC_DELEGATE_MODEL", "env-model")
    assert _common.resolve_provider().model == "env-model"
    assert _common.resolve_provider(args_model="flag-model").model == "flag-model"


def test_legacy_kimi_model_env_is_no_longer_read(clean_env, monkeypatch):
    """REQ-522 ADR-5: the legacy KIMI_MODEL env read is dropped — it was a
    branded non-key env var, not key continuity. Setting it must have NO effect;
    the shipped default model wins (use ADLC_DELEGATE_MODEL instead)."""
    monkeypatch.setenv("KIMI_MODEL", "legacy-model")
    # KIMI_MODEL is ignored → falls through to the shipped default.
    assert _common.resolve_provider().model == _common._DEFAULT_MODEL
    # ADLC_DELEGATE_MODEL is the supported override.
    monkeypatch.setenv("ADLC_DELEGATE_MODEL", "env-model")
    assert _common.resolve_provider().model == "env-model"


def test_base_url_and_api_key_env_from_config(clean_env, monkeypatch):
    cfg = _write_config(
        clean_env,
        'delegate:\n  enabled: true\n  base_url: "https://groq/v1"\n  api_key_env: "GROQ_API_KEY"\n',
    )
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    p = _common.resolve_provider()
    assert p.base_url == "https://groq/v1"
    assert p.api_key_env == "GROQ_API_KEY"


# --- BR-3 key-in-config refusal --------------------------------------------

@pytest.mark.parametrize("bad", [
    "sk-abcdefghijklmnopqrstuvwxyz0123",          # sk- key family
    "AKIAABCDEFGHIJKLMNOP",                       # AWS key
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",   # github token
    "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7",         # long mixed-class run
    "not a var name",                             # has spaces
])
def test_key_in_config_refused(clean_env, monkeypatch, bad):
    cfg = _write_config(clean_env, f'delegate:\n  api_key_env: "{bad}"\n')
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    with pytest.raises(SystemExit) as exc:
        _common.resolve_provider()
    assert "NAME" in str(exc.value)


def test_valid_env_var_name_accepted(clean_env, monkeypatch):
    cfg = _write_config(clean_env, 'delegate:\n  api_key_env: "MY_PROVIDER_KEY"\n')
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    assert _common.resolve_provider().api_key_env == "MY_PROVIDER_KEY"


# --- BR-11 opt-in posture ---------------------------------------------------

def test_fresh_install_disabled_by_default(clean_env):
    """Config present but no enabled:true, no legacy key → disabled."""
    cfg = _write_config(clean_env, 'delegate:\n  base_url: "https://x/v1"\n  model: m\n')
    os.environ["ADLC_CONFIG"] = cfg
    try:
        assert _common.resolve_provider().enabled is False
    finally:
        del os.environ["ADLC_CONFIG"]


def test_config_enabled_true_opts_in(clean_env, monkeypatch):
    cfg = _write_config(clean_env, "delegate:\n  enabled: true\n")
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    assert _common.resolve_provider().enabled is True


def test_env_base_model_alone_is_not_opt_in(clean_env, monkeypatch):
    monkeypatch.setenv("ADLC_DELEGATE_BASE_URL", "https://x/v1")
    monkeypatch.setenv("ADLC_DELEGATE_MODEL", "m")
    assert _common.resolve_provider().enabled is False


def test_delegate_enabled_env_opts_in(clean_env, monkeypatch):
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    assert _common.resolve_provider().enabled is True


# --- --print-enabled gate probe (used by delegate-gate.sh) ------------------

def _print_enabled(env_overrides, tmp_home):
    """Invoke `adlc-read --print-enabled` in a clean subprocess env."""
    import subprocess
    env = {"HOME": str(tmp_home), "PATH": os.environ.get("PATH", "")}
    env.update(env_overrides)
    adlc_read = os.path.join(os.path.dirname(HERE), "adlc-read")
    r = subprocess.run([sys.executable, adlc_read, "--print-enabled"],
                       capture_output=True, text=True, env=env)
    return r


def test_print_enabled_reports_zero_for_key_in_config(clean_env):
    """BR-3 x BR-11: a config opted-in (enabled:true) but with a KEY value in
    api_key_env must report 0 — the gate must not green-light a config that would
    fail loudly on the first real call."""
    cfg = _write_config(clean_env, 'delegate:\n  enabled: true\n  api_key_env: "sk-abcdefghijklmnop0123456789"\n')
    r = _print_enabled({"ADLC_CONFIG": cfg}, clean_env)
    assert r.returncode == 0
    assert r.stdout.strip() == "0", r.stdout + r.stderr


def test_print_enabled_reports_one_for_valid_opt_in(clean_env):
    r = _print_enabled({"ADLC_DELEGATE_ENABLED": "1"}, clean_env)
    assert r.returncode == 0
    assert r.stdout.strip() == "1", r.stdout + r.stderr


def test_print_enabled_reports_zero_fresh_install(clean_env):
    r = _print_enabled({}, clean_env)
    assert r.returncode == 0
    assert r.stdout.strip() == "0", r.stdout + r.stderr
