---
id: TASK-011
title: "Audit /canary skill for /bugfix-as-caller cross-references; update post-REQ-381 note"
status: complete
parent: REQ-381
created: 2026-05-04
updated: 2026-05-04
dependencies: []
---

## Description

Audit `canary/SKILL.md` for any reference to `/bugfix` as a caller and update the existing post-REQ-380 manual-only annotation to also acknowledge the `/bugfix` removal landing in REQ-381. Closes REQ-381 BR-5.

## Files to Create/Modify

- `canary/SKILL.md` — line ~65 currently reads:
  ```
  **Note (post-REQ-380)**: `/canary` is no longer auto-invoked from `/proceed`. Operators run it manually when a production canary is needed.
  ```
  Update to:
  ```
  **Note (post-REQ-380, REQ-381)**: `/canary` is no longer auto-invoked from `/proceed` (REQ-380) or `/bugfix` (REQ-381). Operators run it manually when a production canary is needed.
  ```
  Then grep the rest of the file for any other reference to `/bugfix` or `bugfix` as a caller (excluding generic prose like "after fixing a bug"). Remove or annotate any such reference. If the grep returns nothing else, BR-5 is vacuously satisfied beyond the note update.

## Acceptance Criteria

- [ ] `canary/SKILL.md` line containing the post-REQ-380 note now mentions REQ-381 and `/bugfix`.
- [ ] `grep -in '/bugfix\|bugfix' canary/SKILL.md` returns no caller-reference lines beyond the updated note.
- [ ] No other behavior or step in `canary/SKILL.md` is changed.

## Technical Notes

- This is a tiny, targeted edit. If the grep audit returns more matches than expected, surface them rather than silently rewriting.
- No tests to run.
