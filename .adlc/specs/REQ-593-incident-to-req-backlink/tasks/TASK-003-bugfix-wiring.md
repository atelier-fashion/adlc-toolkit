---
id: TASK-003
title: "Wire attribution derivation into /bugfix Phase 2"
status: complete
parent: REQ-593
created: 2026-08-31
updated: 2026-08-31
dependencies: [TASK-001, TASK-002]
---

## Description

Add the derive → present → record step to `/bugfix` Phase 2, after root-cause validation
produces the file/line set. Implements BR-3 (advisory, operator selects one or more),
BR-7 (benign `none` path) and BR-8 (per-repo derivation).

## Files to Create/Modify

- `bugfix/SKILL.md` — modify; new step 6 in Phase 2

## Acceptance Criteria

- [ ] Partial is sourced with the two-level fallback and called **in the same fenced block**
      (the `cross-fence-fn` lint rule)
- [ ] 0 candidates → `attribution: none`, exactly **one** stderr line naming the reason,
      `/bugfix` continues to Phase 3 (AC-7, BR-7)
- [ ] 1 candidate → `introduced_by: [REQ-xxx]`, `attribution: derived` (AC-1, AC-2, AC-3, AC-4)
- [ ] 2+ candidates → present all, write nothing until the operator selects; selecting two
      writes a two-element array (AC-9, BR-3)
- [ ] Derivation is per-repo, keyed off the bug's `repo:`/`touched_repos:` frontmatter, each
      against that repo's own history; validation still resolves against the primary (BR-8, AC-13)
- [ ] Never fabricates an id; a REQ with no spec directory is dropped (AC-8)
- [ ] `python3 tools/lint-skills/check.py` exits 0

## Technical Notes

Phase 2 already ends with "Update the bug report with the validated findings" — the new
step slots in immediately after, because it consumes the validated file/line set.

The multi-candidate case is a **halt for operator input**, consistent with LESSON-483
(a detected miss must refuse, not fall back to the closest guess). Do not auto-union.
