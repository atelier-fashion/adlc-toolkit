---
id: TASK-002
title: "Cross-reference /init's vendored-surface list to /template-drift's checked-surface list"
status: complete
parent: REQ-525
created: 2026-06-12
updated: 2026-06-12
dependencies: []
---

## Description

Add the producer half of BR-4 to `init/SKILL.md`: a single, anchored note at the vendored-surface
enumeration (Step 6 / the `.adlc/` directory-tree comment) that cross-references `/template-drift`'s
checked-surface list, plus a stable marker block the toolkit parity check (TASK-003) greps. The edit is
deliberately minimal and localized to reduce overlap with REQ-522, which also edits `init/SKILL.md`.

## Files to Create/Modify

- `init/SKILL.md` — one anchored cross-reference note + a stable "Vendored sync surfaces" marker block
  listing the four copied surfaces (templates, partials, ethos, workflow-runtime) and pointing to
  `/template-drift` for drift detection of each.

## Acceptance Criteria

- [ ] BR-4 (producer half): `/init`'s vendored-surface list is stated in one place with a stable marker
      and explicitly cross-references `/template-drift` as the drift-detection tool for those surfaces.
- [ ] The note makes clear that adding a new vendored surface to `/init` requires adding a matching check
      to `/template-drift` (the gap the parity check enforces).
- [ ] The edit is confined to the vendored-surface region (Step 6 / directory tree); no changes to
      delegation, telemetry, or other regions REQ-522 may touch.
- [ ] `python3 tools/lint-skills/check.py --root .` reports no new findings against the edited SKILL.md.

## Technical Notes

- The marker block format must match what TASK-003's parser expects (a fenced list keyed by a stable
  comment marker, e.g. `<!-- sync-surfaces: init -->`). Coordinate the exact marker string with TASK-003;
  pick a self-documenting marker and use the identical one in both files.
- Keep the four-surface set here aligned with the five-surface vocabulary in `/template-drift`
  (init copies four physical surfaces; `workflow-test-landmine` is a drift *symptom* checked only by
  `/template-drift`, not a thing `/init` copies — note this distinction so the parity check accounts for it).
