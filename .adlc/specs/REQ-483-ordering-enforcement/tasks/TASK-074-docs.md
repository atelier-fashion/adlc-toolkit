---
id: TASK-074
title: "Docs: footprint-block schema + REQ-483 note in architecture context + README"
status: draft
parent: REQ-483
created: 2026-06-04
updated: 2026-06-04
dependencies: [TASK-073]
---

## Description

Document the new enforcement behavior so it's discoverable and the `adlc-footprint` schema is authoritative.

## Files to Create/Modify

- `.adlc/context/architecture.md` — add a one-line REQ-483 "ordering enforcement" note under the cross-session-visibility entry (the deferred ADR from REQ-483 architecture.md)
- `README.md` — note the draft-PR-early + ordering behavior where the `/proceed`/`/sprint`/`/manifest` catalog entries live (no new skill)

## Acceptance Criteria

- [ ] `.adlc/context/architecture.md` gains a concise note: draft-PR-early publishes file footprints; `/manifest` derives a deterministic merge order; a non-mutating trial-merge blocks only real conflicts (lock-free).
- [ ] The `adlc-footprint` block schema is documented where an implementer/reader will find it (architecture context or the `/manifest` skill body), matching what TASK-070 writes and TASK-072 parses.
- [ ] README reflects that `/proceed` opens a draft PR early and `/manifest` now does file-level overlap + ordering.
- [ ] `python3 tools/lint-skills/check.py` passes (README/architecture aren't SKILL.md, but the run must stay clean overall).

## Technical Notes

- Keep it tight — one or two lines each; the spec + architecture.md hold the detail.
- Ensure the schema doc is single-source (don't duplicate the full schema in three places — point to one).
