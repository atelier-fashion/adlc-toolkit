---
id: TASK-270
title: "Run-outcome vocabulary: the `rejected` terminal and the `aborted` reason, in the emitter and in every reader"
status: draft
parent: REQ-719
repo: adlc-toolkit
created: 2026-11-20
updated: 2026-11-20
dependencies: []
---

## Description

Add the two values to the run-outcome log's vocabulary and to every reader of it (architecture ADR-5). No caller passes them yet: TASK-275 makes the exec engine write them.

## Files to Create/Modify

- `tools/delegate/run_outcome.py` — `TERMINALS` gains `rejected`, `BLOCKED_REASONS` gains `aborted`. `build_record` raises `UsageError` for `rejected` with an engine other than `exec`, and gives a `rejected` record an empty `blocked_reason` whatever `closeOut` says.
- `tools/delegate/emit-run-outcome.sh` — header comment only: the two new values.
- `tools/delegate/check-run-outcomes.sh` — the window report counts `rejected` and prints it as a new last column, after `top_classes`. Header comment updated.
- `tools/delegate/tests/test_run_outcome.py` — new cases.
- `tools/delegate/tests/test_check_run_outcomes.py` — new cases.
- `partials/tests/run-outcome.test.sh` — `rejected` with `--engine legacy` appends nothing, under every shell.
- `analyze/SKILL.md` — the harness-fidelity header and row gain `rejected` as the last column.
- `proceed/phases-telemetry.md` — one sentence after the R5 fence: `rejected` and the reason `aborted` are written by the exec engine only. The R5 fence and the paragraph above it stay byte-identical.
- `tools/delegate/README.md` — the vocabulary, where it lists it.

## Acceptance Criteria

- [ ] `run_outcome.py emit --terminal rejected --engine exec` prints one line with `terminal` `rejected` and an empty `blocked_reason`, also when the state's `closeOut.status` is `failed`.
- [ ] `--terminal rejected` with `--engine solo`, `legacy` or `workflow` exits 2 and prints no line. Through `emit-run-outcome.sh` the log file is unchanged and the wrapper exits 0.
- [ ] `--terminal failed --reason aborted` records `blocked_reason` `aborted`, not `other`.
- [ ] Over a log holding lines with and without the new values, `check-run-outcomes.sh` prints the old header's thirteen columns in their old positions with their old values, and `rejected` as column fourteen. A `rejected` line adds to `runs` and to no other count.
- [ ] A log with only older lines prints `0` in the new column and parses as before.
- [ ] `workflows/adlc-sprint.workflow.js`'s `TERMINAL.state` enum is unchanged, and a test reads it.
- [ ] `tools/adlc/exec_prompt.py`'s telemetry anchors still match exactly once (run `tools/adlc/tests/test_exec_prompt.py`).

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-18 | test-case | `tools/delegate/tests/test_run_outcome.py::test_req719_rejected_is_an_exec_only_terminal` | yes |
| BR-19 | test-case | `tools/delegate/tests/test_run_outcome.py::test_req719_aborted_is_a_reason_of_its_own` | no |
| BR-20 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_req719_rejected_has_its_own_last_column` | yes |
| BR-21 | test-case | `tools/delegate/tests/test_run_outcome.py::test_req719_workflow_terminal_enum_is_unchanged` | no |
| AC-14 | test-case | `tools/delegate/tests/test_run_outcome.py::test_req719_rejected_is_an_exec_only_terminal` | yes |
| AC-16 | test-case | `tools/delegate/tests/test_check_run_outcomes.py::test_req719_rejected_has_its_own_last_column` | yes |

## Technical Notes

- `normalize_blocked_reason` returns an exact member of `BLOCKED_REASONS` as is, so adding `aborted` to the tuple is enough.
- `build_record`'s `else` arm (299-301) would give `rejected` a `close-out-failed` reason. Give `rejected` its own arm.
- `check-run-outcomes.sh` is POSIX awk under bash, zsh, `/bin/sh` and dash. Keep the printf and the header in step.
- `sprint/SKILL.md`'s Recurrence step reads finding classes only and needs no change here.
- Do not edit a fence body in `analyze/SKILL.md` or `proceed/phases-telemetry.md`: a fence's id is a hash of its body, and the census goldens belong to TASK-273 and TASK-274.
