---
id: TASK-085
title: "Define the ## Verification obligation shape in task-template.md"
status: draft
parent: REQ-595
created: 2026-08-31
updated: 2026-08-31
dependencies: []
repo: adlc-toolkit
---

## Description

Add the optional `## Verification` section to the canonical task template and
document the convention in `.adlc/context/conventions.md`. This task defines the
shape that TASK-086 (emit) and TASK-087 (gate) both consume, so it lands first.

The section is **optional by design**: the 157 task files already on disk carry
no `## Verification` block and must stay valid (AC-10). Nothing in this change
makes the section required.

## Files to Create/Modify

- `templates/task-template.md` — add an optional `## Verification` section with
  the four-column obligation table (`rule`, `kind`, `artifact`, `benign_path`),
  a filled example row, and a comment stating the section is optional and that
  a task without it remains valid
- `.adlc/context/conventions.md` — add a "Verification obligations" subsection
  recording the table shape, the `BR-`/`AC-` addressing rule (ACs by 1-based
  ordinal within the REQ's `## Acceptance Criteria` list), the two-value `kind`
  enum, and the epoch-1 advisory posture of the coverage gate

## Acceptance Criteria

- [ ] `templates/task-template.md` contains a `## Verification` section with the
      four-column table and at least one example row
- [ ] The template states explicitly that the section is optional and that task
      files without it stay valid
- [ ] `kind` is documented as the closed enum `test-case | structural-check`,
      with `dogfood` named as deliberately excluded
- [ ] AC addressing (1-based ordinal) is documented — the requirement template
      does not print AC numbers, so the rule must be written down somewhere
- [ ] `.adlc/context/conventions.md` carries the convention alongside the
      existing task/commit conventions
- [ ] `python3 tools/lint-skills/check.py --root .` still exits 0 (no SKILL.md
      changed by this task, but the run must stay green and must scan >0 files)

## Technical Notes

Do **not** add a required-field check anywhere. Optionality is what preserves
backward compatibility across the existing corpus (ADR-1).

The template is copied into consumer projects by `/init` and drift-checked by
`/template-drift`. Both operate on the *file list*, not contents, so adding a
section needs no change to either skill's sync surface — confirm this rather
than assuming it (`tools/lint-skills`'s `sync-surface-parity` check covers the
list).

Table column order is `rule | kind | artifact | benign_path` and must match
`architecture.md` exactly — TASK-087's gate reads positionally.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `tools/lint-skills`: sentinels, balance (template + conventions are markdown surfaces; no behavioral runner exists — BR-11 all-`.md` branch) | no |
| BR-7 | structural-check | `tools/lint-skills`: full-root run stays green with no new skill directory created | no |
| AC-10 | structural-check | `tools/lint-skills`: full-root run over the existing 157 `TASK-*.md` corpus, none of which carries the new section | yes |

`benign_path` on AC-10 is the must-not-fire case: the existing obligation-free
task corpus must produce no failure. Kind resolves to `structural-check` for all
three rows because every file this task touches ends in `.md` and this repo has
no `.adlc/config.yml` (BR-11).
