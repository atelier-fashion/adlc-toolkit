---
id: TASK-224
title: "Prompt assembly, anchors and the runtime scan"
status: complete
parent: REQ-659
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

BR-6, BR-7, the close-out prompt of BR-14, and BR-24.

## Files to Create/Modify

- `tools/adlc/exec_prompt.py` — new
- `tools/adlc/tests/test_exec_prompt.py` — build test over the real skills, and the AC-30 fixtures

## Acceptance Criteria

- [x] The pipeline prompt from the real tree passes the scan, with every empty-allowlist token absent
- [x] A changed anchor refuses the build, naming it
- [x] AC-30's alterations refuse; a substring of an allowlisted line refuses; the exact line passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_pipeline_prompt_real_tree` | yes |
| BR-7 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_gate_text` | no |
| BR-24 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_scan_refusals` | yes |
| AC-1 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_pipeline_prompt_real_tree` | yes |
| AC-30 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_scan_refusals` | yes |

## Technical Notes

ADR-7. Sources come from ToolkitRoot and the primary path, never a working copy.
