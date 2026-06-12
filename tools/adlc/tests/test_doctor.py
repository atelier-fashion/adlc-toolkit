"""Tests for the doctor runner framework (TASK-002 / BR-4, BR-6, BR-8)."""
import pytest

import doctor
from doctor import Check, CheckOutcome, Profile, Result


def _profile(os_name="Linux"):
    return Profile(os=os_name, login_shell="/bin/zsh", repo_root="/tmp/repo")


def _check(cid, result, applies=True):
    return Check(
        cid,
        run=lambda p, r=result: (r, f"{cid} detail", "fix it" if r is Result.FAIL else ""),
        applies_to=lambda p, a=applies: a,
    )


# --- registry iteration + filter -------------------------------------------

def test_runner_iterates_in_registry_order():
    reg = [_check("a", Result.PASS), _check("b", Result.PASS), _check("c", Result.PASS)]
    outcomes = doctor.run_checks(_profile(), registry=reg)
    assert [o.id for o in outcomes] == ["a", "b", "c"]


def test_checks_filter_runs_only_subset():
    reg = [_check("a", Result.PASS), _check("b", Result.PASS), _check("c", Result.PASS)]
    outcomes = doctor.run_checks(_profile(), registry=reg, only=["b"])
    assert [o.id for o in outcomes] == ["b"]


def test_unknown_check_id_rejected(capsys):
    reg = [_check("gh-auth", Result.PASS)]
    with pytest.raises(ValueError) as exc:
        doctor._parse_only("gh-auth,bogus", reg)
    assert "bogus" in str(exc.value)
    assert "valid checks" in str(exc.value)


def test_parse_only_accepts_known_ids():
    reg = [_check("gh-auth", Result.PASS), _check("delegate-gate", Result.PASS)]
    assert doctor._parse_only("gh-auth,delegate-gate", reg) == ["gh-auth", "delegate-gate"]


# --- applies_to gating (BR-6) ----------------------------------------------

def test_inapplicable_check_is_skip_not_fail():
    reg = [_check("launchctl", Result.FAIL, applies=False)]
    outcomes = doctor.run_checks(_profile(os_name="Linux"), registry=reg)
    assert outcomes[0].result is Result.SKIP


def test_launchctl_skipped_on_linux_profile():
    # The real launchctl check applies_to os==Darwin; simulate a Linux profile.
    reg = [Check("launchctl", run=lambda p: (Result.FAIL, "x", "y"),
                 applies_to=lambda p: p.os == "Darwin")]
    outcomes = doctor.run_checks(_profile(os_name="Linux"), registry=reg)
    assert outcomes[0].result is Result.SKIP


# --- verdict / exit code (BR-4: SKIP never fails) --------------------------

def test_exit_code_zero_when_all_pass_or_skip():
    outcomes = [
        CheckOutcome("a", Result.PASS, "", ""),
        CheckOutcome("b", Result.SKIP, "", ""),
    ]
    assert doctor.verdict_exit_code(outcomes) == 0


def test_exit_code_nonzero_on_any_fail():
    outcomes = [
        CheckOutcome("a", Result.PASS, "", ""),
        CheckOutcome("b", Result.FAIL, "", "fix"),
    ]
    assert doctor.verdict_exit_code(outcomes) == 1


def test_skip_only_is_zero():
    outcomes = [CheckOutcome("a", Result.SKIP, "", ""), CheckOutcome("b", Result.SKIP, "", "")]
    assert doctor.verdict_exit_code(outcomes) == 0


# --- report format (BR-5) --------------------------------------------------

def test_report_shows_remediation_on_fail():
    outcomes = [CheckOutcome("x", Result.FAIL, "broken", "run this")]
    report = doctor.format_report(outcomes, _profile())
    assert "[FAIL] x — broken" in report
    assert "-> fix: run this" in report


def test_report_no_remediation_line_on_pass():
    outcomes = [CheckOutcome("x", Result.PASS, "good", "")]
    report = doctor.format_report(outcomes, _profile())
    assert "[PASS] x — good" in report
    assert "-> fix:" not in report


def test_report_includes_profile_and_verdict():
    outcomes = [CheckOutcome("x", Result.PASS, "good", "")]
    report = doctor.format_report(outcomes, _profile(os_name="Darwin"))
    assert "profile: os=Darwin" in report
    assert "verdict: OK" in report


# --- a crashing check must not crash doctor --------------------------------

def test_crashing_check_becomes_fail_not_exception():
    def boom(p):
        raise RuntimeError("kaboom")

    reg = [Check("boom", run=boom)]
    outcomes = doctor.run_checks(_profile(), registry=reg)
    assert outcomes[0].result is Result.FAIL
    assert "RuntimeError" in outcomes[0].detail
