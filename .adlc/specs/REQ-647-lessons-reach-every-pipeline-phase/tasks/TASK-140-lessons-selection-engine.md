---
id: TASK-140
title: "tools/adlc/lessons.py — the LessonSet selection engine (Step 1.6 score, recency rule, loaded text, state write, log line, acknowledgement check) and its tests"
status: complete
parent: REQ-647
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

The one implementation every call site uses. Stdlib Python, no PyYAML. Parses
lesson frontmatter the way `adlc_lesson_check` does, scores with the `/spec`
Step 1.6 rule over lessons only, applies the per-set rules from the REQ
(step0 / task / phase5 / bugfix), extracts the 40-line loaded text, merges the
set into a state file atomically, prints the BR-10 log line, and runs the BR-4
acknowledgement check. See `architecture.md` "Engine".

## Files to Create/Modify

- `tools/adlc/lessons.py` — create; subcommands `select`, `text`, `log-line`, `ack-check`
- `tools/adlc/tests/test_lessons.py` — create; unit + corpus tests
- `tools/adlc/README.md` — modify; one row for the new tool

## Acceptance Criteria

- [ ] Frontmatter reader skips BOM, CRs, blank lines and multi-line HTML comments; a malformed block is skipped, not fatal
- [ ] `select --set step0` on REQ-593's spec does not contain LESSON-582; `select --set task` with `--component adlc/partials/forge` does, with `newerThanSpec: true`
- [ ] Every corpus lesson's loaded text is ≤ 40 lines; LESSON-571 is exactly 40 with the marker; LESSON-013 contributes its first body section; no loaded text contains `## What Happened`
- [ ] `unacknowledged()` on 12 qualifying lessons returns 5 lines plus `(+7 more applicable lessons not listed)`; a tags-only lesson and a trailer-acknowledged lesson are excluded
- [ ] `--state-out` preserves every other key; `--fresh` resets `lessons`; `--reuse` returns an existing set unchanged; a state file with no `lessons` key is read without error
- [ ] `log-line` appends `(stale: 1 lessons newer than this set)` when one lesson file's mtime is later than `retrievedAt`
- [ ] Caps: step0 ≤ 10, task ≤ 15 (5 + ≤3 recency + process carry-over), phase5 ≤ 15 with top-up to 10, bugfix ≤ 5
- [ ] `pytest tools/adlc/tests/test_lessons.py` passes with collected > 0

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_lessons.py::test_step0_set_is_top10_by_req_tags` | no |
| BR-1a | test-case | `tools/adlc/tests/test_lessons.py::test_task_set_recency_rule_most_specific_first` | no |
| BR-1b | test-case | `tools/adlc/tests/test_lessons.py::test_loaded_text_cap_every_corpus_lesson` | no |
| BR-3 | test-case | `tools/adlc/tests/test_lessons.py::test_phase5_set_top15_and_topup` | no |
| BR-4 | test-case | `tools/adlc/tests/test_lessons.py::test_unacknowledged_caps_at_five` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_lessons.py::test_bugfix_set_top5` | no |
| BR-7 | test-case | `tools/adlc/tests/test_lessons.py::test_state_out_is_additive` | yes |
| BR-10 | test-case | `tools/adlc/tests/test_lessons.py::test_log_line_stale_suffix` | no |
| AC-2 | test-case | `tools/adlc/tests/test_lessons.py::test_lesson_604_reproduction` | no |
| AC-3 | test-case | `tools/adlc/tests/test_lessons.py::test_task_text_has_lesson_and_applies_when_not_what_happened` | no |
| AC-4 | test-case | `tools/adlc/tests/test_lessons.py::test_loaded_text_cap_every_corpus_lesson` | no |
| AC-6 | test-case | `tools/adlc/tests/test_lessons.py::test_unacknowledged_caps_at_five` | yes |
| AC-11 | test-case | `tools/adlc/tests/test_lessons.py::test_log_line_stale_suffix` | no |
| AC-12 | test-case | `tools/adlc/tests/test_lessons.py::test_state_without_lessons_key` | yes |

## Technical Notes

- Follow `tools/adlc/lane_check.py` for CLI shape and `tools/adlc/tests/test_lane_check.py` for test layout.
- Scoring, ordering and caps exactly as `architecture.md` "Selection". Most-specific-first is decided by caller-passed vs derived-ancestor components (ADR-2).
- `retrievedAt` defaults to `datetime.now(timezone.utc)`; `--retrieved-at` pins it for tests.
- Entry fields: `id, title, path, component, score?, confidence?, kind?, newerThanSpec?, supersededBy?, text?` (`path` relative to `--root`).
- Ack trailers: `^Lessons:\s*` followed by comma/space separated `LESSON-\d{3,6}` ids, read from `git log --format=%B <base>..HEAD`. Validate every id against `^LESSON-[0-9]{3,6}$` (LESSON-008).
- Corpus tests read this repo's own `.adlc/knowledge/lessons`; mark them so a missing corpus skips rather than passes vacuously only when the corpus is absent.
