---
id: TASK-241
title: "/bugfix runs the regression protocol from a companion"
status: complete
parent: REQ-691
created: 2026-11-04
updated: 2026-11-04
dependencies: [TASK-239, TASK-240]
repo: adlc-toolkit
---

## Description

Wire the regression protocol into `/bugfix`: read the mode before Phase 1, write and contrast the test in Phase 3, record it in Phase 4, carry it into the PR body in Phase 5, gate the merge in Phase 6, and summarise it in Step 6. The protocol text lives in `bugfix/references/regression-test.md` (ADR-691-G), and `bugfix/SKILL.md` gets one read-and-follow sentence per site. A contract test pins the order and the wording the rules depend on.

## Files to Create/Modify

- `bugfix/references/regression-test.md` — new companion, with five sections: **Mode** (fence: root line, guarded source of `partials/regression-check.sh`, `adlc_regression_check mode`; stop on rc 2 with the engine's message), **Write and contrast** (ADR-691-E test-first order, BR-2 to BR-4, the passes-before-the-fix rule, the seam rule, the load-failure case), **Record** (BR-5 fields in flow form and the `## Regression Test` section; BR-6 waiver; BR-7 never both), **PR body** (a `## Regression Test` block: tests and contrast, or the waiver and its reason, or a load-failure flag), **Gate** (fence running `adlc_regression_check check --require-recorded BUG-nnn` in the fix worktree; stop before the merge on anything but rc 0). Each section begins by re-reading the mode (ADR-691-H) and says what to do when it is `off`.
- `bugfix/SKILL.md` — one pointer sentence each in Prerequisites, Phase 3, Phase 4, Phase 5 and a new first step of Phase 6. The BR-16 sentence goes beside "A reproduce-then-fix sequence is a contrast", outside the capture-rules block. A `### Regression test` slot goes in the Step 6 summary fence: the tests, the waiver, or "off for this project" plus, when the key is absent, the key that turns it on (BR-8). Correct the Context fence's stale "before Step 1" to "before Phase 1".
- `tools/lint-skills/tests/test_bugfix_regression_contract.py` — new. Reads both files by path.

## Acceptance Criteria

- [x] The contract test asserts: the Prerequisites pointer comes before `### Phase 1`; the Write and contrast section records the failing run before it says to write the fix; the Gate pointer comes before Phase 6's merge step; the companion names `regression_tests`, `regression_waiver`, `--require-recorded` and both modes; and the BR-16 sentence is outside the capture-rules block.
- [x] `tools/lint-skills/check.sh` passes, including `lesson-check-order`, the rules-parity check against `wrapup/SKILL.md`, `toolkit-root-line`, `unguarded-source`, `cross-fence-fn`, `cross-fence-var`, `companion-templating` and `skill-line-budget`.
- [x] `partials/tests/lesson-check.test.sh` (the Step 6 slice and `NO_ENTRY: <reason>`) and `tools/lint-skills/tests/test_lessons_contract.py` (the Phase 2 slice) still pass.
- [x] `bugfix/SKILL.md` grows by no more than 25 lines.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_mode_read_before_phase_1` | yes |
| BR-2 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_write_and_contrast_section` | no |
| BR-3 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_failing_run_recorded_before_fix` | no |
| BR-4 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_write_and_contrast_section` | no |
| BR-5 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_record_section_names_fields` | no |
| BR-6 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_waiver_reaches_pr_body_and_summary` | no |
| BR-7 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_record_section_names_fields` | no |
| BR-8 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_off_mode_at_every_site` | yes |
| BR-13 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_gate_before_merge` | no |
| BR-16 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_contrast_sentence_outside_rules_block` | no |
| BR-17 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_mode_read_before_phase_1` | no |
| AC-1 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_record_section_names_fields` | no |
| AC-2 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_off_mode_at_every_site` | yes |
| AC-3 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_mode_read_before_phase_1` | no |
| AC-4 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_failing_run_recorded_before_fix` | no |
| AC-12 | test-case | `tools/lint-skills/tests/test_bugfix_regression_contract.py::test_gate_before_merge` | no |

## Technical Notes

- Every companion fence starts with the canonical root line and sources the partial with the one guarded spelling, in the same fence as the call. No variable crosses fences; the bug id goes in as a substituted `'<bug-id>'` placeholder checked against `^BUG-[0-9]{3,6}$` before use.
- The companion's fences don't consume the skill argument, so they may live there (`companion-templating`).
- AC-1 to AC-4 and AC-12 describe what a live `/bugfix` run produces. The contract test pins the text that makes the model produce it; a live run is the reviewer's dogfood check, recorded in the PR, not a gate.
- Don't touch the Phase 2 headings or the phrase `keeps the top 5`, the `Granularity:` line, or the `adlc_lesson_check` fence.
