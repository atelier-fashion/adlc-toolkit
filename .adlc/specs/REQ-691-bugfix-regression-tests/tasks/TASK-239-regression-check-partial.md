---
id: TASK-239
title: "`partials/regression-check.sh` wrapper, its contract and its shell harness"
status: draft
parent: REQ-691
created: 2026-11-04
updated: 2026-11-04
dependencies: [TASK-238]
---

## Description

Give skill fences one sourceable function, `adlc_regression_check <verb> [args]`, that runs the TASK-238 engine from the installed toolkit, mirroring `partials/lane-check.sh` line by line, rationale comments included (LESSON-023).

## Files to Create/Modify

- `partials/regression-check.sh` — new. Resolves `${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/regression_check.py`. Refuses a relative root and an engine inside the working tree under check. Takes the interpreter from `_adlc_forge_python` and runs `command "$py" -E <engine> "$@"`. Replaces any rc other than 0/1/2, or a first stdout line that isn't a known verdict, with `regression-check: error` and rc 2.
- `partials/regression-check.md` — new. The rc and output contract, with each verdict line and what a fence does with it.
- `partials/tests/regression-check.test.sh` — new. POSIX harness over a temp repo, asserting on the verdict lines, never on exit status alone (LESSON-754).
- `partials/tests/run.sh` — register the harness on its own `run_all` line (LESSON-738).
- `partials/README.md` — add the partial to the roster.

## Acceptance Criteria

- [ ] Under bash, zsh, `/bin/sh` and dash, `adlc_regression_check mode` prints `regression-test: off` for a repo with no config, and `check` prints `regression-check: off`.
- [ ] With a config setting `required`, a passing bug gives `regression-check: pass` rc 0, and a failing one gives `regression-check: fail` rc 1 with its `BUG-nnn:` line.
- [ ] A missing engine, a relative `ADLC_TOOLKIT_ROOT`, and an engine stubbed to print nothing each give `regression-check: error` and rc 2.
- [ ] `sh partials/tests/run.sh` passes with the new harness registered.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `partials/tests/regression-check.test.sh::mode_absent_config_is_off` | yes |
| BR-10 | test-case | `partials/tests/regression-check.test.sh::check_pass_and_fail_verdicts` | yes |
| BR-11 | test-case | `partials/tests/regression-check.test.sh::check_off_verdict` | yes |
| BR-17 | test-case | `partials/tests/regression-check.test.sh::wrapper_errors_never_read_as_off` | no |

## Technical Notes

- The partial carries no root line (partials never do); it reads the default-expansion spelling.
- No `local` and no bash-isms: the harness runs it under dash.
- `_adlc_forge_python` is in `partials/forge.sh`. Source it inside the function's file with the guarded two-level spelling, as `lane-check.sh` does.
