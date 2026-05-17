---
id: TASK-048
title: "Capture LESSON (CANCELLED — superseded by main's LESSON-019)"
status: cancelled
parent: REQ-435
created: 2026-05-16
updated: 2026-05-16
dependencies: [TASK-047]
repo: adlc-toolkit
---

## Description

**Cancelled.** This task would have captured a LESSON about directory-walk
skip lists no-op'ing from inside a skipped dir. That generalization is
already on `main` as
`LESSON-019-presence-guards-rot-when-indirection-moves` (point #2),
committed by REQ-433/REQ-436. Capturing a second lesson would duplicate
existing knowledge and re-collide the `.adlc/.next-lesson` counter. No
lesson file is created and `.adlc/.next-lesson` is left untouched.

## Acceptance Criteria

- [x] No `LESSON-*.md` created by REQ-435.
- [x] `.adlc/.next-lesson` unchanged from `main` (no counter mutation).

## Technical Notes

- Knowledge is preserved upstream; the supersession itself is recorded in
  this REQ's requirement.md / architecture.md for the audit trail.
