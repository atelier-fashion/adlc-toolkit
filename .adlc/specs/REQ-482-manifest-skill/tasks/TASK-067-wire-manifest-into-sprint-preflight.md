---
id: TASK-067
title: "Wire /manifest 'In-Flight (cross-session)' section into /sprint pre-flight"
status: draft
parent: REQ-482
created: 2026-06-04
updated: 2026-06-04
dependencies: [TASK-065]
---

## Description

Add a separate "In-Flight (cross-session)" manifest section to the `/sprint` Step 2 pre-flight, distinct from the existing worktree-collision eligibility table, so a sprint operator sees cross-session work and coarse overlaps across the whole batch before launching.

## Files to Create/Modify

- `sprint/SKILL.md` — add the advisory cross-session manifest section to the Step 2 pre-flight

## Acceptance Criteria

- [ ] `/sprint` Step 2 pre-flight renders a separate "In-Flight (cross-session)" section after the existing eligibility table (sprint/SKILL.md ~L129), before the lineup confirmation. (BR-9, OQ-4)
- [ ] The manifest is built ONCE for the batch and reused across all candidate REQs (not once per REQ). (BR-14)
- [ ] Includes both PR-derived and branch-only entries; the sprint's own batch REQs are marked as self. (BR-3, BR-12, BR-13)
- [ ] Coarse overlaps among in-flight REQs are flagged as advisory only; no eligibility/scheduling change in this REQ. (BR-8)
- [ ] The existing worktree-collision eligibility check and two-engine selection behavior are unchanged.
- [ ] `python3 tools/lint-skills/check.py` passes clean.

## Technical Notes

- Insertion point (architecture-mapper): after the existing pre-flight table (sprint/SKILL.md ~L129/131), before "Remove ineligible REQs"/lineup confirmation.
- Keep it advisory: the section informs, it does NOT mark REQs ineligible or reorder them (enforcement is the follow-on REQ).
- Account for the current two-engine (workflow + legacy) structure — the section is engine-agnostic (pre-flight runs before engine dispatch).
