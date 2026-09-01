---
id: TASK-005
title: "Document the attribution surface in CHANGELOG and architecture context"
status: complete
parent: REQ-593
created: 2026-08-31
updated: 2026-08-31
dependencies: [TASK-003, TASK-004]
---

## Description

Record what shipped so the next REQ can find it without reading the diff.

## Files to Create/Modify

- `CHANGELOG.md` — modify; entry for the attribution surface
- `.adlc/context/architecture.md` — modify; one cross-cutting-dependency bullet for
  `partials/attribution.sh`, mirroring the existing forge/id-alloc entries

## Acceptance Criteria

- [ ] CHANGELOG entry names the new partial, the two bug-template fields, and both call sites
- [ ] architecture.md gains an "Incident attribution (REQ-593)" bullet in the cross-cutting
      dependencies list, in the same voice as the neighbouring entries
- [ ] No enumeration that will rot (LESSON-019) — describe the mechanism, not a file census

## Technical Notes

Keep the architecture bullet short and mechanism-focused. The existing entries
(forge adapter, ordering enforcement, atomic counters) are the model for length and tone.
