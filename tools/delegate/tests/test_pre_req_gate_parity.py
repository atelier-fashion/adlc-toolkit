"""REQ-603 AC-19 / AC-21 — compare the CURRENT gate against the PRE-REQ gate.

Three review passes asked for this and none of the prior substitutes did it:
they compared the cascade against a restatement of itself, by the same author.
This runs BOTH gate scripts — origin/main's, frozen as a fixture — over one
input matrix, backed by the SAME real adlc-read, so the only variable is the
shell layer and the reason mapping. That is exactly what BR-4 makes claims
about.

The named divergences (BR-4 D1-D5) must occur; nothing else may.
"""
import os
import subprocess
import sys

import pytest

import _child_env  # noqa: E402  (REQ-609: child interpreters need the parent's PyYAML)

_HERE = os.path.dirname(os.path.abspath(__file__))
_DELEGATE = os.path.dirname(_HERE)
_ROOT = os.path.normpath(os.path.join(_DELEGATE, "..", ".."))
_CURRENT = os.path.join(_ROOT, "partials", "delegate-gate.sh")
_FIXTURE = os.path.join(_ROOT, "partials", "tests", "fixtures", "delegate-gate.pre-req-603.sh")
_ADLC_READ = os.path.join(_DELEGATE, "adlc-read")
# The pre-REQ CLI + resolver, frozen from origin/main. D3/D4/D5 are PYTHON-layer
# divergences; comparing them needs the old Python behind the old gate, or the
# old gate merely reports the new resolver's answer and the row looks identical.
_OLD_ADLC_READ = os.path.join(_ROOT, "partials", "tests", "fixtures", "pre-req-603", "adlc-read")


def _run_gate(gate, env):
    r = subprocess.run(
        ["/bin/sh", "-c",
         f'. "{gate}"; adlc_delegate_gate_check >/dev/null 2>&1; '
         'printf "%s %s" "$?" "$ADLC_DELEGATE_GATE_REASON"'],
        capture_output=True, text=True, env=env)
    return r.stdout.strip()


def _env(tmp_path, veto=False, env_optin=False, config=None, legacy=False,
         key_var_unset=False, unreadable=False, cli=_ADLC_READ):
    # One wrapper directory PER CLI. A shared tmp_path/bin let a later
    # _env(new) call overwrite the wrapper a prior _env(old) had written, so
    # the OLD gate ran with the NEW resolver behind it. D3 passed by coincidence
    # (both CLIs agree on that row); the malformed-class rows exposed it.
    bindir = tmp_path / ("bin-old" if cli == _OLD_ADLC_READ else "bin-new")
    bindir.mkdir(exist_ok=True)
    wrapper = bindir / "adlc-read"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{cli}" "$@"\n')
    wrapper.chmod(0o755)
    e = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    # A key the REAL resolver can find, via a custom var so legacy-key
    # continuity is exercised only by the `legacy` axis.
    e["ADLC_DELEGATE_API_KEY_ENV"] = "MY_PROVIDER_KEY"
    if not key_var_unset:
        e["MY_PROVIDER_KEY"] = "sk-resolvable"
    if veto:
        e["ADLC_DISABLE_DELEGATE"] = "1"
    if env_optin:
        e["ADLC_DELEGATE_ENABLED"] = "1"
    if legacy:
        e["MOONSHOT_API_KEY"] = "sk-legacy"
    if config is not None:
        cfg = tmp_path / "config.yml"
        cfg.write_text(f"delegate:\n  enabled: {config}\n  api_key_env: MY_PROVIDER_KEY\n")
        if unreadable:
            cfg.chmod(0o000)
        e["ADLC_CONFIG"] = str(cfg)
    return _child_env.with_yaml(e)


# The full exported cross-product, with the SAME Python behind both gates. This
# isolates the shell layer: any difference here is a shell-arm difference, which
# is exactly what BR-1 removed and BR-4 makes claims about. Python-layer
# divergences (D3, D4, D5) are asserted separately below with the OLD CLI behind
# the OLD gate. Unexported variables are a KNOWN divergence (pass-3 M5): the old
# shell arms read shell scope, the probe cannot; not modelled here.
_MATRIX = [
    (veto, env_optin, config, legacy)
    for veto in (False, True)
    for env_optin in (False, True)
    for config in (None, "true", "false")
    for legacy in (False, True)
]

# BR-4's named divergences, as (inputs) -> (pre-REQ, current). Anything that
# differs between the gates and is NOT listed here is a finding.
_NAMED = {
    # D1: enabled:false, no legacy key -> label corrected, rc unchanged
    (False, False, "false", False): ("1 not-opted-in", "1 disabled-via-config"),
}


@pytest.mark.parametrize("row", _MATRIX, ids=lambda r: str(r))
def test_current_gate_matches_pre_req_gate_except_named_rows(row, tmp_path):
    veto, env_optin, config, legacy = row
    env = _env(tmp_path, veto=veto, env_optin=env_optin, config=config, legacy=legacy)
    old = _run_gate(_FIXTURE, env)
    new = _run_gate(_CURRENT, env)
    if row in _NAMED:
        assert (old, new) == _NAMED[row], f"named divergence {row} changed shape: {old!r} -> {new!r}"
    else:
        assert old == new, f"UNNAMED divergence at {row}: pre-REQ={old!r} current={new!r}"


def test_every_named_divergence_actually_diverges(tmp_path):
    """A table of exceptions is only honest if each exception is real."""
    for row, (exp_old, exp_new) in _NAMED.items():
        veto, env_optin, config, legacy = row
        env = _env(tmp_path, veto=veto, env_optin=env_optin, config=config, legacy=legacy)
        assert _run_gate(_FIXTURE, env) == exp_old, row
        assert _run_gate(_CURRENT, env) == exp_new, row


def test_d3_key_unset_diverges_fail_closed(tmp_path):
    """D3: opt-in satisfied, key var unset. pre-REQ (old gate + old CLI): ok —
    the old probe never checked the key. current: disabled-via-config, rc 0->1."""
    old_env = _env(tmp_path, config="true", key_var_unset=True, cli=_OLD_ADLC_READ)
    new_env = _env(tmp_path, config="true", key_var_unset=True)
    assert _run_gate(_FIXTURE, old_env) == "0 ok"
    assert _run_gate(_CURRENT, new_env) == "1 disabled-via-config"


def test_d4_unreadable_config_diverges_fail_closed(tmp_path):
    """D4: config exists but unreadable, legacy key exported. pre-REQ (old gate
    + old CLI): ok — unreadable read as absent, continuity granted. current:
    refuses. This is the BUG-205 outcome the REQ closes."""
    old_env = _env(tmp_path, config="false", legacy=True, unreadable=True, cli=_OLD_ADLC_READ)
    try:
        assert _run_gate(_FIXTURE, old_env) == "0 ok"
        (tmp_path / "config.yml").chmod(0o644)
        new_env = _env(tmp_path, config="false", legacy=True, unreadable=True)
        assert _run_gate(_CURRENT, new_env) == "1 disabled-via-config"
    finally:
        (tmp_path / "config.yml").chmod(0o644)


def test_d5_print_enabled_is_not_frozen_and_the_spec_says_so(tmp_path):
    """D5: --print-enabled inherited the fail-closed config rule. Three
    artifacts claimed it was frozen; it is not, and the honest thing is to
    name it. Old CLI: 1. Current CLI: 0. Same unreadable config, same key."""
    env = _env(tmp_path, config="false", legacy=True, unreadable=True)
    try:
        old = subprocess.run([sys.executable, _OLD_ADLC_READ, "--print-enabled"],
                             capture_output=True, text=True, env=env).stdout.strip()
        new = subprocess.run([sys.executable, _ADLC_READ, "--print-enabled"],
                             capture_output=True, text=True, env=env).stdout.strip()
        assert (old, new) == ("1", "0"), (old, new)
    finally:
        (tmp_path / "config.yml").chmod(0o644)


def test_old_and_new_python_agree_where_no_divergence_is_named(tmp_path):
    """The Python layer, old vs new, on a row NO divergence names: must agree.
    Guards against a Python-layer change hiding behind the shell-only matrix."""
    for cfg, legacy in ((None, True), ("true", False), ("false", False)):
        old_env = _env(tmp_path, config=cfg, legacy=legacy, cli=_OLD_ADLC_READ)
        new_env = _env(tmp_path, config=cfg, legacy=legacy)
        o = subprocess.run([sys.executable, _OLD_ADLC_READ, "--print-enabled"],
                           capture_output=True, text=True, env=old_env).stdout.strip()
        n = subprocess.run([sys.executable, _ADLC_READ, "--print-enabled"],
                           capture_output=True, text=True, env=new_env).stdout.strip()
        assert o == n, (cfg, legacy, o, n)


# --- Malformed-config classes the 24-row matrix could not observe -----------
# Pass 4: the config axis was (None, "true", "false"), so no BR-4 D4-class row was
# ever compared against the pre-REQ gate. These rows are. Two of them are
# KNOWN LIMITATIONS (BR-14): they fail open on BOTH gates, so they do not
# diverge, and the test records that fact rather than hiding it.

def _cfg_dir(tmp_path):
    d = tmp_path / "adlc"; d.mkdir(); return str(d)

def _cfg_file(tmp_path, body):
    f = tmp_path / "config.yml"; f.write_bytes(body); return str(f)

@pytest.mark.parametrize("label,make,expect_old,expect_new", [
    # Undecodable byte INSIDE the key: the pre-REQ reader's errors="replace"
    # turns it into U+FFFD, the key no longer matches `enabled`, {} -> continuity
    # -> grant. The current reader refuses on the decode error. D4 class.
    ("undecodable byte in the key (D4 class: refused now)",
     lambda t: _cfg_file(t, b"delegate:\n  enabl\xe9d: false\n"), "0 ok", "1 disabled-via-config"),
    # Undecodable byte inside a COMMENT: replace() leaves `enabled: false`
    # parseable, so BOTH gates refuse. Not a divergence; recorded so the row is
    # a measured fact and not an assumption (the first version of this test
    # expected the old gate to grant here, and was wrong).
    ("undecodable byte in a comment (both refuse — benign path)",
     lambda t: _cfg_file(t, b"delegate:\n  enabled: false  # d\xe9sactiv\xe9\n"), "1 disabled-via-config", "1 disabled-via-config"),
    # REQ-609 flips both: a non-regular file is malformed with no carve-out
    # (BR-4), and a real parser reads the block behind a header comment (BR-3,
    # BR-7). The old gate still grants — that is the pre-existing fail-open
    # REQ-603 BR-14 recorded; the current gate refuses. TASK-095 registers these
    # as named divergences (ADR-4) beside D1-D5.
    ("directory at the path (REQ-603 BR-14 fail-open, discharged by REQ-609 BR-4: old grants, new refuses)",
     lambda t: _cfg_dir(t), "0 ok", "1 disabled-via-config"),
    ("header comment no longer discards the block (REQ-603 BR-14 fail-open, discharged by REQ-609: old grants, new reads enabled: false)",
     lambda t: _cfg_file(t, b"delegate:  # settings\n  enabled: false\n"), "0 ok", "1 disabled-via-config"),
], ids=lambda v: v if isinstance(v, str) else "")
def test_malformed_classes_against_pre_req_gate(label, make, expect_old, expect_new, tmp_path):
    path = make(tmp_path)
    base = dict(legacy=True)
    old_env = _env(tmp_path, cli=_OLD_ADLC_READ, **base); old_env["ADLC_CONFIG"] = path
    new_env = _env(tmp_path, **base);                       new_env["ADLC_CONFIG"] = path
    assert _run_gate(_FIXTURE, old_env) == expect_old, (label, "pre-REQ")
    assert _run_gate(_CURRENT, new_env) == expect_new, (label, "current")
