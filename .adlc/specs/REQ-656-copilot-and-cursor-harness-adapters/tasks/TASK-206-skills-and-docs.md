---
id: TASK-206
title: "init, template-drift and the documentation"
status: complete
parent: REQ-656
created: 2026-10-30
updated: 2026-10-30
dependencies: [TASK-204]
repo: adlc-toolkit
---

## Description

Teach `/init` and `/template-drift` the new layers and land the docs in the same change.

## Files to Create/Modify

- `init/SKILL.md`, `template-drift/SKILL.md`
- `tools/adlc/README.md`, `.adlc/context/architecture.md`, `.adlc/context/conventions.md`
- `.adlc/research/multi-harness-plan.md` — §8 row
- `CHANGELOG.md`

## Acceptance Criteria

- [ ] `sync-surface-parity` is clean with the three files named
- [ ] `architecture.md` has a paragraph per adapter

## Verification

| rule | kind | artifact | benign_path |
|---|---|---|---|
| BR-13 | structural-check | requirement.md Deferred section | no |
| BR-16 | structural-check | tools/lint-skills sync-surface-parity | no |
| AC-13 | structural-check | requirement.md Deferred section | no |
| AC-15 | test-case | tools/lint-skills/check.sh | no |

## Technical Notes

AC-13 is unmet by design here: no `dogfood.md` is written, and the REQ stays `in-progress`.
