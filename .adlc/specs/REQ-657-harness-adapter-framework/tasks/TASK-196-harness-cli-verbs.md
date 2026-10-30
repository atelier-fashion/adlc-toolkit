---
id: TASK-196
title: "adlc harness install, render, doctor, drift; write modes; parity check; render-currency"
status: complete
parent: REQ-657
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-195]
repo: adlc-toolkit
---

## Description

The `adlc harness` verbs, the create/merge write modes, the toolkit parity check,
the consumer drift classification and the doctor checks (BR-2, BR-3, BR-11, BR-13,
BR-15).

## Files to Create/Modify

- `tools/adlc/harness.py` — install, render, doctor, drift verbs
- `tools/adlc/harness_render.py` — write modes, check, drift
- `tools/adlc/harness_doctor.py` — render-currency, doctor_rows
- `tools/adlc/checks.py` — render-currency:<name> registration
- `tools/adlc/adlc.py` — harness help string
- `tools/adlc/tests/test_harness_framework.py` — CLI cases

## Acceptance Criteria

- [ ] AC-2, AC-9 (merge), AC-11, AC-13 hold
- [ ] `grep -rn 'fake' tools/adlc/*.py` and `grep -rn 'if harness == ' tools/adlc` are empty

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/adlc/tests/test_harness_framework.py::test_render_dry_run_and_idempotent` | yes |
| BR-3 | test-case | `tools/adlc/tests/test_harness_framework.py::test_install_claude_nothing_to_write` | yes |
| BR-13 | test-case | `tools/adlc/tests/test_harness_framework.py::test_render_check_parity` | yes |
| BR-15 | test-case | `tools/adlc/tests/test_harness_framework.py::test_doctor_render_currency` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_harness_framework.py::test_render_dry_run_and_idempotent` | yes |
| AC-9 | test-case | `tools/adlc/tests/test_harness_framework.py::test_merge_write_mode` | yes |
| AC-11 | test-case | `tools/adlc/tests/test_harness_framework.py::test_render_check_parity` | yes |
| AC-13 | test-case | `tools/adlc/tests/test_harness_framework.py::test_doctor_rows` | yes |

## Technical Notes

ADR-11, ADR-13. Project root from cwd; toolkit assets from the script (LESSON-397).
