---
id: TASK-117
title: "/wrapup escalation lesson and /status lane columns"
status: draft
parent: REQ-652
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-115]
---

## Description

Escalations become lessons and the lane is visible in status (BR-14, BR-15; architecture ADR-12).

## Files to Create/Modify

- `wrapup/SKILL.md` — Step 4: for each `lane.escalations` entry (or the spec's `lane_escalated` when state is unavailable), write a `kind: process` lesson naming the trigger, the triage reason that was wrong, and the rule to change, through the existing write point and `adlc_lesson_check`; close-out evidence list gains `lane.escalations`; summary gains a `Lane` line.
- `status/SKILL.md` — Requirements Summary and Active Pipelines gain Lane and Escalated columns (absent ⇒ full); an Escalations section modelled on Conflict Resolutions.

## Acceptance Criteria

- [ ] `/wrapup` writes no escalation lesson for a REQ that stayed lite or was always full.
- [ ] The capture-rules block stays byte-identical with `bugfix/SKILL.md`, and the delegated `--question` lines are untouched.
- [ ] `sh tools/lint-skills/check.sh --root .` is clean (`lesson-check-order`, `lesson-rules-parity`, `lesson-question-coverage`).

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-14 | structural-check | `tools/lint-skills`: lesson-check-order, lesson-rules-parity over `wrapup/SKILL.md` | yes |
| AC-11 | structural-check | `tools/lint-skills`: lane-vocabulary over `wrapup/SKILL.md` | yes |
| BR-15 | structural-check | `tools/lint-skills`: lane-vocabulary over `status/SKILL.md` | no |
| AC-12 | structural-check | `tools/lint-skills`: balance over `status/SKILL.md` | no |

## Technical Notes

- The escalation lesson cites its evidence (the escalation entry), which close-out mode already requires of every lesson.
- Reuse `/status`'s inline `python3` JSON reader pattern from Conflict Resolutions; absent `lane` prints nothing.
