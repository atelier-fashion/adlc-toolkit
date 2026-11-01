---
id: TASK-228
title: "Approval, one-way moves and close-out"
status: complete
parent: REQ-659
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-227]
repo: adlc-toolkit
---

## Description

Everything after the gate.

## Files to Create/Modify

- `tools/adlc/sprint_exec.py` — approve, reject, answer, the worker
- `tools/adlc/exec_gates.py` — PR verification, rebase, chore-PR gate, deploy
- `tools/adlc/tests/test_exec_approve.py` — tests

## Acceptance Criteria

- [x] AC-4 runs in the stated order on the fake harness and the mock forge
- [x] Each doctored fixture in AC-10, AC-21, AC-25 and AC-31 is refused with nothing merged
- [x] A clean fixture merges with `--match-head-commit`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-10 | test-case | `tools/adlc/tests/test_exec_approve.py::test_approval_guards` | yes |
| BR-11 | test-case | `tools/adlc/tests/test_exec_approve.py::test_binding` | yes |
| BR-12 | test-case | `tools/adlc/tests/test_exec_approve.py::test_rebase` | yes |
| BR-13 | test-case | `tools/adlc/tests/test_exec_approve.py::test_deploy` | yes |
| BR-14 | test-case | `tools/adlc/tests/test_exec_approve.py::test_close_out` | yes |
| BR-25 | test-case | `tools/adlc/tests/test_exec_approve.py::test_config_isolation` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_exec_approve.py::test_happy_path` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_exec_approve.py::test_reject` | yes |
| AC-6 | test-case | `tools/adlc/tests/test_exec_approve.py::test_queue` | yes |
| AC-7 | test-case | `tools/adlc/tests/test_exec_approve.py::test_rebase` | yes |
| AC-8 | test-case | `tools/adlc/tests/test_exec_approve.py::test_answer` | yes |
| AC-10 | test-case | `tools/adlc/tests/test_exec_approve.py::test_doctored_state` | yes |
| AC-15 | test-case | `partials/tests/exec-engine.test.sh` | yes |
| AC-16 | test-case | `tools/adlc/tests/test_exec_approve.py::test_approval_guards` | yes |
| AC-21 | test-case | `tools/adlc/tests/test_exec_approve.py::test_chore_gate_fields` | yes |
| AC-22 | test-case | `tools/adlc/tests/test_exec_approve.py::test_deploy` | yes |
| AC-24 | test-case | `tools/adlc/tests/test_exec_approve.py::test_planted_partials_and_gate_change` | yes |
| AC-25 | test-case | `tools/adlc/tests/test_exec_approve.py::test_binding` | yes |
| AC-31 | test-case | `tools/adlc/tests/test_exec_approve.py::test_chore_gate_paths` | yes |
| AC-32 | test-case | `tools/adlc/tests/test_exec_approve.py::test_deployable_refs` | yes |
| AC-34 | test-case | `tools/adlc/tests/test_exec_approve.py::test_rebase` | yes |
| AC-37 | test-case | `tools/adlc/tests/test_exec_approve.py::test_config_isolation` | yes |

## Technical Notes

Every merge is pinned. Every step reads the ledger plan, never state.
