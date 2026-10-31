---
id: TASK-210
title: "Adapter schema 3 and the TOML scanner"
status: complete
parent: REQ-655
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

Teach the loader schema 3 and add the fail-closed TOML scanner BR-5 specifies.

## Files to Create/Modify

- `tools/adlc/harness_adapter.py` — schema 3, the `config` surface, the new capability, doctor-row and format fields
- `tools/adlc/toml_merge.py` — new: scan, merge, union
- `tools/adlc/tests/test_toml_merge.py` — new

## Acceptance Criteria

- [ ] Schema 1 and 2 adapters load unchanged; a schema 3 field under an older version is refused, named
- [ ] `sandbox_can_reach_common_gitdir` removed from a schema 3 adapter is refused, named
- [ ] Every fail-closed construct leaves the file byte-identical and names the construct

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | tools/adlc/tests/test_toml_merge.py::test_merge_keeps_every_other_key | yes |
| BR-1 | test-case | tools/adlc/tests/test_harness_codex.py::test_loader_refuses_unknown_key_and_missing_gitdir_field | no |
| AC-5 | test-case | tools/adlc/tests/test_toml_merge.py::test_each_fail_closed_construct | yes |

## Technical Notes

ADR-7. Python 3.9, so no `tomllib`. New keys go above the first header, and the output is re-classified before it is returned.
