---
id: TASK-012
title: "Write wrapup lesson capturing cross-reference rot + topology-hazard-inheritance pattern"
status: draft
parent: REQ-381
created: 2026-05-04
updated: 2026-05-04
dependencies: [TASK-010, TASK-011]
---

## Description

Create a wrapup lesson at `.adlc/knowledge/lessons/LESSON-xxx-...md` capturing the three content blocks required by REQ-381 BR-6:

(a) the cross-reference rot at `bugfix/SKILL.md:128` (the dangling `mirrors /proceed Phase 7.5` reference) and how it was found — REQ-380's architecture-phase scope carve-out left it behind;

(b) the topology-hazard-inheritance pattern: when one skill removes an anti-pattern (here, `/proceed` Phase 7.5 in REQ-380), audit sibling skills (here, `/bugfix`) for the same code path before considering the cleanup complete; and

(c) the fact that REQ-380 + REQ-381 together complete the canary-removal cleanup, plus a recommendation that future deferred-fix carve-outs in any architecture-phase scope-narrowing be tracked as explicit follow-up REQ entries at architecture time so they don't drift.

## Files to Create/Modify

- `.adlc/knowledge/lessons/LESSON-xxx-bugfix-canary-topology-deferred-followup.md` — new lesson file. Use the lesson template at `~/.claude/skills/templates/lesson-template.md`. Number the lesson by:
  1. If `.adlc/.next-lesson` exists in this repo, read it, use the value, and write `value+1` back.
  2. If it doesn't exist, scan `.adlc/knowledge/lessons/` (which currently doesn't exist as a directory in this repo — the toolkit hasn't tracked lessons before) for any existing `LESSON-xxx-` files; use the next number (start from `LESSON-001` if none exist), and write `value+1` to a newly-created `.adlc/.next-lesson` counter.
  3. The directory `.adlc/knowledge/lessons/` may need to be created as part of this task — that's expected; this is the toolkit's first lesson.

  Frontmatter MUST include:
  - `id: LESSON-xxx`
  - `title:` a short hook
  - `domain: adlc`
  - `component: skills/bugfix`
  - `tags: [topology-mismatch, cross-reference-rot, deferred-followup, canary, phase-removal, follows-REQ-380]`
  - `created: 2026-05-04`
  - `updated: 2026-05-04`

  Body must contain the three content blocks above as named sections so future `/spec` retrieval can surface them via tag overlap.

## Acceptance Criteria

- [ ] File exists at `.adlc/knowledge/lessons/LESSON-xxx-bugfix-canary-topology-deferred-followup.md` (where xxx is the actual allocated number).
- [ ] Frontmatter has all required fields including the tags listed above.
- [ ] Body contains three named sections (or equivalent clearly-labeled blocks) covering (a), (b), (c).
- [ ] If the toolkit didn't previously have a `.adlc/knowledge/lessons/` directory or `.adlc/.next-lesson` counter, both are created as part of this task.

## Technical Notes

- This is the toolkit's first lesson — the `.adlc/knowledge/lessons/` directory likely doesn't exist yet. Create it.
- The lesson should be terse and operator-facing — three short sections, not a long write-up. Future readers care about the pattern, not the narrative.
- After writing, update `.adlc/.next-lesson` to the next integer.
- This task depends on TASK-010 and TASK-011 because the lesson references the actual edits made by those tasks; writing it before they're done risks the lesson describing changes that don't exist yet.
