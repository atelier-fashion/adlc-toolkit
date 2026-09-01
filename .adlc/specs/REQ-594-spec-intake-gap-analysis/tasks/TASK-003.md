---
id: TASK-003
title: "Wire Provenance section and gap dispositions into Step 3 spec authoring"
status: complete
parent: REQ-594
created: 2026-08-31
updated: 2026-08-31
dependencies: [TASK-002]
repo: adlc-toolkit
---

## Description

Teach Step 3 to persist the intake result: a `## Provenance` section carrying the full
classified gap table, plus the per-disposition mirrors into Assumptions and Open
Questions (ADR-4). Document the optional section in the requirement template.

## Files to Create/Modify

- `spec/SKILL.md` — Step 3 sub-step 3 and a new sub-step for Provenance
- `templates/requirement-template.md` — document the optional Provenance section

## Acceptance Criteria

- [ ] Step 3 emits `## Provenance` **only** on the intake path. A spec written without intake has no Provenance heading and no placeholder (BR-8, BR-11, ADR-5).
- [ ] `## Provenance` records the source basename, `kind`, and intake date — never a full local path (BR-7, BR-8).
- [ ] `## Provenance` carries the full gap table with columns for section, severity, question, and disposition (AC-2).
- [ ] `assumption`-severity gaps are written into `## Assumptions` with the `question` text **verbatim**, so a grep of the output file for the gap text succeeds (AC-5).
- [ ] Blocking gaps left unanswered in non-interactive mode are written into `## Open Questions`, verbatim, marked blocking (BR-4).
- [ ] A source that produces zero gaps adds no Assumptions entries and no Open Questions entries from intake; the only difference from a non-intake spec is the Provenance section (BR-11).
- [ ] The requirement template documents Provenance as an optional, intake-only section, so the 45 existing specs stay valid without migration.
- [ ] `sh tools/lint-skills/check.sh` exits 0.

## Technical Notes

AC-5's "verbatim" is load-bearing and is what the test greps for. Write the assumption
entry so the gap `question` survives unmodified — put the surrounding commentary around
it, not inside it. A format that satisfies this:

```
- <question text verbatim> — assumed: <the assumption>. (intake gap: <section>)
```

Provenance duplicates gaps that also appear in Assumptions/Open Questions. That is
deliberate (ADR-4): Provenance is the audit record, the other two are the surfaces the
rest of the pipeline already reads. Do not "optimize" the duplication away.

`templates/` changes propagate to consumer projects via `/template-drift` detection, not
auto-update. Adding an optional section is additive and safe; do not reorder or rename
any existing section.
