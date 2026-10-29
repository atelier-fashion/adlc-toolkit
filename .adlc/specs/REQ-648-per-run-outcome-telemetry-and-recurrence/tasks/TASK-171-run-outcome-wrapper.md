---
id: TASK-171
title: "emit-run-outcome.sh wrapper and its four-shell harness"
status: complete
parent: REQ-648
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-170]
repo: adlc-toolkit
---

## Description

Add the POSIX wrapper `tools/delegate/emit-run-outcome.sh` (executed, never
sourced) that runs `run_outcome.py` and appends the emitted line to the
run-outcome log with `umask 077`, passes `record-*` subcommands through, and
always exits 0 with one stderr line on any failure. Add its harness to
`partials/tests/run.sh` so it runs under bash, zsh, sh and dash. Document the
three new tools in `tools/delegate/README.md`.

## Files to Create/Modify

- `tools/delegate/emit-run-outcome.sh` — new wrapper (mode 0755)
- `partials/tests/run-outcome.test.sh` — new: append + 0600 + never-blocks + record passthrough + no-python degrade, under `$ADLC_TEST_SHELL`
- `partials/tests/run.sh` — add `run-outcome.test.sh` to the harness list
- `tools/delegate/README.md` — document `run_outcome.py`, `emit-run-outcome.sh`, `check-run-outcomes.sh` and the log

## Acceptance Criteria

- [ ] A first emit creates `$ADLC_RUN_OUTCOMES_LOG` with mode 0600 and one line; a second appends
- [ ] A bad state path, a missing `python3`, an unwritable log directory each print one `run-outcome:` stderr line and exit 0
- [ ] `record-validate` through the wrapper writes the state key
- [ ] `partials/tests/run.sh` lists `run-outcome.test.sh` and it passes with executed cases > 0 under every installed shell
- [ ] `emit-telemetry.sh` and `check-delegation.sh` are unchanged

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `partials/tests/run-outcome.test.sh`: never-blocks cases | yes |
| BR-11 | test-case | `partials/tests/run.sh` (bash, zsh, sh, dash passes of `run-outcome.test.sh`) | no |
| AC-10 | test-case | `tools/delegate/tests/test_run_outcome.py::test_delegation_tools_untouched` | yes |
| AC-11 | test-case | `partials/tests/run-outcome.test.sh`: log mode 0600 | no |
| AC-14 | test-case | `partials/tests/run.sh` lists `run-outcome.test.sh`, cases > 0 | no |

## Technical Notes

- No `set -e`, no `local`, no `[[`, no `mktemp -t` (BR-11). Resolve the module as `$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/run_outcome.py`.
- Capture the line in a variable, then append with `printf '%s\n' "$line" >>"$LOG"` only when it is non-empty and rc was 0.
- `AC-10`'s test asserts `git diff --quiet origin/main -- tools/delegate/emit-telemetry.sh tools/delegate/check-delegation.sh` when a git checkout is present and skips otherwise.
