---
id: TASK-240
title: "Bug and config templates carry the regression fields and setting"
status: complete
parent: REQ-691
created: 2026-11-04
updated: 2026-11-04
dependencies: [TASK-238]
repo: adlc-toolkit
---

## Description

Document the two optional bug fields and the `## Regression Test` section in `templates/bug-template.md`, and add the uncommented `bugfix.regression_test: required` block to `templates/config-template.yml` (BR-15). A test confirms the engine reads the template as `required` and that the existing template tests still hold.

## Files to Create/Modify

- `templates/bug-template.md` — after `attribution:`, add `regression_tests: []` and `regression_waiver: ""` with comments: optional, additive, flow list only, waiver double-quoted, never both set. Extend the HTML comment block. Add `## Regression Test` after `## Resolution`, with the slots BR-5 lists.
- `templates/config-template.yml` — a `bugfix:` section in the file's comment-banner style: what the setting does, both values, that an absent key means `off`, when to choose `off`, and the waiver. Uncommented `regression_test: required`. Place it after the `# branches:` block, and keep every uncommented line free of the word `lanes`.
- `tools/adlc/tests/test_regression_templates.py` — new.

## Acceptance Criteria

- [x] `regression_check.py mode`, run on a temp repo whose `.adlc/config.yml` is a copy of the template, prints `regression-test: required`.
- [x] `harness_yaml.loads` parses the template, and its `bugfix` mapping has exactly one key.
- [x] The template bug report, with its placeholders filled, reads as `legacy` with the empty fields absent, and as `passed` once `regression_tests` names a tracked file citing the id.
- [x] `tools/adlc/tests/test_lane_check.py`'s template case and `tools/lint-skills/tests/test_integration_branch_key.py` still pass.
- [x] Neither template gains a home-directory path or a bare `/init`.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | `tools/adlc/tests/test_regression_templates.py::test_bug_template_documents_fields_and_section` | no |
| BR-15 | test-case | `tools/adlc/tests/test_regression_templates.py::test_config_template_reads_required` | yes |
| AC-13 | test-case | `tools/adlc/tests/test_regression_templates.py::test_bug_template_documents_fields_and_section` | no |

## Technical Notes

- The template's empty `regression_tests: []` and `regression_waiver: ""` must count as "not present" in the engine, so a bug copied from the template and never filled reads as `legacy`, not `failed`. Confirm that TASK-238's reader treats an empty list and an empty string as absent. If it doesn't, the fix belongs in the engine, with a test there, not in this template.
- `/template-drift` already compares `templates/*.md`, so AC-13's drift report needs no code; `config-template.yml` is exempt from the sync surface by design.
