---
id: TASK-005
title: "Capture wrapup lesson — Phase 7.5/8a removal + global REQ counter"
req: REQ-380
status: pending
created: 2026-05-04
updated: 2026-05-04
dependencies: [TASK-001, TASK-002, TASK-003, TASK-004]
repo: adlc-toolkit
---

## Files to Modify
- `.adlc/knowledge/lessons/<date>-req-380-drop-phases-and-global-counter.md` (new)

## Acceptance Criteria

- [ ] A new lesson file is created at `.adlc/knowledge/lessons/2026-05-04-req-380-drop-proceed-phases-and-global-counter.md`. (BR-9; ADLC convention is for `/wrapup` to land lessons.)
- [ ] Three required content blocks:
  1. **Topology mismatch driving Phase 7.5 / 8a removal** — feature-branch → prod canary defeats the staging gate; Phase 8a's 30-min staging-tip poll is operator-driven and almost never green at /proceed end-of-feature wall-clock.
  2. **REQ-379 / REQ-380 ship-order rationale** — REQ-379 lands the workflow first; helper script's `already_present` 4-state idempotency keeps the overlap window safe; REQ-380 then removes Phase 8a so the workflow becomes the sole producer.
  3. **Global REQ-counter policy adoption + intentional REQ-264..REQ-379 gap** — fast-forward from REQ-263 to next-slot-above-379 to share counter across repos.
- [ ] Cross-reference atelier-fashion REQ-379's lesson by id.
- [ ] Frontmatter follows the lesson template: id, title, domain, component, tags, req, created.

## Technical Notes

- This task is executed by `/wrapup` in Phase 8 by ADLC convention, not in Phase 4 by `task-implementer`. It is listed here for visibility and to satisfy AC #7 of REQ-380. The dependency chain ensures Phase 4 work lands first so the lesson can reference final commit SHAs and PR URL.
