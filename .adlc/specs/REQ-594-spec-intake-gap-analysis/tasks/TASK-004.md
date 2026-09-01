---
id: TASK-004
title: "Document intake in README, partials/README, and toolkit context"
status: complete
parent: REQ-594
created: 2026-08-31
updated: 2026-08-31
dependencies: [TASK-003]
repo: adlc-toolkit
---

## Description

Discoverability. ADR-1 chose to extend `/spec` rather than add an `/intake` skill, and
explicitly accepted the cost: the feature is only findable if it is documented. This task
pays that.

## Files to Create/Modify

- `README.md` — the `--intake` flag in the skill catalog entry for `/spec`
- `partials/README.md` — `intake.sh` under "Sourceable partial"
- `.adlc/context/architecture.md` — intake in the cross-cutting dependencies

## Acceptance Criteria

- [ ] `README.md`'s `/spec` catalog entry documents the `--intake` flag and the two implicit triggers (a file path, or input over 25 lines).
- [ ] `partials/README.md` documents `intake.sh` in the "Sourceable partial" section, listing the four functions and their return-code contracts, matching the depth of the existing `delegate-gate.sh` and `forge.sh` entries.
- [ ] `.adlc/context/architecture.md` gains a cross-cutting-dependency entry for intake naming the segment budget and the gap-destination model, in the style of the existing REQ-482/483/485/520 entries.
- [ ] Documentation states the segment budget (8000 lines / 40 segments) so an operator hitting the refusal can understand it without reading the source.
- [ ] No documentation claims `/proceed` or `/sprint` invokes `/spec` — no such caller exists.
- [ ] `sh tools/lint-skills/check.sh` exits 0.

## Technical Notes

`.adlc/context/architecture.md` is the toolkit's own context file, read by every skill
at invocation. Keep the new entry to the same one-paragraph density as its neighbors —
this file is loaded into context constantly and bloat is a real cost.

Do not re-enumerate the changelog in the overview (LESSON-019 — enumerations rot).
`VERSION` and `CHANGELOG.md` stay authoritative for what shipped.
