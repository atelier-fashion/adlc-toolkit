---
id: TASK-002
title: "doctor runner: profile, CheckResult, registry, --checks filter, report"
status: draft
parent: REQ-519
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

Build the `doctor` subcommand's framework in `tools/adlc/doctor.py`: the machine
`Profile` (BR-6), the `CheckResult` 3-state enum (BR-4), the `Check` descriptor,
the registry runner with the `--checks` filter (BR-8), the ordered report
formatter (BR-5), and exit-code derivation (BR-4: non-zero iff any non-skip
check fails). The individual check implementations land in TASK-003; this task
defines the contract and a registry that TASK-003 populates.

## Files to Create/Modify

- `tools/adlc/doctor.py` —
  - `Profile` dataclass/namedtuple: `os` (`"Darwin"`/`"Linux"`), `login_shell`
    (from `pwd.getpwuid(os.getuid()).pw_shell`, NOT `$SHELL`), `repo_root`.
  - `Result` enum: `PASS`, `FAIL`, `SKIP`.
  - `Check` descriptor: `id`, `run(profile) -> (Result, detail, remediation)`,
    `applies_to(profile) -> bool` (default: always).
  - `REGISTRY`: ordered list of `Check` (imported/assembled from `checks.py`).
  - `run_checks(profile, only=None)`: iterate registry, honor `applies_to`
    (emit SKIP-with-notice for inapplicable), apply `only` filter, collect
    results.
  - `--checks id1,id2` argparse: validate each id is in the registry; unknown id
    → error and non-zero exit (NOT silent no-op).
  - `format_report(results, profile)`: ordered, per-check line
    `[PASS|FAIL|SKIP] <id> — <detail>` and, on FAIL, an indented
    `→ fix: <remediation>` line; trailing machine-profile line and overall
    verdict.
  - `main(argv)`: build profile, parse args, run, print report, return exit code
    (0 if no non-skip FAIL, else 1).

## Acceptance Criteria

- [ ] `Profile.login_shell` comes from the password DB, not `$SHELL` (BR-6).
- [ ] `Result.SKIP` never contributes to a non-zero exit (BR-4).
- [ ] `--checks gh-auth,delegate-gate` runs only those two checks (BR-8, AC-6).
- [ ] `--checks bogus-id` errors with the list of valid ids and exits non-zero.
- [ ] Report lists checks in registry order; each FAIL shows a copy-pasteable
      remediation line (BR-5).
- [ ] `applies_to` False → SKIP with a notice (e.g. "launchctl is macOS-only"),
      never FAIL (BR-6).

## Technical Notes

- Stdlib only: `enum`, `os`, `pwd`, `platform`, `argparse`, `dataclasses`.
- The registry is assembled by importing the check callables from `checks.py`
  (TASK-003). To let TASK-002 land/test independently, define the framework and
  an empty-or-stub registry here; TASK-003 fills it. Keep the runner agnostic to
  which checks exist.
- Exit code: `1` if any `Result.FAIL` present among non-skipped checks; else `0`.
- Report must be plain ASCII (no color codes required) so it's pasteable.
