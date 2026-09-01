"""REQ-515: provider-resolution cascade, config parsing, key-in-config refusal,
and BR-11 opt-in posture in _common.resolve_provider / delegation_enabled.

These tests touch no network — resolve_provider() is pure resolution logic.
Each test isolates the environment (monkeypatch clears all delegate/legacy vars)
so a developer's real shell env cannot leak in.
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import _common  # noqa: E402

_DELEGATE_VARS = (
    "MOONSHOT_API_KEY", "KIMI_API_KEY", "KIMI_MODEL",
    "ADLC_DELEGATE_MODEL", "ADLC_DELEGATE_BASE_URL", "ADLC_DELEGATE_API_KEY_ENV",
    "ADLC_DELEGATE_ENABLED", "ADLC_CONFIG", "ADLC_DISABLE_DELEGATE",
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
    assert p.model == "kimi-k2.6"
    assert p.api_key_env == "MOONSHOT_API_KEY"


def test_no_config_legacy_key_is_enabled(clean_env, monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    p = _common.resolve_provider()
    assert p.enabled is True
    assert p.model == "kimi-k2.6"


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


# --- BUG-205: an explicit `enabled: false` outranks legacy key continuity ----
#
# The regression these pin: `enabled` used to be a flat OR in which the
# legacy-key arm was tested BEFORE the config file, so a `MOONSHOT_API_KEY` left
# in the environment silently re-enabled delegation on a machine whose config
# said `false`. Since REQ-519 `install.sh` scaffolds exactly that line, so this
# was the default posture of every install with a key exported.
#
# The distinction under test is absent-vs-false. Both were previously collapsed
# to "not true"; only `false` is an operator instruction.

def test_config_enabled_false_beats_legacy_key(clean_env, monkeypatch):
    """The BUG-205 case itself: written `false` + legacy key → DISABLED."""
    cfg = _write_config(clean_env, "delegate:\n  enabled: false\n")
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    assert _common.resolve_provider().enabled is False


def test_config_enabled_false_beats_legacy_kimi_key(clean_env, monkeypatch):
    """Both legacy key names are covered — KIMI_API_KEY is the older alias."""
    cfg = _write_config(clean_env, "delegate:\n  enabled: false\n")
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    monkeypatch.setenv("KIMI_API_KEY", "sk-legacy")
    assert _common.resolve_provider().enabled is False


def test_absent_enabled_still_yields_to_legacy_key(clean_env, monkeypatch):
    """The other side of the fix, and the one BR-11 actually wrote the
    continuity exception for: `enabled` ABSENT (not false) + legacy key stays
    ENABLED. Absence is a default and yields; a written `false` does not.

    If this flips, the fix has over-reached and broken pre-config installs."""
    cfg = _write_config(clean_env, 'delegate:\n  model: cfg-model\n')
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    assert _common.resolve_provider().enabled is True


def test_env_opt_in_still_outranks_config_false(clean_env, monkeypatch):
    """ADLC_DELEGATE_ENABLED is rank 2 and the config file rank 3, so an
    explicit env opt-in deliberately overrides `enabled: false`. This is the
    documented escape hatch, not a leak — the fix must not swallow it."""
    cfg = _write_config(clean_env, "delegate:\n  enabled: false\n")
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    assert _common.resolve_provider().enabled is True


def test_print_enabled_reports_zero_for_config_false_with_key(clean_env):
    """The shell gate reads `--print-enabled`, so the CLI must agree with
    delegation_enabled() on the BUG-205 case or the two surfaces skew."""
    cfg = _write_config(clean_env, "delegate:\n  enabled: false\n")
    r = _print_enabled({"ADLC_CONFIG": cfg, "MOONSHOT_API_KEY": "sk-legacy"}, clean_env)
    assert r.stdout.strip() == "0"


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


# --- BUG-206: the CLIs enforce `enabled` themselves --------------------------
#
# Before this guard, `enabled` was consulted ONLY by `--print-enabled`. The flag
# governing whether file contents may leave the machine was read exclusively by
# the probe, never by the code path that does the leaving — so the shell gate was
# the sole enforcement. That gate is vendored per repo, so a stale vendored copy
# called straight through a correct opt-out with nothing downstream objecting.

def _run_cli(tool, args, env_overrides, tmp_home):
    """Invoke a delegate CLI in a clean subprocess env."""
    env = dict(os.environ)
    for v in _DELEGATE_VARS:
        env.pop(v, None)
    env["HOME"] = str(tmp_home)
    env.update(env_overrides)
    return subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), tool)] + args,
                          capture_output=True, text=True, env=env)


def test_adlc_read_refuses_to_transmit_when_disabled(clean_env, tmp_path):
    """The BUG-206 case: config says false, a legacy key is set, and the caller
    invokes the real read path anyway (as a stale vendored gate would)."""
    cfg = _write_config(clean_env, "delegate:\n  enabled: false\n")
    src = tmp_path / "f.md"; src.write_text("secret contents", encoding="utf-8")
    r = _run_cli("adlc-read", ["--paths", str(src), "--question", "q"],
                 {"ADLC_CONFIG": cfg, "MOONSHOT_API_KEY": "sk-legacy"}, clean_env)
    assert r.returncode != 0, "a disabled CLI must fail, so callers fall back"
    assert "not enabled" in r.stderr
    assert "secret contents" not in r.stdout


def test_adlc_write_refuses_and_writes_no_target_when_disabled(clean_env, tmp_path):
    cfg = _write_config(clean_env, "delegate:\n  enabled: false\n")
    target = tmp_path / "out.md"
    r = _run_cli("adlc-write", ["--spec", "s", "--target", str(target)],
                 {"ADLC_CONFIG": cfg, "MOONSHOT_API_KEY": "sk-legacy"}, clean_env)
    assert r.returncode != 0
    assert "not enabled" in r.stderr
    assert not target.exists(), "a refused run must leave no partial artifact"


def test_guard_fires_before_any_network_touch(clean_env, tmp_path):
    """Point the endpoint at an unroutable address. If the guard ran after the
    client were built, this would hang or emit a connection error instead."""
    cfg = _write_config(clean_env, "delegate:\n  enabled: false\n")
    src = tmp_path / "f.md"; src.write_text("x", encoding="utf-8")
    r = _run_cli("adlc-read",
                 ["--base-url", "https://10.255.255.1/v1", "--paths", str(src), "--question", "q"],
                 {"ADLC_CONFIG": cfg, "MOONSHOT_API_KEY": "sk-legacy"}, clean_env)
    assert r.returncode != 0
    assert "not enabled" in r.stderr
    assert "onnect" not in r.stderr, "should never have reached the network"


def test_dry_run_still_works_while_disabled(clean_env, tmp_path):
    """A dry run packs the corpus locally and sends nothing, so it stays
    available for debugging while delegation is off."""
    cfg = _write_config(clean_env, "delegate:\n  enabled: false\n")
    src = tmp_path / "f.md"; src.write_text("x", encoding="utf-8")
    r = _run_cli("adlc-read", ["--dry-run", "--paths", str(src), "--question", "q"],
                 {"ADLC_CONFIG": cfg, "MOONSHOT_API_KEY": "sk-legacy"}, clean_env)
    assert r.returncode == 0, r.stderr
    assert "not enabled" not in r.stderr


def test_probes_still_work_while_disabled(clean_env):
    """--print-enabled and --version are how an operator INSPECTS a disabled
    setup; the guard must not break the tools used to diagnose it."""
    cfg = _write_config(clean_env, "delegate:\n  enabled: false\n")
    env = {"ADLC_CONFIG": cfg, "MOONSHOT_API_KEY": "sk-legacy"}
    assert _run_cli("adlc-read", ["--print-enabled"], env, clean_env).stdout.strip() == "0"
    v = _run_cli("adlc-read", ["--version"], env, clean_env)
    assert v.returncode == 0 and "enabled: false" in v.stdout


def test_enabled_run_is_not_blocked_by_the_guard(clean_env, tmp_path):
    """The guard must not become a second opt-out. With delegation properly
    enabled it steps aside — the run proceeds past it and fails later at the
    network/auth layer, not at the guard."""
    src = tmp_path / "f.md"; src.write_text("x", encoding="utf-8")
    r = _run_cli("adlc-read",
                 ["--no-warn", "--base-url", "https://10.255.255.1/v1",
                  "--paths", str(src), "--question", "q"],
                 {"ADLC_DELEGATE_ENABLED": "1", "MOONSHOT_API_KEY": "sk-fake"}, clean_env)
    assert "not enabled" not in r.stderr, "guard must not block an opted-in run"


# --- BUG-209: ADLC_DISABLE_DELEGATE is the kill switch, honoured in Python ---
# The shell gate has covered this since it was written
# (partials/tests/delegate-gate.test.sh: "ADLC_DISABLE_DELEGATE=1 beats
# everything"). The CLI side had no equivalent, so delegation_enabled() never
# read the variable at all and every direct CLI call ignored a documented
# emergency stop. These are the missing half.

def test_disable_beats_enabled_env(clean_env, monkeypatch):
    """The kill switch outranks the opt-in env var (README: 'overriding
    everything including ADLC_DELEGATE_ENABLED=1')."""
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    assert _common.delegation_enabled() is False


def test_disable_beats_config_true(clean_env, monkeypatch):
    cfg = _write_config(clean_env, "delegate:\n  enabled: true\n")
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    assert _common.delegation_enabled() is True
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    assert _common.delegation_enabled() is False


def test_disable_beats_legacy_key(clean_env, monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    assert _common.delegation_enabled() is True
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    assert _common.delegation_enabled() is False


def test_disable_beats_everything_at_once(clean_env, monkeypatch):
    """Every opt-in arm asserted simultaneously — mirrors the shell gate's
    'beats everything' case so the two layers are tested on equal terms."""
    cfg = _write_config(clean_env, "delegate:\n  enabled: true\n")
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    assert _common.delegation_enabled() is False


def test_disable_requires_exactly_one(clean_env, monkeypatch):
    """Only the literal "1" disables, matching delegate-gate.sh's
    `[ "${ADLC_DISABLE_DELEGATE:-0}" = "1" ]`. A truthy-looking value that the
    shell would ignore must not disable here either, or the layers disagree."""
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    for value in ("0", "", "true", "yes", "2"):
        monkeypatch.setenv("ADLC_DISABLE_DELEGATE", value)
        assert _common.delegation_enabled() is True, value


def test_disable_reflected_in_resolved_provider(clean_env, monkeypatch):
    """--version / --print-enabled read through resolve_provider, so the switch
    must show there too — that report is the documented way to check what a
    machine will actually do."""
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    assert _common.resolve_provider().enabled is False


def test_require_delegation_names_the_kill_switch(clean_env, monkeypatch):
    """A refusal caused by the switch must say so rather than advising the
    operator to enable delegation they deliberately turned off."""
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    with pytest.raises(SystemExit) as exc:
        _common.require_delegation_enabled("adlc-read")
    msg = str(exc.value)
    assert "ADLC_DISABLE_DELEGATE" in msg
    assert "delegate.enabled: true" not in msg


# --- REQ-603 TASK-091: cascade coverage relocated from the shell harness ----
# These assert WHICH ARM WINS. They live here, not in
# partials/tests/delegate-gate.test.sh, because the gate no longer decides —
# it dispatches. Keeping them in shell would preserve the exact condition
# REQ-603 removes: a green shell assertion standing in for coverage of the real
# resolver, which is how BUG-209 survived.

def test_gate_verdict_enabled_false_plus_legacy_key(clean_env, monkeypatch):
    """AC-7 / BUG-205's case. An explicit `false` outranks key continuity."""
    cfg = _write_config(clean_env, "delegate:\n  enabled: false\n")
    monkeypatch.setenv("ADLC_CONFIG", cfg)
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    assert _common.resolve_gate_verdict() == (False, "disabled-via-config")


def test_gate_verdict_no_config_plus_legacy_key(clean_env, monkeypatch):
    """AC-8 / REQ-515 BR-11 continuity, reached only when NO config file exists."""
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    enabled, reason = _common.resolve_gate_verdict()
    assert (enabled, reason) == (True, "ok")


def test_gate_verdict_no_config_no_key_is_not_opted_in(clean_env):
    """BR-11 fresh-install posture: delegation is OFF by default."""
    assert _common.resolve_gate_verdict() == (False, "not-opted-in")


def test_removing_env_arm_changes_gate_verdict(clean_env, monkeypatch):
    """AC-5. An install whose ONLY opt-in signal is ADLC_DELEGATE_ENABLED.

    Revert method (BR-9): delete the `ADLC_DELEGATE_ENABLED` arm from
    delegation_enabled() and this fails — proving the gate no longer decides it
    and that the arm is genuinely load-bearing rather than shadowed by another.
    """
    # A legacy key must NOT be set here: it is the arm that shadows this one, and
    # its presence made the original version of this test pass with the env arm
    # deleted — the opposite of what its docstring claimed. The key is supplied
    # via a custom api_key_env so resolve_key succeeds without a legacy key
    # satisfying the opt-in cascade.
    monkeypatch.setenv("ADLC_DELEGATE_API_KEY_ENV", "MY_PROVIDER_KEY")
    monkeypatch.setenv("MY_PROVIDER_KEY", "sk-t")
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    assert _common.resolve_gate_verdict() == (True, "ok")
    # ...and with the ONLY opt-in signal removed, the same install is off.
    monkeypatch.delenv("ADLC_DELEGATE_ENABLED")
    assert _common.resolve_gate_verdict()[0] is False


def test_removing_veto_stops_cli_refusing(clean_env, monkeypatch):
    """AC-6 — the BUG-209 regression, asserted WITHOUT transmitting.

    The criterion is the guard's refusal, not an actual transmission. Verifying
    "it would transmit" by transmitting would put the governance violation inside
    the suite that exists to prevent it, and would break the hermetic-test
    posture besides (that was /validate W-1 on this REQ).

    Revert method: delete the veto arm from delegation_enabled() and
    require_delegation_enabled() stops raising here, while the shell gate's own
    veto still holds — each layer's responsibility asserted in its own suite.
    """
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    with pytest.raises(SystemExit) as exc:
        _common.require_delegation_enabled("adlc-read")
    assert "ADLC_DISABLE_DELEGATE" in str(exc.value)


def test_per_arm_revert_enumeration(clean_env, monkeypatch):
    """AC-14 / BR-9. Each of the four arms is independently load-bearing.

    Enumerated rather than asserted in aggregate: a single "coverage did not
    decrease" claim is unmeasurable, which is what /validate W-2 flagged. Each
    row below is an input that ONLY that arm can decide, so deleting the arm
    changes this result.
    """
    results = {}

    # A key must be resolvable, or LESSON-392's resolve_key half correctly
    # reports disabled for every row regardless of the arm under test.
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-t")
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    results["veto"] = _common.resolve_gate_verdict()
    monkeypatch.delenv("ADLC_DISABLE_DELEGATE")

    results["env-opt-in"] = _common.resolve_gate_verdict()
    monkeypatch.delenv("ADLC_DELEGATE_ENABLED")

    monkeypatch.setenv("ADLC_CONFIG", _write_config(clean_env, "delegate:\n  enabled: false\n"))
    results["config"] = _common.resolve_gate_verdict()
    monkeypatch.delenv("ADLC_CONFIG")

    results["legacy-key"] = _common.resolve_gate_verdict()

    assert results == {
        "veto": (False, "disabled-via-env"),
        "env-opt-in": (True, "ok"),
        "config": (False, "disabled-via-config"),
        "legacy-key": (True, "ok"),
    }


def test_covered_arm_reports_no_false_gap(clean_env, monkeypatch):
    """BR-9 benign path. A correctly-covered arm must not report as a gap.

    A coverage check that flags everything is indistinguishable from one that
    works, and would train the next reader to ignore it.
    """
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-t")
    enabled, reason = _common.resolve_gate_verdict()
    assert enabled is True and reason == "ok"
