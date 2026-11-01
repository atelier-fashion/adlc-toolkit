---
id: TASK-237
title: "Documentation"
status: complete
parent: REQ-663
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-235, TASK-236]
repo: adlc-toolkit
---

## Description

State the layout where the docs state it, in the same change.

## Files to Create/Modify

- `README.md` — a `--migrate-home` section: what moves, what never moves, the backup, `--back`
- `.adlc/context/architecture.md` — the stage-then-flip rule, the symlink-versus-tombstone sentence, the chosen mechanism
- `.adlc/context/conventions.md` — the three-step resolution rule
- `tools/adlc/README.md` — `home-layout`
- `CHANGELOG.md` — the entry
- `install.sh` — the usage header

## Acceptance Criteria

- [ ] `grep -n 'migrate-home' README.md` finds the section
- [ ] architecture.md says in one sentence why counters get symlinks and locks get tombstones

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-14 | structural-check | `tools/lint-skills` over the docs; `grep` in tools/adlc/tests/test_migrate_home.py::test_docs_carry_the_layout | no |
| AC-13 | test-case | tools/adlc/tests/test_migrate_home.py::test_docs_carry_the_layout | no |

## Technical Notes

LESSON-019: no enumeration that will rot; point at `home_layout.py` for the inventory.
