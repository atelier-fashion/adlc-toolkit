---
id: TASK-285
title: "Architecture context, changelog, and a full verification run on the final tree"
status: complete
parent: REQ-722
created: 2026-11-24
updated: 2026-11-24
dependencies: [TASK-283, TASK-284]
---
## Description

Record the new Phase-5 member and the `family` key in the project's context docs and
changelog, then run every suite that parses or exercises the changed surfaces on the
final tree.

## Files to Create/Modify

- `.adlc/context/architecture.md` — Phase 5 section: the cross-family reviewer, its skip vocabulary, and where families come from; delegation section: the `family` key
- `CHANGELOG.md` — entry under the next version

## Acceptance Criteria

- [ ] The architecture context names `partials/cross-family-review.sh`, `cross_family.py`, the `crossFamilyReview` record and the two family sources
- [ ] `tools/lint-skills`, `partials/tests/run.sh`, `tools/delegate/tests`, `tools/adlc/tests` (sharded per directory) and `workflows/tests` all pass on the final tree, each reporting a non-zero executed count

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| AC-18 | test-case | `partials/tests/run.sh` (all harnesses), `tools/delegate/tests`, `workflows/tests` | no |
| BR-15 | structural-check | `tools/lint-skills`: full check set over the final tree | no |

## Technical Notes

- `pytest tools` single-process runs over an hour; shard per test directory (memory: toolkit full test runs).
- A zero-collected run (`exit 5`) or `lint-skills` scanning zero files (`exit 255`) fails this task, not passes it.
