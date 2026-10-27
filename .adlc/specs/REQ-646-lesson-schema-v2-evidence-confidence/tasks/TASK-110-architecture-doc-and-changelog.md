---
id: TASK-110
title: "architecture.md knowledge-retrieval paragraph + template row for the v2 fields; CHANGELOG [Unreleased] entry"
status: complete
parent: REQ-646
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-108, TASK-109]
---

## Description

REQ-646 BR-11 plus the release bookkeeping. `.adlc/context/architecture.md` still
describes knowledge retrieval as a "3-tier grep"; rewrite that paragraph for the REQ-258
weighted retriever, the six v2 fields, the `NO_ENTRY` contract, and
`partials/lesson-check.sh` as the writer-side structural guard. The Template-anatomy row
for `lesson-template.md` lists all sixteen fields. `CHANGELOG.md` `[Unreleased]` gains
`### Added` / `### Changed` entries.

## Files to Create/Modify

- `.adlc/context/architecture.md` — "Template anatomy" row for `lesson-template.md`: `(id, title, component, domain, stack, concerns, tags, req, created, updated, kind, evidence, confidence, enforcement, generalizes, supersedes)`. "Knowledge retrieval (current and evolving)" paragraph: replace with a description of the REQ-258 weighted-score retriever (three corpora, top-15), the v2 attribution fields and what reads them (`/review` escalation exemptions, `/spec` superseded annotation), the `NO_ENTRY` summary-slot contract shared by `/wrapup` and `/bugfix`, and `partials/lesson-check.sh` (`adlc_lesson_check`, 0/1/2) as the structural guard on every capture write, with the `lesson-check-order` lint guarding its placement. Do not use the retired `2>/dev/null || . ~/.claude/…` sourcing literal anywhere (`source-guard.test.sh` case (e) counts it in `.adlc/context/*.md`).
- `CHANGELOG.md` — under `## [Unreleased]`, above the existing `### Fixed`: `### Added` (lesson schema v2 fields; `partials/lesson-check.sh` + harness; `lesson-check-order` lint) and `### Changed` (capture prompts carry the four rules; `/review` no longer escalates on `confidence: low`/superseded; `/spec` annotates superseded lessons; `/bugfix` writes before it rechecks; `NO_ENTRY` summary slot in both skills). Cite REQ-646.

## Acceptance Criteria

- [ ] `.adlc/context/architecture.md` names all six new fields, `NO_ENTRY`, `adlc_lesson_check` and `lesson-check-order`, and no longer says "3-tier grep"
- [ ] `grep -c '2>/dev/null || \. ~/.claude' .adlc/context/architecture.md` is 0
- [ ] `CHANGELOG.md` `[Unreleased]` has `### Added` and `### Changed` sections referencing REQ-646
- [ ] `python3 tools/lint-skills/check.py` clean; `sh partials/tests/run.sh` green (including `architecture_doc_names_six_fields`, which stops skipping once this task lands)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-11 | structural-check | `partials/tests/lesson-check.test.sh::architecture_doc_names_six_fields` | no |
| AC-13 | structural-check | `partials/tests/lesson-check.test.sh::architecture_doc_names_six_fields` | no |

## Technical Notes

- Keep the architecture paragraph factual about what reads each field: `confidence` and `supersedes` have readers after this REQ; `enforcement` and `generalizes` do not yet (REQ-646 Out of Scope) — say so rather than implying a consumer.
- The harness case `architecture_doc_names_six_fields` was written in TASK-105 with a skip-with-notice until this doc lands; after this task it must pass, not skip — verify the run output shows it as PASS.
