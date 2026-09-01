"""REQ-603 TASK-089 — resolve_gate_verdict() and the --print-gate probe.

The probe is the single authority the shell gate defers to (BR-1). These cases
pin the two properties that are easy to lose: it shares the real call's
resolution (LESSON-392), and it REPORTS rather than refuses (BR-10).
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _common  # noqa: E402

_VARS = (
    "MOONSHOT_API_KEY", "KIMI_API_KEY", "ADLC_DELEGATE_MODEL",
    "ADLC_DELEGATE_BASE_URL", "ADLC_DELEGATE_API_KEY_ENV",
    "ADLC_DELEGATE_ENABLED", "ADLC_CONFIG", "ADLC_DISABLE_DELEGATE",
)
_CLI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adlc-read")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for v in _VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _cfg(tmp_path, body):
    p = tmp_path / "config.yml"
    p.write_text(body, encoding="utf-8")
    return str(p)


# --- BR-3: the probe reports verdict AND reason -----------------------------

def test_print_gate_emits_verdict_and_reason(clean_env, monkeypatch):
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test")
    assert _common.resolve_gate_verdict() == (True, "ok")


def test_print_enabled_output_unchanged(clean_env, monkeypatch):
    """BR-3 freezes the old flag. A caller written before REQ-603 still works."""
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test")
    out = subprocess.run([sys.executable, _CLI, "--print-enabled"],
                         capture_output=True, text=True, env={**os.environ})
    assert out.returncode == 0
    assert out.stdout.strip() == "1"


def test_print_enabled_against_frozen_caller(clean_env, monkeypatch):
    """The pre-REQ gate's contract: '1' or nothing, exit 0. Nothing else."""
    monkeypatch.setenv("ADLC_CONFIG", _cfg(clean_env, "delegate:\n  enabled: false\n"))
    out = subprocess.run([sys.executable, _CLI, "--print-enabled"],
                         capture_output=True, text=True, env={**os.environ})
    assert out.returncode == 0
    assert out.stdout.strip() in ("0", "")


# --- BR-6: the reason is always inside the frozen enum ----------------------

@pytest.mark.parametrize("env,cfg_body", [
    ({"ADLC_DISABLE_DELEGATE": "1"}, None),
    ({"ADLC_DELEGATE_ENABLED": "1", "MOONSHOT_API_KEY": "sk-t"}, None),
    ({}, "delegate:\n  enabled: false\n"),
    ({}, None),
    ({"MOONSHOT_API_KEY": "sk-t"}, "delegate:\n  enabled: false\n"),
])
def test_reason_always_within_enum(clean_env, monkeypatch, env, cfg_body):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    if cfg_body is not None:
        monkeypatch.setenv("ADLC_CONFIG", _cfg(clean_env, cfg_body))
    _, reason = _common.resolve_gate_verdict()
    assert reason in _common.GATE_REASONS
    # no-binary and unset are the gate's alone; the probe must never emit them.
    assert reason not in _common._GATE_ONLY_REASONS


# --- BR-10 / AC-12: the probe reports, it never refuses ---------------------

def test_probe_reports_disabled_never_refuses(clean_env, monkeypatch):
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    assert _common.resolve_gate_verdict() == (False, "disabled-via-env")


def test_probe_exits_zero_under_kill_switch(clean_env, monkeypatch):
    """The CLI path, not just the function: exit 0 with a verdict, no refusal."""
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    out = subprocess.run([sys.executable, _CLI, "--print-gate"],
                         capture_output=True, text=True, env={**os.environ})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "0 disabled-via-env"
    assert "refus" not in out.stderr.lower()


# --- BR-4 / ADR-4: the ratified reason correction ---------------------------

def test_enabled_false_without_legacy_key_is_disabled_via_config(clean_env, monkeypatch):
    """The one intentional divergence (ADR-4).

    The pre-REQ shell heuristic reported `not-opted-in` here, because it never
    read `enabled` — it checked only whether a config file existed AND a legacy
    key happened to be exported. Same written instruction, two labels.
    """
    monkeypatch.setenv("ADLC_CONFIG", _cfg(clean_env, "delegate:\n  enabled: false\n"))
    assert _common.resolve_gate_verdict() == (False, "disabled-via-config")


def test_enabled_false_with_legacy_key_is_also_disabled_via_config(clean_env, monkeypatch):
    """The other half of ADR-4: the label no longer depends on the key."""
    monkeypatch.setenv("ADLC_CONFIG", _cfg(clean_env, "delegate:\n  enabled: false\n"))
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    assert _common.resolve_gate_verdict() == (False, "disabled-via-config")


# --- LESSON-392: the probe shares the real call's resolution ----------------

def test_key_in_config_reports_disabled_not_opted_in(clean_env, monkeypatch):
    """A config the REAL call refuses must not report as enabled.

    This is LESSON-392's regression. `delegation_enabled()` alone answers "opted
    in?" and would say yes; only `resolve_provider()` knows the call would be
    refused. If this fails, the gate green-lights delegation that dies on the
    first API call, mislabelled as a runtime error.
    """
    monkeypatch.setenv("ADLC_CONFIG", _cfg(
        clean_env, "delegate:\n  enabled: true\n  api_key_env: sk-pasted-key-value\n"))
    enabled, reason = _common.resolve_gate_verdict()
    assert enabled is False
    assert reason == "disabled-via-config"


# --- AC-20: the frozen enum is what delegate-pre-pass receives --------------

def test_reason_stays_within_frozen_enum_for_pre_pass(clean_env, monkeypatch):
    """agents/delegate-pre-pass.md forwards gateReason verbatim, so every value
    the probe can emit must be inside the frozen six."""
    frozen = set(_common.GATE_REASONS) | set(_common._GATE_ONLY_REASONS)
    assert len(frozen) == 6
    for env in ({"ADLC_DISABLE_DELEGATE": "1"}, {"ADLC_DELEGATE_ENABLED": "1"}, {}):
        for v in _VARS:
            monkeypatch.delenv(v, raising=False)
        for k, val in env.items():
            monkeypatch.setenv(k, val)
        _, reason = _common.resolve_gate_verdict()
        assert reason in frozen


# --- BUG-056 / LESSON-022: imports stay lazy -------------------------------

def test_probe_runs_without_the_sdk(clean_env, monkeypatch):
    """--print-gate is a pre-API guard and must run with no openai installed."""
    env = {**os.environ, "PYTHONPATH": ""}
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.modules['openai']=None; "
         f"sys.path.insert(0,{os.path.dirname(_CLI)!r}); "
         "import _common; print(_common.resolve_gate_verdict()[1])"],
        capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() in _common.GATE_REASONS


# --- adlc-write --print-gate: previously ZERO coverage at any level ---------
_CLI_WRITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adlc-write")


def test_adlc_write_print_gate_reports(clean_env, monkeypatch):
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-t")
    out = subprocess.run([sys.executable, _CLI_WRITE, "--print-gate"],
                         capture_output=True, text=True, env={**os.environ})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "1 ok"


def test_adlc_write_print_gate_not_hijacked_from_value_position(clean_env, monkeypatch):
    """The `--sp "--version"` hijack class, for --print-gate.

    A bare `"--print-gate" in argv` also matched VALUE positions, so this argv
    printed the verdict and exited 0 instead of reaching argparse's error.
    """
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    out = subprocess.run(
        [sys.executable, _CLI_WRITE, "--spec", "--print-gate", "--target", "/tmp/adlc-no-write.txt"],
        capture_output=True, text=True, env={**os.environ})
    assert out.returncode != 0, f"argv was hijacked: {out.stdout!r}"
    assert "1 ok" not in out.stdout
    assert not os.path.exists("/tmp/adlc-no-write.txt")


# --- AC-19 / AC-21: the EXHAUSTIVE matrix -----------------------------------
# Its absence is why the BR-2 precedence inversion shipped: every individual row
# was spot-checked, and the one combination that mattered — env opt-in WITH
# `enabled: false` — was covered by nothing. A per-arm enumeration that sets each
# arm in isolation cannot catch a precedence bug, because precedence only exists
# between arms.

_MATRIX = [
    # (veto, env_optin, config, legacy_key) -> (enabled, reason)
    ((False, False, None,    False), (False, "not-opted-in")),
    ((False, False, None,    True),  (True,  "ok")),
    ((False, True,  None,    False), (True,  "ok")),
    ((False, True,  None,    True),  (True,  "ok")),
    ((False, False, "true",  False), (True,  "ok")),
    ((False, False, "true",  True),  (True,  "ok")),
    ((False, False, "false", False), (False, "disabled-via-config")),
    ((False, False, "false", True),  (False, "disabled-via-config")),
    # THE ROW THAT REGRESSED. The pre-REQ gate returned 0 ok here: env opt-in is
    # rank 1 and outranks a config `false` at rank 2. A version of
    # resolve_gate_verdict that checked config first inverted this, and the gate
    # refused while a direct CLI call still transmitted.
    ((False, True,  "false", False), (True,  "ok")),
    ((False, True,  "false", True),  (True,  "ok")),
    # The veto outranks everything, on every combination.
    ((True,  False, None,    False), (False, "disabled-via-env")),
    ((True,  True,  "true",  True),  (False, "disabled-via-env")),
    ((True,  True,  "false", True),  (False, "disabled-via-env")),
]


@pytest.mark.parametrize("inputs,expected", _MATRIX,
                         ids=lambda v: str(v) if isinstance(v, tuple) else str(v))
def test_full_verdict_matrix(inputs, expected, clean_env, monkeypatch):
    veto, env_optin, config, legacy = inputs
    monkeypatch.setenv("ADLC_DELEGATE_API_KEY_ENV", "MY_PROVIDER_KEY")
    monkeypatch.setenv("MY_PROVIDER_KEY", "sk-resolvable")
    if veto:
        monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    if env_optin:
        monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    if config is not None:
        monkeypatch.setenv("ADLC_CONFIG", _cfg(clean_env, f"delegate:\n  enabled: {config}\n"))
    if legacy:
        monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    assert _common.resolve_gate_verdict() == expected


def test_matrix_and_delegation_enabled_never_disagree(clean_env, monkeypatch):
    """The invariant the whole REQ rests on: the gate's verdict and the predicate
    that guards transmission must agree on every row. They diverged once."""
    for (veto, env_optin, config, legacy), (expected_enabled, _) in _MATRIX:
        for v in _VARS:
            monkeypatch.delenv(v, raising=False)
        monkeypatch.setenv("HOME", str(clean_env))
        monkeypatch.setenv("ADLC_DELEGATE_API_KEY_ENV", "MY_PROVIDER_KEY")
        monkeypatch.setenv("MY_PROVIDER_KEY", "sk-resolvable")
        if veto: monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
        if env_optin: monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
        if config is not None:
            monkeypatch.setenv("ADLC_CONFIG", _cfg(clean_env, f"delegate:\n  enabled: {config}\n"))
        if legacy: monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
        gate_enabled, _ = _common.resolve_gate_verdict()
        assert gate_enabled == _common.delegation_enabled(), (
            f"gate and delegation_enabled disagree for "
            f"veto={veto} env={env_optin} config={config} legacy={legacy}: "
            f"gate={gate_enabled} predicate={_common.delegation_enabled()}")
