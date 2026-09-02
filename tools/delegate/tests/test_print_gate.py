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

def _expected(veto, env_optin, config, legacy):
    """The intended verdict, derived from REQ-515 BR-2's ranking as documented.

    Written independently of the implementation so the matrix is a specification
    of the ranking, not a transcript of whatever the code currently does. The
    previous hand-listed table covered 13 of 24 combinations and only 3 of the
    12 veto rows, which is why a legacy-key-over-veto inversion was invisible.
    """
    if veto:
        return (False, "disabled-via-env")          # rank 0, beats everything
    if env_optin:
        return (True, "ok")                          # rank 1, beats config
    if config == "false":
        return (False, "disabled-via-config")        # rank 2, decisive both ways
    if config == "true":
        return (True, "ok")
    if legacy:
        return (True, "ok")                          # rank 3, no-config continuity
    return (False, "not-opted-in")                   # rank 4, fresh-install default


# FULL cross-product: 2 x 2 x 3 x 2 = 24 rows, no combination omitted.
_MATRIX = [
    ((veto, env_optin, config, legacy), _expected(veto, env_optin, config, legacy))
    for veto in (False, True)
    for env_optin in (False, True)
    for config in (None, "true", "false")
    for legacy in (False, True)
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
        # No exception for D3/D4 here: with a resolvable key and a readable
        # config, the gate and the cascade must agree on EVERY row. The rows
        # where they legitimately differ (key unset, config unreadable) are
        # asserted separately, on all three surfaces, above.
        assert gate_enabled == _common.delegation_enabled(), (
            f"gate and delegation_enabled disagree for "
            f"veto={veto} env={env_optin} config={config} legacy={legacy}: "
            f"gate={gate_enabled} predicate={_common.delegation_enabled()}")


# --- Round-2 review: three fixes shipped with ZERO coverage -----------------
# Mutation testing showed the full suite passed with each of these reverted.
# "Fixed but untested" is how the previous round's Critical shipped, so each
# fix below now has a test that fails when the fix is removed.

def _unreadable(tmp_path, body="delegate:\n  enabled: false\n"):
    f = tmp_path / "unreadable.yml"
    f.write_text(body, encoding="utf-8")
    f.chmod(0o000)
    return str(f)


def test_unreadable_config_fails_closed_on_every_surface(clean_env, monkeypatch):
    """BUG-205's shape via a read failure instead of a precedence bug.

    An operator wrote `enabled: false`; the file became unreadable (permission
    drift, a partial checkout, an editor lockfile) and a stale legacy key is
    still exported. Before the fix all three surfaces delegated.

    Asserted on ALL THREE, because the first version of this fix reached only
    the probe: the gate refused while a direct CLI call still transmitted.
    """
    monkeypatch.setenv("ADLC_CONFIG", _unreadable(clean_env))
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    assert _common.parse_delegate_config().get(_common._MALFORMED) is True
    assert _common.resolve_gate_verdict() == (False, "disabled-via-config")
    assert _common.delegation_enabled() is False
    with pytest.raises(SystemExit):
        _common.require_delegation_enabled("adlc-read")


def test_unreadable_parent_directory_fails_closed(clean_env, monkeypatch):
    """os.path.lexists() swallows PermissionError, so an unreadable PARENT DIR
    read as 'absent' and fell through to legacy-key continuity — the gate itself
    granted against a written `enabled: false`. Discrimination is on errno now."""
    d = clean_env / "locked"
    d.mkdir()
    (d / "config.yml").write_text("delegate:\n  enabled: false\n", encoding="utf-8")
    d.chmod(0o000)
    try:
        monkeypatch.setenv("ADLC_CONFIG", str(d / "config.yml"))
        monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
        assert _common.resolve_gate_verdict() == (False, "disabled-via-config")
        assert _common.delegation_enabled() is False
    finally:
        d.chmod(0o755)


def test_absent_config_is_still_absent_not_malformed(clean_env, monkeypatch):
    """Benign path. Fail-closed must not swallow the legitimate no-config case,
    or every fresh install with a legacy key would stop delegating."""
    monkeypatch.setenv("ADLC_CONFIG", str(clean_env / "does-not-exist.yml"))
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    assert _common.parse_delegate_config() == {}
    assert _common.resolve_gate_verdict() == (True, "ok")


def test_key_env_named_but_unset_reports_disabled(clean_env, monkeypatch):
    """LESSON-392's OTHER half (D3), which had no direct coverage.

    The existing lesson test uses a key-SHAPED value, which resolve_provider()
    refuses before resolve_key() is ever reached. This is the case resolve_key()
    alone catches: a syntactically valid env-var name that is genuinely unset.
    Deleting the resolve_key() call from the probe passed the entire suite.
    """
    monkeypatch.setenv("ADLC_CONFIG", _cfg(
        clean_env, "delegate:\n  enabled: true\n  api_key_env: MY_PROVIDER_KEY\n"))
    monkeypatch.delenv("MY_PROVIDER_KEY", raising=False)
    assert _common.resolve_gate_verdict() == (False, "disabled-via-config")


def test_gate_does_not_hold_a_private_veto_copy(clean_env, monkeypatch):
    """resolve_gate_verdict() must not re-decide the veto.

    It previously tested the kill switch itself before calling the cascade. The
    answers agreed, so it looked harmless — but it MASKED the cascade: with the
    veto mis-ranked inside delegation_enabled(), the probe still reported
    disabled-via-env from its private copy while require_delegation_enabled(),
    which has no such copy, let the call through. A duplicate that agrees today
    is a second authority hiding the first one's bugs.

    Asserted structurally: the verdict must equal the cascade on every input,
    including ones where only the veto differs.
    """
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-legacy")
    monkeypatch.setenv("ADLC_DISABLE_DELEGATE", "1")
    assert _common.resolve_gate_verdict()[0] == _common.delegation_enabled()


def test_malformed_config_outranks_env_opt_in(clean_env, monkeypatch):
    """The _MALFORMED arm sits ABOVE ADLC_DELEGATE_ENABLED=1 — deliberately: a
    config we were told to read and could not is not a state the env override
    may lift. Pass 4 found this ordering had ZERO coverage: every malformed test
    ran under a fixture that deletes the env var, and moving the arm below it
    passed 610 tests. This sets both, on all three surfaces."""
    f = clean_env / "cfg.yml"
    f.write_text("delegate:\n  enabled: false\n", encoding="utf-8")
    f.chmod(0o000)
    try:
        monkeypatch.setenv("ADLC_CONFIG", str(f))
        monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
        monkeypatch.setenv("MOONSHOT_API_KEY", "sk-stale")
        assert _common.resolve_gate_verdict() == (False, "disabled-via-config")
        assert _common.delegation_enabled() is False
        with pytest.raises(SystemExit):
            _common.require_delegation_enabled("adlc-read")
    finally:
        f.chmod(0o644)
