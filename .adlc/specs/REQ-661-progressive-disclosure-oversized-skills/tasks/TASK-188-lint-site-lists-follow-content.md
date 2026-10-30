---
id: TASK-188
title: "lint-skills: per-root site lists and the lesson checks follow content into companions"
status: complete
parent: REQ-661
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-187]
repo: adlc-toolkit
---

## Description

Architecture ADR-9: `retrieval-status-parity`, `lane-vocabulary`, `lesson-rules-parity`,
`lesson-check-order` and `lesson-question-coverage` find their marker block or fence
sequence in a companion, and a listed site that moved or vanished is a finding naming
the path and the list, once the check is armed.

## Files to Create/Modify

- `tools/lint-skills/check.py` — unit-aware lesson gate and capture file, `capture-step-split`, site-moved findings for the retrieval reader and writers and the rules-parity sites, companions of listed lane sites, armed rules-parity
- `tools/lint-skills/tests/test_site_lists_follow_content.py` — new: AC-9 fixtures for each check
- `tools/lint-skills/README.md` — the site-following rule

## Acceptance Criteria

- [ ] Post-split fixtures fire on: a writer's excluded status declared in a companion; a lane value outside the vocabulary in a `references/` file; capture-rules blocks that differ with `/wrapup`'s in a companion; a lesson fence out of order in a companion
- [ ] A listed site missing (armed) is a finding naming the path and the constant; a block moved within its unit is a finding naming where it is
- [ ] The constructs split across two files of the `wrapup` unit report `capture-step-split`
- [ ] Existing lesson, retrieval and lane tests still pass

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-10 | test-case | `tools/lint-skills/tests/test_site_lists_follow_content.py` | yes |
| BR-5 | test-case | `tools/lint-skills/tests/test_site_lists_follow_content.py::test_capture_step_split` | yes |
| AC-9 | test-case | `tools/lint-skills/tests/test_site_lists_follow_content.py` | yes |
| AC-14 | test-case | `pytest tools/lint-skills/tests` | no |
| AC-18 | structural-check | `tools/lint-skills/README.md`: site-following rule | no |

## Technical Notes

- The inert gates are unchanged: `retrieval-status-parity` needs `spec/SKILL.md`,
  `lesson-rules-parity` needs both `wrapup/SKILL.md` and `bugfix/SKILL.md`,
  `lane-vocabulary` needs its vocabulary file or `proceed/phases-lite.md`.
- A within-file lesson-check finding keeps today's message, so `test_check.py`'s lesson
  cases are untouched.
