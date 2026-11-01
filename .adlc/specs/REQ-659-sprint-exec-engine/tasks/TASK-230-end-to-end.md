---
id: TASK-230
title: "The end-to-end fixture under four shells"
status: complete
parent: REQ-659
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-228, TASK-229]
repo: adlc-toolkit
---

## Description

BR-18: launch to cleanup, offline, under every shell, and the rerunnable manual table.

## Files to Create/Modify

- `partials/tests/exec-engine.test.sh` — new
- `partials/tests/run.sh` — one more harness
- `tools/adlc/tests/e2e/claude-exec-manual.sh` — new

## Acceptance Criteria

- [x] AC-11's sequence exits 0 under bash, zsh, `/bin/sh` and dash
- [x] `claude-exec-manual.sh` reproduces the table on a logged-out binary

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-18 | test-case | `partials/tests/exec-engine.test.sh` | yes |
| AC-11 | test-case | `partials/tests/exec-engine.test.sh` | yes |

## Technical Notes

`kill` only PIDs this test started: another runner shares the machine.
