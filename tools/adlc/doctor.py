#!/usr/bin/env python3
"""adlc doctor — read-only environment health check (REQ-519).

Doctor iterates an ordered registry of checks, each reporting PASS / FAIL / SKIP
with a copy-pasteable remediation on FAIL (BR-5). It exits non-zero **iff** any
non-skip check fails (BR-4): SKIP never contributes to failure, so inapplicable
checks (a macOS-only check on Linux, delegation checks when delegation is off)
keep the overall verdict honest (BR-6).

Doctor is also the pre-flight primitive other skills call: ``--checks id1,id2``
runs only the named subset (BR-8), the contract that lets ``/sprint`` and
``/proceed`` converge their environment probes on doctor instead of maintaining
parallel probe code.

Pure standard library — doctor must run before/without the delegation venv.
"""

import argparse
import os
import platform
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Result(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class Profile:
    """Honest machine profile (BR-6).

    ``login_shell`` is read from the password database, NOT ``$SHELL`` — ``$SHELL``
    reflects the shell that happens to be invoking us, which may differ from the
    user's real login shell (e.g. a bash subshell under a zsh login).
    """

    os: str            # "Darwin" | "Linux" | other platform.system() value
    login_shell: str   # absolute path to the login shell, or "" if undetermined
    repo_root: str     # toolkit checkout root


def _detect_login_shell() -> str:
    """Real login shell from the password DB, not $SHELL (BR-6)."""
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_shell or ""
    except (ImportError, KeyError, OSError):
        # pwd is POSIX-only; on a platform without it, degrade to empty rather
        # than lying via $SHELL.
        return ""


def _detect_repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", here, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out:
            return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return os.path.dirname(os.path.dirname(here))


def build_profile() -> Profile:
    return Profile(
        os=platform.system(),
        login_shell=_detect_login_shell(),
        repo_root=_detect_repo_root(),
    )


# A check's run() returns (Result, detail, remediation). remediation is only
# meaningful on FAIL and must be a copy-pasteable command or exact file edit
# (BR-5); on PASS/SKIP it may be "".
CheckRun = Callable[[Profile], Tuple[Result, str, str]]


@dataclass
class Check:
    id: str
    run: CheckRun
    # applies_to gates platform/opt-in relevance (BR-6). When it returns False,
    # the check is reported SKIP-with-notice, never FAIL.
    applies_to: Callable[[Profile], bool] = field(default=lambda p: True)
    skip_notice: str = "not applicable on this machine"


@dataclass
class CheckOutcome:
    id: str
    result: Result
    detail: str
    remediation: str


def _build_registry() -> List[Check]:
    """Assemble the ordered registry from checks.py.

    Imported lazily so the doctor framework (and its tests) can be exercised even
    if a specific check has an import issue; an empty registry is a valid state
    for framework-only tests.
    """
    try:
        import checks
    except ImportError:
        return []
    return checks.REGISTRY


def run_checks(profile: Profile,
               registry: Optional[List[Check]] = None,
               only: Optional[List[str]] = None) -> List[CheckOutcome]:
    """Run the registry (optionally filtered to ``only``) and collect outcomes.

    ``only`` is validated by the caller (main) before reaching here; an unknown
    id is a hard error there, not a silent no-op (BR-8).
    """
    if registry is None:
        registry = _build_registry()
    outcomes: List[CheckOutcome] = []
    for check in registry:
        if only is not None and check.id not in only:
            continue
        if not check.applies_to(profile):
            outcomes.append(CheckOutcome(check.id, Result.SKIP, check.skip_notice, ""))
            continue
        try:
            result, detail, remediation = check.run(profile)
        except Exception as exc:  # a check must never crash doctor
            outcomes.append(CheckOutcome(
                check.id, Result.FAIL,
                f"check raised {type(exc).__name__}: {exc}",
                "report this as a doctor bug; rerun with the check excluded via "
                f"--checks <others> to continue",
            ))
            continue
        outcomes.append(CheckOutcome(check.id, result, detail, remediation))
    return outcomes


def verdict_exit_code(outcomes: List[CheckOutcome]) -> int:
    """0 unless any non-skip check FAILed (BR-4)."""
    return 1 if any(o.result is Result.FAIL for o in outcomes) else 0


def format_report(outcomes: List[CheckOutcome], profile: Profile) -> str:
    lines: List[str] = []
    for o in outcomes:
        lines.append(f"[{o.result.value}] {o.id} — {o.detail}")
        if o.result is Result.FAIL and o.remediation:
            lines.append(f"    -> fix: {o.remediation}")
    n_fail = sum(1 for o in outcomes if o.result is Result.FAIL)
    n_skip = sum(1 for o in outcomes if o.result is Result.SKIP)
    n_pass = sum(1 for o in outcomes if o.result is Result.PASS)
    lines.append("")
    shell = profile.login_shell or "(undetermined)"
    lines.append(f"profile: os={profile.os} login_shell={shell}")
    verdict = "OK" if n_fail == 0 else "FAILED"
    lines.append(
        f"verdict: {verdict} ({n_pass} pass, {n_fail} fail, {n_skip} skip)"
    )
    return "\n".join(lines)


def _parse_only(value: str, registry: List[Check]) -> List[str]:
    """Parse a --checks value into a validated list of ids.

    Unknown ids are a hard error (BR-8) — returns the list on success, raises
    ValueError with the valid set on failure.
    """
    requested = [s.strip() for s in value.split(",") if s.strip()]
    valid = {c.id for c in registry}
    unknown = [r for r in requested if r not in valid]
    if unknown:
        raise ValueError(
            "unknown check id(s): " + ", ".join(unknown)
            + "\nvalid checks: " + ", ".join(sorted(valid))
        )
    return requested


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="adlc doctor",
        description="Read-only environment health check.",
    )
    parser.add_argument(
        "--checks",
        metavar="id1,id2",
        help="run only the named checks (comma-separated). The skill pre-flight "
             "contract: e.g. --checks gh-auth,delegate-gate",
    )
    args = parser.parse_args(argv)

    profile = build_profile()
    registry = _build_registry()

    only = None
    if args.checks:
        try:
            only = _parse_only(args.checks, registry)
        except ValueError as exc:
            sys.stderr.write(f"adlc doctor: {exc}\n")
            return 2

    outcomes = run_checks(profile, registry=registry, only=only)
    print(format_report(outcomes, profile))
    return verdict_exit_code(outcomes)


if __name__ == "__main__":
    raise SystemExit(main())
