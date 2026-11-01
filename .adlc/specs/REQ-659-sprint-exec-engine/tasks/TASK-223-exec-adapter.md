---
id: TASK-223
title: "The exec block, its loader validation, and exec_adapter"
status: complete
parent: REQ-659
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

The `claude` exec block in `harness/claude.yml`, closed-schema validation, and the module that
turns it into argv, rules, env and exit classes.

## Files to Create/Modify

- `harness/claude.yml` — the `exec` block
- `tools/adlc/harness_adapter.py` — validate `exec` when `exec_schema_version` is present
- `tools/adlc/exec_adapter.py` — new
- `tools/adlc/README.md` — the adapter contract, including the trust contract for REQ-662
- `tools/adlc/tests/test_exec_adapter.py` — tests

## Acceptance Criteria

- [x] `--disallowedTools` is a superset of the deny tier and holds every BR-8 minimum
- [x] No forbidden flag can reach an argv from config or the CLI
- [x] `working_copy` accepts the scalar and the `{strategy}` spelling
- [x] An unknown exec key is a loud loader error

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_exec_block_validates` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_deny_superset` | yes |
| BR-21 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_exit_class` | yes |
| BR-22 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_child_env` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_forbidden_flags` | yes |
| AC-26 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_deny_superset` | yes |

## Technical Notes

No code compares a harness name (conventions.md). Everything claude-specific is adapter data.
