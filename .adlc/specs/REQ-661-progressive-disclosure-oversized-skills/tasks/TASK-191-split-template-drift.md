---
id: TASK-191
title: "Split /template-drift: Steps 5 and 6 into template-drift/references/"
status: complete
parent: REQ-661
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-187]
repo: adlc-toolkit
---

## Description

Architecture ADR-4, ADR-5: move Step 5 (the drift report) and Step 6 (the reconciliation
actions) verbatim, keep their headings with the read-and-follow sentence, and leave the
sync-surfaces block, Step 0a, Step 0 and every comparison fence in `SKILL.md`.

## Files to Create/Modify

- `template-drift/SKILL.md` — two stubs
- `template-drift/references/drift-report.md` — new: Step 5, verbatim
- `template-drift/references/reconciliation.md` — new: Step 6, verbatim

## Acceptance Criteria

- [ ] `wc -l template-drift/SKILL.md` below 500; the lint is clean
- [ ] `sync-surface-parity` and `partials/tests/plugin-route.test.sh` pass unchanged
- [ ] Every fence, marker block and stderr literal of the unit is unchanged as a multiset

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `tools/lint-skills`: skill-line-budget | no |
| BR-3 | structural-check | AC-3 equivalence script over the `template-drift` unit | no |
| BR-11 | structural-check | `tools/lint-skills`: sync-surface-parity | no |
| AC-11 | structural-check | `git diff --name-only origin/main` lists nothing under `partials/`, `templates/`, `workflows/`, nor `ETHOS.md` | no |
