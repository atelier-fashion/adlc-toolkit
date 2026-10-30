---
id: TASK-201
title: "Documentation, declared residuals and CHANGELOG"
status: complete
parent: REQ-657
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-197, TASK-198, TASK-200]
repo: adlc-toolkit
---

## Description

Docs move with the code and the declared residuals are carried in the same words
everywhere (BR-17, BR-18).

## Files to Create/Modify

- `README.md`, `.adlc/context/architecture.md`, `.adlc/context/conventions.md` — adapter layer
- `tools/adlc/README.md`, `tools/lint-skills/README.md` — verbs, checks, residuals
- `harness/claude/README.md` — the adapter README with residuals
- `CHANGELOG.md` — with the BR-7 re-sync note

## Acceptance Criteria

- [ ] The residuals section is byte-identical in the three READMEs and ends the lint report
- [ ] conventions.md states what adding a harness consists of

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-17 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_docs_carry_surfaces` | no |
| BR-18 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_residuals_identical` | no |
| AC-15 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_docs_carry_surfaces` | no |
| AC-17 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_residuals_identical` | no |

## Technical Notes

No README describes the allowlist as preventing a deny-tier command (Rule B).
