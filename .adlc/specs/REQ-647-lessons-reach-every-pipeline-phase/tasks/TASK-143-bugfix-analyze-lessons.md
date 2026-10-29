---
id: TASK-143
title: "/bugfix Phase 2 opens with the bugfix LessonSet: Prior lessons consulted, top 5"
status: complete
parent: REQ-647
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-141]
repo: adlc-toolkit
---

## Description

BR-5: before root-cause analysis, build the bugfix set from the bug's
frontmatter and the components of the reproduction's file paths, and list the
top 5 under `Prior lessons consulted:`.

## Files to Create/Modify

- `bugfix/SKILL.md` — modify; Phase 2 gains a first step with the `adlc_lessons select --set bugfix` fence

## Acceptance Criteria

- [ ] Phase 2's first step computes the set and prints `Prior lessons consulted:` with ≤ 5 lessons before the root-cause analysis
- [ ] A non-zero return is logged and Phase 2 continues
- [ ] `tools/lint-skills` passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_bugfix_phase2_consults_lessons_first`; `tools/lint-skills`: toolkit-root-line, unguarded-source | no |
| AC-7 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_bugfix_phase2_consults_lessons_first` | no |

## Technical Notes

- Number the new step 1 and renumber the rest; attribution (now step 7) is referenced by name elsewhere, check with grep.
