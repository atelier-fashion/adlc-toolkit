---
id: TASK-276
title: "Documents: what the six changes mean for an operator, and the three amendment notes"
status: complete
parent: REQ-719
repo: adlc-toolkit
created: 2026-11-20
updated: 2026-11-20
dependencies: [TASK-273, TASK-274, TASK-275]
---

## Description

Bring every document BR-28 names in line with the code TASK-270 to TASK-275 landed, add the residuals BR-17 states, and write the amendment notes in the three earlier requirements.

## Files to Create/Modify

- `sprint/references/exec-engine.md` — what `abort` does to a blocked run and what it leaves; `rejected` and `aborted` in the outcome record.
- `sprint/SKILL.md` — the exec section: a blocked run has two ways out.
- `README.md` — the exec section (`abort` on a blocked run, the PR tie, exit 75, the lane check on a single-branch clone, Phase 7's CI read) and the runner's declared residuals (a symlink inside the working copy is now refused; a hard link is not detected).
- `tools/adlc/README.md` — the runner's statuses (3, 65, 69, 75), the arg-file rule, `abortedFrom`, the mock's `pr_checks`.
- `CHANGELOG.md` — one entry.
- `.adlc/context/architecture.md` — the additions the architecture document proposes.
- `.adlc/context/conventions.md` — the forge adapter's operation set gains `checks`; `gh pr checks` stays direct only where `/wrapup` and `/bugfix` use it.
- `.adlc/specs/REQ-659-sprint-exec-engine/requirement.md` — amendment note on BR-10 and BR-20.
- `.adlc/specs/REQ-648-per-run-outcome-telemetry-and-recurrence/requirement.md` — amendment note on the two vocabularies.
- `.adlc/specs/REQ-682-exec-fences-run-without-widening/requirement.md` — amendment note on the runner's statuses and the PR tie.
- `tools/adlc/tests/test_exec_docs.py` — pins for the sentences below.
- `proceed/phases-state.md` — the list of `exec` keys gains `abortedFrom` (found by TASK-275; one change only).

## Acceptance Criteria

- [x] `sprint/references/exec-engine.md` says, in one place: `abort` on a blocked run ends it `failed` and leaves the branch, the PR and the working copy for a person. Every `sprint-exec` operator line in the file still parses (`test_bug287_the_reference_s_operator_lines_parse`).
- [x] `sprint/SKILL.md` names `answer` and `abort` for a blocked run, stays under 500 lines, and no fence body in it changes.
- [x] The README's declared residuals for the runner hold both BR-17 statements, and `test_declared_residuals_block_lists_a_to_f` passes (extended if the block gains an item).
- [x] `tools/adlc/README.md` lists status 75 with `fence_run_unverified:` beside 3, 65 and 69.
- [x] Each of the three amendment notes is dated 2026-11-20, names REQ-719 and the rule it narrows or extends, and changes no other text of that requirement.
- [x] `.adlc/context/architecture.md` and `.adlc/context/conventions.md` name `adlc_forge_pr_checks`.
- [x] `CHANGELOG.md` has the entry under the unreleased heading.
- [x] `python3 -m pytest tools/adlc/tests/test_exec_docs.py tools/adlc/tests/test_exec_prompt.py`, `pytest tools/lint-skills/tests`, `sh tools/lint-skills/check.sh` and `python3 tools/adlc/fence_census.py --check` pass.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | `tools/adlc/tests/test_exec_docs.py::test_req719_the_reference_says_what_abort_leaves` | yes |
| BR-17 | test-case | `tools/adlc/tests/test_exec_docs.py::test_req719_readme_states_the_arg_file_residuals` | no |
| BR-28 | test-case | `tools/adlc/tests/test_exec_docs.py::test_req719_every_named_document_carries_its_change` | no |
| AC-5 | test-case | `tools/adlc/tests/test_exec_docs.py::test_req719_the_reference_says_what_abort_leaves` | yes |
| AC-13 | test-case | `tools/adlc/tests/test_exec_docs.py::test_req719_readme_states_the_arg_file_residuals` | no |
| AC-22 | test-case | `tools/adlc/tests/test_exec_docs.py::test_req719_every_named_document_carries_its_change` | no |

## Technical Notes

- Read the merged code and `architecture.md` of this requirement before writing: document what the code does, with the words the code prints.
- `partials/lane-check.md`, `partials/forge.md`, `proceed/phases-telemetry.md` and `templates/config-template.yml` are BR-28 documents that TASK-270, TASK-271 and TASK-274 already changed. `test_req719_every_named_document_carries_its_change` checks them too, and this task fixes any that is missing its change.
- Prose only in skill files: a fence's id is a hash of its body.
- The exec prompt is built from `sprint/` and `proceed/` text with anchors that must match exactly once, and its scan refuses merge instructions. Run `test_exec_prompt.py` after every edit to those files.
- Plain sentences, the operator's words. No new terms where the code already has one.
