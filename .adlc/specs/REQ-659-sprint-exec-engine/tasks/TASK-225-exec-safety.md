---
id: TASK-225
title: "Validators, neutral environment, manifest, checksums"
status: complete
parent: REQ-659
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

BR-17 and BR-23 as one module every other module calls through.

## Files to Create/Modify

- `tools/adlc/exec_safety.py` — new
- `tools/adlc/tests/test_exec_safety.py` — tests

## Acceptance Criteria

- [x] A sentinel planted in a hook, in repo config, in `~/.gitconfig` or `~/.ssh/config` after launch never runs
- [x] A `git push -u` by the model does not trip the checksum
- [x] An edit to an installed partial or a resolved binary fails before the next source or exec

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-17 | test-case | `tools/adlc/tests/test_exec_safety.py::test_validators` | yes |
| BR-23 | test-case | `tools/adlc/tests/test_exec_safety.py` | yes |
| AC-23 | test-case | `tools/adlc/tests/test_exec_safety.py::test_planted_hook_and_config` | yes |
| AC-29 | test-case | `tools/adlc/tests/test_exec_safety.py::test_filters_and_snapshots` | yes |

## Technical Notes

Environment, not `-c` flags, because partials spawn git themselves. `credential.helper` needs an
empty first value to clear what the repo config planted.
