---
id: TASK-108
title: "/review Step 4: no escalation on confidence: low or superseded lessons; /spec Step 1.6: superseded annotation, scoring untouched"
status: complete
parent: REQ-646
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-104]
---

## Description

The two consumers that keep the new fields from being dead data (REQ-646 BR-6, BR-7;
ADR-6). `/review` reads `confidence` alongside the three tags it already reads and runs a
corpus-wide reverse lookup for `supersedes:`; a finding that matches a `low` or
superseded lesson is cited but **not** escalated, with the stated annotation. `/spec`
parses `supersedes`, runs the same reverse lookup for each retrieved lesson, and
annotates the retrieval summary and `## Retrieved Context` — the score is unchanged.

## Files to Create/Modify

- `review/SKILL.md` — Step 1 item 7b: read `confidence` and `supersedes` in addition to `domain`, `component`, `tags`. New item 7f: for each lesson in the relevance set, `superseded_by = $(grep -l -E '^supersedes:.*LESSON-<id>' .adlc/knowledge/lessons/*.md 2>/dev/null)` phrased split-free (`find … -name 'LESSON-*.md' | xargs grep -l`), recorded next to the lesson. Step 4 item 4: escalation fires only when the matched lesson has `confidence` absent or `medium`/`high` **and** is not superseded; otherwise the finding cites the id and the report says `(matched LESSON-xxx, confidence low — not escalated)` or `(matched LESSON-xxx, superseded by LESSON-yyy — not escalated)`. Step 6 item 4: list non-escalated matches too.
- `spec/SKILL.md` — Step 1.6 sub-step 2: add `supersedes` and `confidence` to the parsed field list. New sub-step 7a (after the body read, before the summary): reverse lookup per retrieved lesson as above. Sub-step 8 display: `LESSON-034 (lesson, score 5, superseded by LESSON-040): …` when applicable. Step 3 `## Retrieved Context` bullet: same parenthetical. Scoring sub-steps 3–6 untouched; the `retrieval-status: spec-exclude` block untouched.

## Acceptance Criteria

- [ ] `review/SKILL.md` Step 4 states both non-escalation cases with the exact annotation strings and keeps "absent `confidence` escalates as today"
- [ ] `spec/SKILL.md` sub-step 2's field list includes `supersedes` and `confidence`; sub-steps 3–6 are byte-unchanged (`git diff` shows no hunk in the scoring rule); the `spec-exclude` marker block is byte-unchanged
- [ ] Neither skill uses a bare `ls <glob>` for the lookup (LESSON-335); `python3 tools/lint-skills/check.py` is clean (incl. `retrieval-status-parity`)
- [ ] Manual dogfood (AC-10): `/review` on a diff matching a `confidence: low` fixture lesson reports the match without escalation; on a superseded fixture likewise with the superseded annotation; on a legacy lesson it escalates
- [ ] Manual dogfood (AC-11): `/spec` on a request matching a superseded fixture lesson shows `(superseded by LESSON-yyy)` and the same score as before

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | structural-check | `partials/tests/lesson-check.test.sh::review_step4_states_both_exemptions` (greps the two annotation strings and the legacy-escalates sentence) | yes |
| BR-7 | structural-check | `tools/lint-skills`: `retrieval-status-parity` (exclusion block untouched); `partials/tests/lesson-check.test.sh::spec_scoring_rule_unchanged` (the +3/+2/+2/+1/+1 lines are present verbatim) | yes |
| AC-10 | structural-check | `partials/tests/lesson-check.test.sh::review_step4_states_both_exemptions` (dogfood is manual) | yes |
| AC-11 | structural-check | `partials/tests/lesson-check.test.sh::spec_summary_annotation_documented` | no |

## Technical Notes

- Reverse lookup, split-free and zsh-safe: `find .adlc/knowledge/lessons -maxdepth 1 -name 'LESSON-*.md' -print0 2>/dev/null | xargs -0 grep -l -E "^supersedes:.*LESSON-<id>([^0-9]|$)"` — the `([^0-9]|$)` delimiter stops `LESSON-40` matching `LESSON-404` (LESSON-013: no `\b`).
- The reflector agent and `/architect` grep lessons but do no escalation — no change there (confirmed by exploration).
- The three harness cases named above (`review_step4_states_both_exemptions`, `spec_scoring_rule_unchanged`, `spec_summary_annotation_documented`) are added by **TASK-109**; this task does not touch `partials/tests/lesson-check.test.sh`.
