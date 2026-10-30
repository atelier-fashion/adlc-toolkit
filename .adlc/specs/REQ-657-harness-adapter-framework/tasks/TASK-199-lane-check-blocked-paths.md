---
id: TASK-199
title: "Lane check blocks harness, permissions, hooks and settings paths"
status: complete
parent: REQ-657
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Four blocked paths so a lite PR cannot widen an allowlist or soften a hook (BR-14).

## Files to Create/Modify

- `tools/adlc/lane_check.py` — DEFAULT_BLOCKED_PATHS
- `tools/adlc/tests/test_lane_check.py` — REQ-657 cases
- `partials/lane-check.md` — documented defaults

## Acceptance Criteria

- [ ] The five AC-12 paths report blocked-path; only the four globs are added

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-14 | test-case | `tools/adlc/tests/test_lane_check.py::test_req657_blocked_globs` | yes |
| AC-12 | test-case | `tools/adlc/tests/test_lane_check.py::test_req657_blocked_globs` | yes |

## Technical Notes

ADR-14.
