---
id: TASK-145
title: "Contract tests for the wiring, the /status benign path, and the architecture.md Knowledge retrieval paragraph"
status: complete
parent: REQ-647
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-142, TASK-143, TASK-144]
repo: adlc-toolkit
---

## Description

The structural checks that keep the wiring from rotting (LESSON-012), a
scripted benign path for `/status` over a state file with and without a
`lessons` key, and the documentation: `.adlc/context/architecture.md`
"Knowledge retrieval" and the CHANGELOG.

## Files to Create/Modify

- `tools/lint-skills/tests/test_lessons_contract.py` — create; needle tests over the wired files
- `.adlc/context/architecture.md` — modify; "Knowledge retrieval" paragraph and the lesson-schema reader note
- `CHANGELOG.md` — modify; an Unreleased entry

## Acceptance Criteria

- [ ] The contract tests pass and fail when a needle is removed
- [ ] `/status`'s state-reading fences run without error over a sandbox state file with no `lessons` key
- [ ] No new skill directory; the `knowledge capture: unavailable — BUG-249` notice appears nowhere
- [ ] `tools/lint-skills` passes; `pytest tools/lint-skills` passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-9 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_no_bug249_unavailable_notice` | no |
| BR-11 | structural-check | `tools/lint-skills/tests/test_lessons_contract.py::test_no_new_skill_directory` | no |
| AC-12 | test-case | `tools/lint-skills/tests/test_lessons_contract.py::test_status_fences_tolerate_state_without_lessons` | yes |
| AC-13 | structural-check | `tools/lint-skills` (scanned > 0); `pytest tools/lint-skills` | no |

## Technical Notes

- Follow `tools/lint-skills/tests/test_lite_lane_contract.py` for the needle style.
- Extract `/status`'s Python heredocs by their fence markers and run them in a temp `.adlc/specs/` sandbox; do not execute arbitrary fence text (LESSON-619).
