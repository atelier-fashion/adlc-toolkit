---
id: TASK-229
title: "The /sprint branch, the state keys and the docs"
status: complete
parent: REQ-659
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-227, TASK-228]
repo: adlc-toolkit
---

## Description

BR-1, BR-2's skill half, and BR-19.

## Files to Create/Modify

- `sprint/SKILL.md` — engine selection
- `sprint/references/exec-engine.md` — the exec branch, approve, reject, answer, abort, the operator-instruction rule
- `proceed/phases-state.md` — the three state keys
- `.adlc/context/architecture.md`, `README.md`, `CHANGELOG.md`, `templates/config-template.yml` — docs
- `partials/tests/sprint-fence.test.sh` — the new fences

## Acceptance Criteria

- [x] `sh tools/lint-skills/check.sh` is clean
- [x] `grep -n 'three-engine\|exec engine' .adlc/context/architecture.md README.md` finds the sections
- [x] The legacy prompt fence in `sprint/SKILL.md` is byte-identical

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-19 | structural-check | `tools/lint-skills` plus `tools/adlc/tests/test_exec_docs.py` | no |
| AC-14 | test-case | `tools/adlc/tests/test_exec_docs.py::test_sections` | no |
| AC-12 | test-case | `tools/adlc/tests/test_exec_docs.py::test_legacy_prompt_unchanged` | yes |

## Technical Notes

`phases-state.md` is inlined into the prompt, so its new text must pass the scan.
