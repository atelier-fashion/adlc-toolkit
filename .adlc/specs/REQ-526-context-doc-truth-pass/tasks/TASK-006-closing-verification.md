---
id: TASK-006
title: "Closing verification sweep — grep the edited docs for the corrected claims"
status: complete
parent: REQ-526
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-001, TASK-002, TASK-003, TASK-004, TASK-005]
repo: adlc-toolkit
---

## Description

BR-6 (Ethos #4 — Verify, Don't Trust): a closing verification greps the edited docs for
the corrected claims so the fix is checkable, not just authored. Run every acceptance
criterion as a mechanical check and confirm each passes. This task gates Phase 4 completion.

## Files to Create/Modify

- None (verification only). If any check fails, the corresponding task's edit is incomplete
  and must be fixed before this task passes.

## Acceptance Criteria

- [ ] `grep -rn 'five principles\|5 principles' .adlc/context/ README.md` → empty
- [ ] `test ! -d map` → true (map/ absent)
- [ ] `grep -rn 'atelier' README.md install.sh` → no project-specific skill reference
- [ ] `grep -rn "doesn't track lessons\|track lessons or bugs for itself yet" .adlc/context/` → empty
- [ ] CHANGELOG epoch list reads 1, 2, 3, 4, 5 in source order (visual)
- [ ] README + architecture.md template lists match `ls templates/*.md`
- [ ] `partials/README.md` documents id-alloc/id-recheck and makes no false drift claim

## Technical Notes

Run the full sweep as one block and capture output into the verify summary. Any non-empty
result on a "must be empty" grep, or a present `map/` dir, is a hard fail that blocks the
phase. This is the BR-6 deliverable — record the actual command output as evidence.
