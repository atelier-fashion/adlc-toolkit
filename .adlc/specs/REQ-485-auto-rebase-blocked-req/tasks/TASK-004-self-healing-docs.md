---
id: TASK-004
title: "Self-healing serialization docs (sprint subsection + architecture context bullet)"
status: draft
parent: REQ-485
created: 2026-06-05
updated: 2026-06-05
dependencies: [TASK-002, TASK-003]
repo: adlc-toolkit
---

## Description

Document the new self-healing behavior so it is discoverable and the
scope/limitations are explicit:

1. **`sprint/SKILL.md`** — add a "Self-healing serialization (REQ-485)"
   subsection that ties together the auto-rebase/resume trigger across both
   engines: the blocker-merged → rebase-held-REQ → resume flow (BR-1/2/3),
   deterministic order + serialization (BR-6), the retry bound + manual fallback
   (BR-10), degrade-safe behavior (BR-7), the within-run scope guard (BR-9,
   cross-session stays manual), and the OQ-5 blocker-failed release. State that
   solo `/proceed` is unchanged (BR-1) and that conflicts are never auto-resolved
   (BR-4).
2. **`.adlc/context/architecture.md`** — add a one-line "Self-healing
   serialization (REQ-485)" bullet to the ordering-enforcement / cross-cutting
   dependencies area, right after the REQ-483 ordering-enforcement bullet.

This task depends on TASK-002 and TASK-003 so the prose matches the implemented
behavior in both engines.

## Files to Create/Modify

- `sprint/SKILL.md` — new "Self-healing serialization (REQ-485)" subsection + "What This Skill Does NOT Do" entries for cross-session/solo scope
- `.adlc/context/architecture.md` — one-line REQ-485 bullet under ordering enforcement

## Acceptance Criteria

- [ ] `sprint/SKILL.md` has a coherent "Self-healing serialization" subsection covering BR-1/2/3/4/6/7/9/10 and OQ-5 at the behavior level (not duplicating TASK-002/003 step prose, but cross-referencing it).
- [ ] The subsection states: solo `/proceed` is unchanged (manual resume); cross-session blocker auto-resume is out of scope for v1 (manual); conflicts are never auto-resolved.
- [ ] `.adlc/context/architecture.md` has a one-line REQ-485 self-healing bullet placed with the REQ-482/REQ-483 coordination bullets.
- [ ] No contradiction with the implemented Step 5 / workflow behavior from TASK-002/003.

## Technical Notes

- Mirror the doc style of the existing REQ-482/REQ-483 cross-cutting bullets in
  architecture.md (one sentence, names the mechanism + scope).
- The "What This Skill Does NOT Do" additions reinforce BR-9 (no cross-session
  watch/poll) and BR-1 (no solo-/proceed auto-resume) so scope creep is fenced.
