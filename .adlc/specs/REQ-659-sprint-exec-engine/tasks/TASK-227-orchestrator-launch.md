---
id: TASK-227
title: "Pre-flight, working copies, launch, exit and the plan"
status: complete
parent: REQ-659
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-222, TASK-223, TASK-224, TASK-225, TASK-226]
repo: adlc-toolkit
---

## Description

The supervisor up to the halt: pre-flight, working copies, launch, reap, exit checks, plan,
dashboard, abort.

## Files to Create/Modify

- `tools/adlc/sprint_exec.py` — new
- `tools/adlc/exec_gates.py` — new: exit checks, plan, deploy plan and surface
- `tools/adlc/adlc.py` — the subcommand row
- `tools/delegate/run_outcome.py` — engine `exec`
- `tools/adlc/tests/fake_harness/exec_harness.py`, `tools/adlc/tests/exec_helpers.py`, `tools/adlc/tests/test_exec_launch.py` — tests

## Acceptance Criteria

- [x] AC-1 to AC-3 hold on the fake harness, with the real-model run recorded as owed
- [x] Each AC-9 exit is classified as written
- [x] Each pre-flight refusal starts no process

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_exec_launch.py::test_engine_selection` | yes |
| BR-2 | test-case | `tools/adlc/tests/test_exec_launch.py::test_plain_shell_verbs` | yes |
| BR-4 | test-case | `tools/adlc/tests/test_exec_launch.py::test_working_copy` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_exec_launch.py::test_trust_recorded` | yes |
| BR-9 | test-case | `tools/adlc/tests/test_exec_launch.py::test_state_ownership` | yes |
| BR-15 | test-case | `tools/adlc/tests/test_exec_launch.py::test_exit_classification` | yes |
| BR-16 | test-case | `tools/adlc/tests/test_exec_launch.py::test_plan` | yes |
| BR-20 | test-case | `tools/adlc/tests/test_exec_launch.py::test_abort` | yes |
| AC-1 | test-case | `tools/adlc/tests/test_exec_launch.py::test_two_reqs` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_exec_launch.py::test_forbidden_flag_refused` | yes |
| AC-3 | test-case | `tools/adlc/tests/test_exec_launch.py::test_two_reqs` | yes |
| AC-9 | test-case | `tools/adlc/tests/test_exec_launch.py::test_exit_classification` | yes |
| AC-12 | test-case | `tools/adlc/tests/test_exec_launch.py::test_engine_selection` | yes |
| AC-13 | test-case | `tools/adlc/tests/test_exec_launch.py::test_trust_recorded` | yes |
| AC-17 | test-case | `tools/adlc/tests/test_exec_launch.py::test_child_env_and_denied` | yes |
| AC-18 | test-case | `tools/adlc/tests/test_exec_launch.py::test_protection_preflight` | yes |
| AC-19 | test-case | `tools/adlc/tests/test_exec_launch.py::test_no_session_id` | yes |
| AC-20 | test-case | `tools/adlc/tests/test_exec_launch.py::test_cross_repo` | yes |
| AC-27 | test-case | `tools/adlc/tests/test_exec_launch.py::test_direct_push_detection` | no |
| AC-28 | test-case | `tools/adlc/tests/test_exec_launch.py::test_halt_record` | yes |
| AC-33 | test-case | `tools/adlc/tests/test_exec_launch.py::test_straggler_sweep` | yes |
| AC-35 | test-case | `tools/adlc/tests/test_exec_launch.py::test_child_env_and_denied` | yes |
| AC-36 | test-case | `tools/adlc/tests/test_exec_launch.py::test_first_parent_check` | yes |

## Technical Notes

ADR-1, ADR-2, ADR-3. No code compares a harness name.
