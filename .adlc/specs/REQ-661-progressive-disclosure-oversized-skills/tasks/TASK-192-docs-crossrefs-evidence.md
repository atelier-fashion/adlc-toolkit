---
id: TASK-192
title: "Docs, cross-references, the AC-3 equivalence run and dogfood evidence"
status: complete
parent: REQ-661
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-189, TASK-190, TASK-191]
repo: adlc-toolkit
---

## Description

BR-13 and BR-17: record the companion contracts in `architecture.md` Skill anatomy and
the companion and unit rules in `conventions.md` "Bash in skills"; make every live
reference to a moved section name its new file; widen the e2e `SHIPPED` list; run the
AC-3 equivalence script and the BR-16 dogfood and keep their output for the PR body.

## Files to Create/Modify

- `.adlc/context/architecture.md` — Skill anatomy: the two companion contracts and which files are under which
- `.adlc/context/conventions.md` — "Bash in skills": a fence may live in a companion; the cross-fence rules apply across the unit
- `agents/pipeline-runner.md` — names `proceed/phases-telemetry.md`
- `tools/adlc/tests/e2e/plugin-sandbox.sh` — `SHIPPED` gains `*/references/*.md`
- `tools/lint-skills/README.md` — the history paragraph that names `proceed/SKILL.md` as a write site

## Acceptance Criteria

- [ ] AC-13's grep returns no match naming `spec/`, `proceed/`, `template-drift/` or `wrapup/`
- [ ] A grep for `references/` finds the BR-17 sentences in `architecture.md` and `conventions.md`
- [ ] The AC-3 script reports equal fence multisets, equal marker blocks and no lost stderr literal for each split unit
- [ ] `git diff --name-only --diff-filter=A origin/main` lists only the companions, `tools/lint-skills/` files and this REQ's `.adlc/` artifacts
- [ ] The dogfood stderr and telemetry match the pre-split fences'

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | structural-check | AC-3 equivalence script (PR body) | no |
| BR-11 | structural-check | `git diff --name-only origin/main` | no |
| BR-13 | structural-check | AC-13 grep | no |
| BR-14 | structural-check | `git diff --name-only --diff-filter=A origin/main` | no |
| BR-16 | structural-check | dogfood transcript (PR body) | no |
| BR-17 | structural-check | grep `references/` in `architecture.md`, `conventions.md` | no |
| AC-3 | structural-check | AC-3 equivalence script (PR body) | no |
| AC-10 | structural-check | `grep -rn 'lesson-write-point\|adlc_lesson_check\|adlc_recheck_id lesson' wrapup/` | no |
| AC-11 | structural-check | `git diff --name-only origin/main` | no |
| AC-13 | structural-check | AC-13 grep | no |
| AC-15 | structural-check | dogfood transcript (PR body) | no |
| AC-16 | structural-check | `git diff --name-only --diff-filter=A origin/main` | no |
| AC-18 | structural-check | grep in `architecture.md`, `conventions.md`, lint README | no |
