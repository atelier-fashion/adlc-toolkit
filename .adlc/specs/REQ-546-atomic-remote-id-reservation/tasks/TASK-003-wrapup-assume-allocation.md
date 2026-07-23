---
id: TASK-003
title: "Route /wrapup ASSUME allocation through adlc_alloc_id assume"
status: draft
parent: REQ-546
created: 2026-07-23
updated: 2026-07-23
dependencies: [TASK-001]
---

## Description

Replace the bespoke inline ASSUME counter block in `wrapup/SKILL.md` with a call
to the reservation-aware `adlc_alloc_id assume` (BR-12), so concurrent /wrapup
runs across clones of one repo cannot double-allocate an ASSUME id.

## Files to Create/Modify

- `wrapup/SKILL.md`

## Acceptance Criteria

- [ ] The `#### Assumptions Validated or Invalidated` allocation block sources `id-alloc.sh` (two-level fallback) and calls `ASSUME_NUM=$(adlc_alloc_id assume)` in the SAME fenced block, with the parent-context empty-guard.
- [ ] The prose explaining the counter is updated: per-checkout `.adlc/.next-assume` is a cache; `max(remote, local) + 1` supersedes "never re-scan after the counter exists"; the reservation makes it collision-safe across clones.
- [ ] The existing `adlc_alloc_id lesson` fenced usage (Lessons Learned) is untouched (BR-7).
- [ ] `tools/lint-skills/check.py` is clean for `wrapup/SKILL.md`.

## Technical Notes

- Use the canonical usage from the id-alloc.sh header (source-then-call in one
  fence, guard the empty result).
- Keep the LESSON-014 / LESSON-110 rationale references; the mkdir-lock + symlink
  guards now live inside `adlc_alloc_id` for the assume kind.
