---
id: TASK-235
title: "`--back`, `--prune-backup` and a repair of a missing home"
status: complete
parent: REQ-663
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-234]
repo: adlc-toolkit
---

## Description

Add the reverse flip with its own copy, the prune, and the restore from backup.

## Files to Create/Modify

- `tools/adlc/migrate_home.py` — the reverse flip, prune, the restore source
- `tools/adlc/tests/test_migrate_back.py` — AC-9 and the amended BR-9

## Acceptance Criteria

- [ ] `--back` restores the live values, removes `<dir>` and both copies, and doctor's verdicts match the start
- [ ] A failed `--back` leaves the migrated layout with live counters
- [ ] `--back` works after `--prune-backup`
- [ ] A repair with `<dir>` gone restores from the backup

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-9 | test-case | tools/adlc/tests/test_migrate_back.py::test_back_reverses_exactly | no |
| BR-9 | test-case | tools/adlc/tests/test_migrate_back.py::test_back_works_after_prune | yes |
| BR-10 | test-case | tools/adlc/tests/test_migrate_back.py::test_prune_removes_only_the_backup | yes |
| BR-11 | test-case | tools/adlc/tests/test_migrate_back.py::test_repair_restores_a_missing_home | no |
| AC-9 | test-case | tools/adlc/tests/test_migrate_back.py::test_back_reverses_exactly | no |
| AC-9 | test-case | tools/adlc/tests/test_migrate_back.py::test_back_failure_keeps_the_layout | no |

## Technical Notes

`<dir>` is removed only when nothing but the migrated home remains. Foreign entries stay and are named.
