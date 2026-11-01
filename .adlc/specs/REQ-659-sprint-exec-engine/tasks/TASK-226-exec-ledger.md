---
id: TASK-226
title: "Run directories, the ledger and tokens"
status: complete
parent: REQ-659
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

BR-10's storage half.

## Files to Create/Modify

- `tools/adlc/exec_ledger.py` — new
- `tools/adlc/tests/test_exec_ledger.py` — tests

## Acceptance Criteria

- [x] Run directories are 128-bit random, 0700, under `$XDG_STATE_HOME`
- [x] Every ledger write replaces the file
- [x] An unaccounted ledger is reported

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-10 | test-case | `tools/adlc/tests/test_exec_ledger.py` | yes |
| AC-33 | test-case | `tools/adlc/tests/test_exec_ledger.py::test_run_dir_and_ledger` | yes |

## Technical Notes

ADR-4.
