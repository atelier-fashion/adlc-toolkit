---
id: TASK-063
title: "Tests — deterministic workflow helpers + harness"
status: complete
parent: REQ-474
created: 2026-05-29
updated: 2026-05-30
dependencies: [TASK-058, TASK-060]
---

## Description

Give the security-critical and consolidation logic real unit coverage. The orchestration is dogfooded (per conventions), but the pure helpers — especially `validateCitations` (LESSON-008) — must not regress, so they get deterministic tests under a minimal harness. (ADR-10)

## Files to Create/Modify

- `workflows/tests/` — CREATE. Harness + unit tests for `validateCitations`, `dedupeAndRank`, `scoreEligibility`, and the `args.answers` cache-key behavior.
- `workflows/` — MODIFY if helpers need extracting into importable form for testing.

## Acceptance Criteria

- [ ] `validateCitations`: rejects `..` paths, paths absent from `changedFiles`, and `^[A-Za-z0-9_./-]+$` violations; sanitizes descriptions; accepts valid candidates. (LESSON-008 cases are mandatory.)
- [ ] `dedupeAndRank`: dedupes within a repo, tags cross-repo findings, orders by severity, and the Critical-gate predicate is correct.
- [ ] `scoreEligibility` and the max-5 truncation behave per BR-12 (and truncation is logged).
- [ ] The harness runs from a documented command and is wired into whatever CI the toolkit uses (or documented as a manual gate if none).

## Technical Notes

- Use Node's built-in `node:test` (no new dependency) or a pytest-subprocess wrapper matching the `tools/*/tests` convention (ADR-10). Pick the lighter option and document it.
- This is the "Verify, Don't Trust" backstop for the parts that can silently fail — prioritize the LESSON-008 path cases.
