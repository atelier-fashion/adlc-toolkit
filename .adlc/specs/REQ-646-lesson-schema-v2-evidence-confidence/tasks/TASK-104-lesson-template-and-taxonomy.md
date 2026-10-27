---
id: TASK-104
title: "Add the six v2 fields to lesson-template.md and document the three enums in taxonomy-template.md"
status: complete
parent: REQ-646
created: 2026-10-27
updated: 2026-10-27
dependencies: []
---

## Description

Additive template change (REQ-646 BR-1). Six one-line fields go into
`templates/lesson-template.md` after `updated:` and before the closing `---`; the
frontmatter block, HTML comment included, must close at **line 25 or earlier** (it closes
at 19 today — six lines leaves zero slack, so every field is exactly one line with a
single-line trailing comment). `templates/taxonomy-template.md` gains three sections for
the fixed enums (ADR-7: these are enforced vocabularies, not advisory tags — say so).

## Files to Create/Modify

- `templates/lesson-template.md` — insert, after the `updated:` line and before the closing `---`, exactly:
  ```yaml
  kind: ""            # process | domain — how a skill/agent/pipeline works vs what an implementer must know
  evidence: ""        # the moment: a commit sha, BUG-/REQ-/LESSON-/TASK-nnn, path:line, or test name. No home paths.
  confidence: ""      # high | medium | low — see the contrast rule in the capture prompt
  enforcement: none   # none | lint:<check-id> | test:<path> | script:<path> | hook:<name>
  generalizes: []     # LESSON ids this one generalizes
  supersedes: []      # LESSON ids this one replaces
  ```
  No existing line changes. The `## Applies When` section's hint line gains one sentence: "This is the cue — required on every lesson the capture steps write."
- `templates/taxonomy-template.md` — before `## tags (free-form)`, add `## kind (lesson scope)`, `## confidence (lesson evidence strength)`, `## enforcement (lesson structural guard)`. Each: the `## field (descriptor)` heading, a shape line ("Single string. Fixed vocabulary — `adlc_lesson_check` rejects any other value; not project-extensible."), the values with one-line meanings (for `confidence`, the contrast rule in three lines; for `enforcement`, the four patterns), and no "Values are project-local" paragraph. Do not change the intro's advisory wording for the retrieval tags.

## Acceptance Criteria

- [ ] `awk '/^---$/{n++; if(n==2){print NR; exit}}' templates/lesson-template.md` prints a number ≤ 25
- [ ] `git diff templates/lesson-template.md` shows only added lines (plus the one-sentence addition to the Applies When hint)
- [ ] All six keys are present, each on one line, each with a trailing `#` comment
- [ ] `templates/taxonomy-template.md` has the three new `##` sections before `## tags (free-form)` and the file's intro still calls the retrieval tags advisory
- [ ] A fixture lesson built from the new template with all six fields filled has its closing `---` within the first 30 lines and its five retrieval-tag fields byte-identical to the same fixture without the six keys (the `/spec` Step 1.6 scorer therefore scores both identically)
- [ ] Manual dogfood (AC-12): on a fixture consumer directory holding the *old* vendored `lesson-template.md`, `/template-drift` reports `lesson-template.md` as `stale`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `partials/tests/lesson-check.test.sh`: `template_frontmatter_closes_by_line_25`, `taxonomy_documents_three_enums` | no |
| BR-9 | structural-check | `tools/lint-skills`: `sync-surface-parity` (unchanged surface lists still pass — the partial and template ride existing globs) | yes |
| AC-1 | structural-check | `partials/tests/lesson-check.test.sh`: `template_frontmatter_closes_by_line_25`, `template_has_six_fields_one_line_each` | no |
| AC-2 | structural-check | `partials/tests/lesson-check.test.sh`: `six_field_fixture_frontmatter_within_30_lines_and_tags_unchanged` | yes |

## Technical Notes

- Zero slack: a two-line comment on any field pushes the closing `---` to 26 and breaks BR-1. Keep comments to one line; shorten them rather than wrap.
- Quote the string defaults (`""`) so a future value containing `: ` cannot make the YAML unparseable for `/spec` Step 1.6's prose parse (which drops malformed docs silently).
- The harness cases cited above are implemented in TASK-105; this task only has to produce files those cases pass against. Coordinate the exact case names with TASK-105 (same tier — both land before TASK-109's lint run).
- `/init` copies `templates/*.md` by glob and `/template-drift` already classifies "toolkit added a field" as accidental staleness; no sync-surface list edit (BR-9).
