---
id: TASK-109
title: "tools/lint-skills check lesson-check-order: write-point → check fence → recheck fence, Teton line, rules block byte-equal across /wrapup and /bugfix"
status: complete
parent: REQ-646
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-106, TASK-107]
---

## Description

The structural enforcement for REQ-646 BR-3's placement, BR-4's "same rules in both
skills", and BR-15's Teton line (ADR-5). A new `tools/lint-skills` check reads
`wrapup/SKILL.md` and `bugfix/SKILL.md` and fails the lint when any of the three
orderings or the block equality is broken. Markers are matched at line start and
rejected inside backticks (LESSON-404 — the toolkit's own docs mention the marker in
prose).

## Files to Create/Modify

- `tools/lint-skills/check.py` — new `check_lesson_check_order(path, text)` registered in `run()` for exactly the two files (by basename of the parent dir: `wrapup`, `bugfix`); constants `LESSON_WRITE_POINT_RE = re.compile(r'^\s*<!-- lesson-write-point -->\s*$')`, `LESSON_RULES_OPEN_RE` / `_CLOSE_RE` (own-line markers), `LESSON_CHECK_CALL_RE = re.compile(r'^\s*adlc_lesson_check\s')`, `LESSON_RECHECK_CALL_RE = re.compile(r'^\s*adlc_recheck_id\s+lesson\b')` (Python `re` honours `\b`; the LESSON-013 rule is for BSD grep). Findings: `missing-write-point`, `missing-check-fence`, `missing-recheck-fence`, `check-before-write-point`, `recheck-before-check`, `missing-harness-line` (the `**Provenance-classifying harness (BUG-228):**` literal not within 30 lines above the check fence — reuse `HARNESS_SKIP_LITERAL` and the 30-line window), `rules-block-missing`, `rules-block-mismatch` (the two files' blocks differ byte-for-byte), and for `wrapup` only `rules-line-not-in-question` (each non-empty, non-marker line of the block must occur at least twice in the file — once in the block, once inside the delegated `--question`).
- `tools/lint-skills/tests/test_check.py` — tests: good pair passes; recheck-before-check fails with `recheck-before-check`; marker inside backticks is not a write point (decoy fixture — the prose mention of `<!-- lesson-write-point -->` must not satisfy the check); rules block differing by one byte fails `rules-block-mismatch`; missing Teton line fails `missing-harness-line`; a rule line absent from the question fails `rules-line-not-in-question`. Fixtures under `tools/lint-skills/tests/fixtures/lesson-check-order/`.
- `tools/lint-skills/README.md` — a row for `lesson-check-order` in the checks table.
- `tools/lint-skills/check.py` — the existing whole-tree-clean test (`test_shipped_toolkit_tree_is_clean`) must stay green against the real `wrapup/SKILL.md` and `bugfix/SKILL.md` produced by TASK-106/107.
- `partials/tests/lesson-check.test.sh` — append the five skill-text cases Tier 1 owes (this task is the harness's only Tier-2 writer): `wrapup_templates_carry_lessons_captured` (both `/wrapup` Step-5 templates have `### Lessons captured` with a body line), `bugfix_summary_uses_no_entry_form` (`/bugfix` Step 6 has `NO_ENTRY: <reason>` and no "None — fix was straightforward"), `review_step4_states_both_exemptions` (both annotation strings plus the legacy-escalates sentence in `review/SKILL.md`), `spec_scoring_rule_unchanged` (the `+3`/`+2`/`+2 ×`/`+1 ×`/`+1 ×` scoring lines present verbatim in `spec/SKILL.md`), `spec_summary_annotation_documented` (`superseded by LESSON-` appears in `spec/SKILL.md`'s sub-step 8 and Step 3). Keep the counter contract; `sh partials/tests/run.sh` must report them as PASS under all four shells.

## Acceptance Criteria

- [ ] `python3 -m pytest -q tools/lint-skills/tests` passes with the new tests collected (> 0) and the whole-tree-clean test still green
- [ ] `python3 tools/lint-skills/check.py` on the real tree reports no `lesson-check-order` finding; on a copy of `bugfix/SKILL.md` with the recheck fence moved above the check fence it reports `recheck-before-check`
- [ ] A fixture whose only `<!-- lesson-write-point -->` is inside backticks fails `missing-write-point`
- [ ] The README table documents the check and its finding ids

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/lint-skills/tests/test_check.py::test_lesson_check_order_good_pair_passes`, `::test_lesson_check_order_recheck_before_check_fails`, `::test_lesson_check_order_backtick_marker_is_decoy` | yes |
| BR-4 | test-case | `tools/lint-skills/tests/test_check.py::test_lesson_check_order_rules_block_mismatch_fails`, `::test_lesson_check_order_rule_line_absent_from_question_fails` | yes |
| BR-15 | test-case | `tools/lint-skills/tests/test_check.py::test_lesson_check_order_missing_harness_line_fails` | yes |
| AC-4 | test-case | `tools/lint-skills/tests/test_check.py::test_lesson_check_order_good_pair_passes` + `test_retrieval_status_parity.py::test_shipped_toolkit_tree_is_clean` | yes |
| AC-6 | test-case | `tools/lint-skills/tests/test_check.py::test_lesson_check_order_rules_block_mismatch_fails` | yes |
| AC-14 | test-case | `tools/lint-skills/tests/test_retrieval_status_parity.py::test_shipped_toolkit_tree_is_clean` | yes |

## Technical Notes

- Follow the shape of `check_retrieval_status_parity` / `check_harness_skip` (fence iteration helpers already exist — reuse `iter_fences` or its equivalent rather than re-parsing).
- Backtick rejection: a marker line is valid only when the line, stripped, *is* the marker; a line containing the marker plus any other character (backticks, prose) is not a marker (LESSON-404 decoy test).
- The `--question` coverage count is a substring count on the whole file; the block's own occurrence counts once, so the threshold is ≥ 2.
- Do not scan `templates/` or `.adlc/` — the check is scoped to the two skill files.
