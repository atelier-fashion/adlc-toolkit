"""REQ-603 TASK-091 — the shell and Python veto layers must agree.

BR-2 permits ONE deliberate duplication: `ADLC_DISABLE_DELEGATE` lives in both
`delegate-gate.sh` and `delegation_enabled()`. The safety argument is that a veto
arm can only ever return *disabled*, so the copies can agree or abstain but never
contradict — **provided Python recognises at least every input the shell does.**

That proviso is the whole of it, and it is what this file enforces. If the shell
veto is ever widened alone (accepting `true`/`yes` alongside `1`, which reads as
a usability fix), the gate reports `disabled-via-env` while a direct CLI call
transmits: the operator sees "disabled" everywhere they look and file contents
leave the machine anyway. That is BUG-209's failure, reintroduced through the
door BR-2 deliberately opens.

Two per-layer tests cannot substitute for this one. Each passes in isolation
precisely while the layers diverge — that is the failure mode.
"""
import os
import re
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_DELEGATE = os.path.dirname(_HERE)
_PARTIALS = os.path.normpath(os.path.join(_DELEGATE, "..", "..", "partials"))
sys.path.insert(0, _DELEGATE)
import _common  # noqa: E402

# The shared input vector. Every value either layer might plausibly be asked
# about, including the ones a well-meaning "make it friendlier" change would add.
VETO_INPUTS = ["1", "0", "", "true", "yes", "TRUE", "2", "01", None]

_CLEAR = ("MOONSHOT_API_KEY", "KIMI_API_KEY", "ADLC_DELEGATE_ENABLED",
          "ADLC_CONFIG", "ADLC_DISABLE_DELEGATE")


def _shell_veto_fires(value, tmp_path):
    """True iff delegate-gate.sh's veto short-circuits for this value.

    Uses a stub that would say `1 ok` — so a `disabled-via-env` verdict can only
    have come from the veto, never from the cascade.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "adlc-read"
    stub.write_text('#!/bin/sh\n[ "$1" = "--print-gate" ] && { echo "1 ok"; exit 0; }\nexit 0\n')
    stub.chmod(0o755)
    env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path),
           "ADLC_DELEGATE_ENABLED": "1"}
    if value is not None:
        env["ADLC_DISABLE_DELEGATE"] = value
    r = subprocess.run(
        ["/bin/sh", "-c",
         f'. "{_PARTIALS}/delegate-gate.sh"; adlc_delegate_gate_check >/dev/null 2>&1; '
         'printf "%s" "$ADLC_DELEGATE_GATE_REASON"'],
        capture_output=True, text=True, env=env)
    return r.stdout.strip() == "disabled-via-env"


def _python_veto_fires(value, monkeypatch, tmp_path):
    for v in _CLEAR:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ADLC_DELEGATE_ENABLED", "1")
    if value is not None:
        monkeypatch.setenv("ADLC_DISABLE_DELEGATE", value)
    _, reason = _common.resolve_gate_verdict()
    return reason == "disabled-via-env"


@pytest.mark.parametrize("value", VETO_INPUTS, ids=lambda v: repr(v))
def test_both_layers_agree_over_input_vector(value, monkeypatch, tmp_path):
    """AC-3 / BR-2. One test, both layers, one vector — so widening either alone
    fails here rather than silently in production."""
    shell = _shell_veto_fires(value, tmp_path)
    py = _python_veto_fires(value, monkeypatch, tmp_path)
    assert shell == py, (
        f"veto layers disagree for ADLC_DISABLE_DELEGATE={value!r}: "
        f"shell={'vetoes' if shell else 'abstains'}, "
        f"python={'vetoes' if py else 'abstains'}. "
        "BR-2's duplication is only safe while both recognise the same inputs."
    )


def test_shared_input_vector_parity(monkeypatch, tmp_path):
    """The same assertion stated as a whole-vector comparison, so a failure
    reports the full disagreement set rather than the first mismatch."""
    shell = {v: _shell_veto_fires(v, tmp_path) for v in VETO_INPUTS}
    py = {v: _python_veto_fires(v, monkeypatch, tmp_path) for v in VETO_INPUTS}
    assert shell == py, f"disagreements: {[k for k in shell if shell[k] != py[k]]}"


def test_only_the_literal_one_vetoes(monkeypatch, tmp_path):
    """Pins the current agreed breadth. Widening BOTH layers together is a
    deliberate decision; this case makes it deliberate rather than accidental."""
    for v in VETO_INPUTS:
        expected = (v == "1")
        assert _python_veto_fires(v, monkeypatch, tmp_path) is expected, v
        assert _shell_veto_fires(v, tmp_path) is expected, v


def test_widening_python_alone_is_safe_widening_shell_alone_is_not(monkeypatch, tmp_path):
    """Documents the asymmetry BR-2 depends on, as an executable claim.

    A shell veto NARROWER than Python's is harmless: shell abstains, the probe
    still vetoes, and the gate reports disabled. The dangerous direction is a
    shell veto BROADER than Python's, because the gate then short-circuits to
    `disabled-via-env` while a direct CLI call — governed only by Python — still
    transmits.
    """
    # "true" is recognised by neither today. If shell alone were widened to
    # accept it, the gate would veto while Python would not — precisely the
    # divergence this file exists to catch.
    assert _shell_veto_fires("true", tmp_path) is False
    assert _python_veto_fires("true", monkeypatch, tmp_path) is False


# --- Q4: enforce the PROPERTY, not a sample --------------------------------
# The enumerated vector above is a sample. A sample cannot express "Python
# recognises at least every input the shell does" — it only checks the values
# someone thought of. Mutating the shell veto to also accept "on" passed the
# whole suite, and "on" is not exotic: parse_delegate_config's own truthiness set
# in this same codebase is ("true", "yes", "1", "on"), so a developer harmonising
# the veto with config truthiness has a live path to exactly the divergence BR-2
# exists to prevent.
#
# These derive the accepted literal set from the shell source itself, so ANY
# widening of either layer fails whether or not the new value is in a vector.

_GATE_SH = os.path.join(_PARTIALS, "delegate-gate.sh")


def _shell_veto_literals():
    """The literal values delegate-gate.sh's veto compares against.

    Parses the guard rather than trusting a hardcoded copy of it. If the guard's
    shape changes so this cannot find it, the test fails loudly instead of
    silently asserting nothing (a vacuous pass is the failure mode here).
    """
    text = open(_GATE_SH, encoding="utf-8").read()
    lits = set()
    for line in text.splitlines():
        if "ADLC_DISABLE_DELEGATE" not in line:
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # `[ "${ADLC_DISABLE_DELEGATE:-0}" = "1" ]` and case-arm variants.
        for m in re.finditer(r'=\s*"([^"]*)"', line):
            lits.add(m.group(1))
        for m in re.finditer(r"^\s*([A-Za-z0-9|]+)\)", stripped):
            lits.update(m.group(1).split("|"))
    return lits


def test_shell_veto_guard_is_parseable():
    """Guards the guard: if this returns nothing, every assertion below is
    vacuous, which is the LESSON-602 shape."""
    assert _shell_veto_literals(), (
        f"could not parse the veto guard out of {_GATE_SH} — the assertions "
        "below would pass vacuously")


def test_shell_veto_accepts_exactly_the_literal_one():
    """The property, derived from source. Widening the shell veto fails here
    even if the new value appears in no test vector."""
    assert _shell_veto_literals() == {"1"}, (
        "delegate-gate.sh's veto accepts values beyond the literal \"1\". "
        "Python must be widened in the same commit, or the gate will report "
        "disabled while a direct CLI call transmits (BUG-209's shape).")


def test_python_veto_accepts_every_literal_the_shell_does(monkeypatch, tmp_path):
    """BR-2's stated condition, asserted directly rather than sampled:
    Python must recognise AT LEAST every input the shell does."""
    for lit in _shell_veto_literals():
        assert _python_veto_fires(lit, monkeypatch, tmp_path), (
            f"shell vetoes on {lit!r} but Python does not — the gate would "
            "report disabled while a direct CLI call transmits")


def test_kill_switch_has_exactly_two_implementations():
    """The docs say ONE deliberate duplication (shell + Python). It was four:
    delegation_enabled, resolve_gate_verdict, require_delegation_enabled, and
    the shell. The parity test compared only two of them, so widening the shell
    and one Python copy together left the suite green while the copy guarding
    transmission stayed narrow."""
    src = open(os.path.join(_DELEGATE, "_common.py"), encoding="utf-8").read()
    comparisons = [
        ln for ln in src.splitlines()
        if "ADLC_DISABLE_DELEGATE" in ln and "==" in ln and not ln.strip().startswith("#")
    ]
    assert len(comparisons) == 1, (
        "ADLC_DISABLE_DELEGATE is compared in more than one Python place: "
        f"{comparisons}. Every site must call _kill_switch_set() so the veto has "
        "exactly two textual implementations toolkit-wide.")
