---
id: TASK-283
title: "`/proceed` Phase 5 and Phase 6 run the reviewer, merge its findings and refuse undisposed ones"
status: complete
parent: REQ-722
created: 2026-11-24
updated: 2026-11-24
dependencies: [TASK-282]
---
## Description

Wire the reviewer into `/proceed` with the procedure in a new companion file and five
pointer lines in `proceed/SKILL.md`, add the Phase 6 disposition precondition and the PR
body section, and record `subagent-mode` skips from the pipeline runner.

## Files to Create/Modify

- `proceed/phases-cross-family.md` — new: the per-repo fence, the subagent record-only fence, Step B merge rule, Step C disposition rule, the Phase 6 precondition; a line beside each fence that it does not run on reading and what it needs first (LESSON-899)
- `proceed/SKILL.md` — Phase 5 Step A/B/C/D and subagent-mode pointer lines; Phase 6 precondition line; stays under 500 lines and keeps "exactly **four**" halts
- `proceed/phases-6-8-ship.md` — PR body: `## Cross-family review` from `cross_family.py pr-section`, between Test Coverage and Reflection Notes
- `agents/pipeline-runner.md` — subagent mode runs the record-only fence per touched repo
- `tools/lint-skills/tests/test_read_bin_fences.py` — call-site pin updated if a fence's `adlc-read` count changes
- `tools/adlc/exec_prompt.py` — `PIPELINE_SOURCES` gains `proceed/phases-cross-family.md`, so an exec run records the review too (BR-12)
- `tools/adlc/fence_census.py` — closed placeholders `<repo-id>` and `<declineReason>` so the companion's fences route through the runner
- `tools/adlc/tests/test_fence_run.py` — samples for the two new placeholders (hostile-value test)
- `harness/claude/exec-fence-census.json` — regenerated golden
- `harness/codex/exec-fence-census.json` — regenerated golden
- `tools/lint-skills/tests/test_cross_family_skill_text.py` — new: structural assertions below
- `tools/lint-skills/tests/test_lite_lane_contract.py` — the lite path names no cross-family step

## Acceptance Criteria

- [x] No panel or reflector dispatch paragraph references the cross-family findings block (structural test)
- [x] Step D text says the cross-family reviewer is not re-run, and `fixedPairs`-style scoping never names it
- [x] The subagent-mode path records `skipped` / `subagent-mode` per touched repo
- [x] The pre-pass section of `proceed/SKILL.md` is byte-identical outside the added pointer lines
- [x] Phase 6 text runs `check-dispositions` before creating the PR, and a non-zero exit returns to Step C, not a halt
- [x] The lite lane's Phase 5 (`proceed/phases-lite.md`) is unchanged
- [x] `tools/lint-skills`, `partials/tests/run.sh` and the fence census test pass, with goldens regenerated

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_step_a_runs_reviewer_per_repo_once` | no |
| BR-5 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_pr_body_section_from_renderer` | no |
| BR-7 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_no_panel_dispatch_sees_findings` | no |
| BR-8 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_phase6_checks_dispositions_without_halt` | yes |
| BR-11 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_prepass_section_unchanged` | no |
| BR-14 | test-case | `tools/lint-skills/tests/test_lite_lane_contract.py::test_lite_path_has_no_cross_family_step` | no |
| BR-15 | test-case | `tools/adlc/tests/test_fence_census.py::test_golden_matches_fresh_census` | no |
| AC-2 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_step_b_unions_source` | no |
| AC-3 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_no_panel_dispatch_sees_findings` | no |
| AC-9 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_step_c_decline_needs_check_decline` | no |
| AC-10 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_step_d_does_not_rerun` | no |
| AC-11 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_subagent_mode_records_skip` | no |
| AC-12 | test-case | `tools/lint-skills/tests/test_cross_family_skill_text.py::test_prepass_section_unchanged` | yes |
| AC-17 | test-case | `tools/lint-skills/tests/test_lite_lane_contract.py::test_lite_path_has_no_cross_family_step` | yes |

Lessons: LESSON-742, LESSON-019, LESSON-404, LESSON-719, LESSON-751 — LESSON-742: `partials/tests/run.sh`, the fence census check and the tests that read `proceed/SKILL.md` ran on the final tree, and a `lane-vocabulary` finding was fixed by rewording the new text, not the guard; LESSON-019: each command the text names is extracted from the real companion and run against the real CLI or partial; LESSON-404: every structural assertion has a planted must-fire input; LESSON-719: the Phase 6 disposition loop leaves `currentPhase` alone and a resume decides from the state file, and the Step A fence re-runs on a resume only when `verify` is absent; LESSON-751: SKILL.md re-measured at 447 lines before the edit (455 after). `test_goldens_match` named in the original table does not exist; the census golden test is `test_golden_matches_fresh_census`.

## Technical Notes

- SKILL.md is at 447/500 (`check.py:303`, `test_phase7_text.py:117`); budget about 12 lines here, everything else in the companion.
- A new fence renumbers later census ids (`proceed/SKILL.md#n`); regenerate with `--write-goldens` and review the diff (memory: regenerate fence census goldens when a partial gains a command).
- Any `##`/`###` step naming an agent needs the canonical fallback paragraph (`check.py:3154`).
- `cross-fence-fn` (`check.py:1819`): the fence that calls `adlc_cross_family_review` must source the partial itself.
- Run `partials/tests/run.sh` on the final tree, not only lint (LESSON-742).
