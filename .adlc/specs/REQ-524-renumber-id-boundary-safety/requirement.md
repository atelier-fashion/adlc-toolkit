---
id: REQ-524
title: "adlc renumber: id-boundary-safe rewrites (no prefix-id collateral damage)"
status: complete
deployable: false
created: 2026-06-12
updated: 2026-06-12
component: "tools/adlc"
domain: "id-allocation"
stack: ["python"]
concerns: ["correctness", "data-loss"]
tags: ["renumber", "id-boundary", "prefix-collision", "str-replace", "req-518-followup"]
---

## Description

`adlc renumber` (REQ-518 BR-9) rewrites references to an old artifact id with a boundary-free `str.replace` (`tools/adlc/renumber.py:212`), and selects target files with `git grep -l -- <old_id>` — also boundary-free. Renumbering any id whose number is a string prefix of another live id corrupts the unrelated artifact: `adlc renumber REQ-120 REQ-999 --yes` rewrites `REQ-1200` → `REQ-9990` everywhere it appears, including frontmatter `id:` fields, leaving an artifact whose id no longer matches its directory and may collide with a real id (adversarial finding M2, reproduced end-to-end). The strict id regexes guard only the command's *arguments*, not the content match. `--yes` (documented for the BR-4 collision-halt fix path, scriptable from CI) applies the damage with no second confirmation, and a dry-run user renumbering REQ-120 has no reason to scan the diff for REQ-1200 collateral.

The fix: every content match, filename match, and file-selection grep uses an id-boundary-anchored pattern — the id matches only when not followed by a digit (and, for robustness, not preceded by an alphanumeric) — so `REQ-120` never matches inside `REQ-1200`.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| IdToken | pattern | regex | `<KIND>-<digits>` followed by a non-digit or end-of-string; preceded by a non-alphanumeric or start-of-string |

## Business Rules

- [ ] BR-1: Content rewrites use a boundary-anchored regex substitution (e.g. `re.sub(rf'(?<![A-Za-z0-9]){re.escape(old_id)}(?!\d)', new_id, …)`), never bare `str.replace`. The same boundary applies to filename/dirname rewrites. (adversarial M2)
- [ ] BR-2: File selection uses the same boundary semantics as the rewrite: a file containing only `REQ-1200` is not selected when renumbering `REQ-120`. (`git grep -E` with the equivalent pattern, or post-filtering matches in Python — selection and rewrite must share one pattern definition so they cannot drift.) (informed by LESSON-023 — mirror the rationale; LESSON-016 — substring buckets miscount)
- [ ] BR-3: The dry-run diff explicitly reports the match count per file using the boundary pattern, and a guard test asserts that renumbering `KIND-N` leaves any `KIND-N<digit>` artifact byte-identical.
- [ ] BR-4: Atomic-write behavior (`temp + os.replace`), strict argument-id validation, the remote-collision refusal, and `--yes` semantics are unchanged. (REQ-518 BR-9 preserved)
- [ ] BR-5: No absolute paths in error or diff output. (informed by LESSON-021, BUG-054)

## Acceptance Criteria

- [ ] Regression test: repo fixture containing `REQ-120` and `REQ-1200` artifacts; `adlc renumber REQ-120 REQ-999 --yes` rewrites every `REQ-120` reference, and every `REQ-1200` file is byte-identical afterward.
- [ ] Test: file containing only `REQ-1200` is not listed in the dry-run plan for renumbering `REQ-120`.
- [ ] Test: id at end-of-line, id followed by punctuation (`REQ-120.`, `REQ-120)`, `REQ-120-slug`), and id inside frontmatter all still rewrite correctly. (Note: `REQ-120-slug` directory names MUST rewrite — the boundary is digit-based, not word-based, precisely so `-slug` suffixes still match.)
- [ ] Existing `tools/adlc/tests/` suite passes unchanged.

## External Dependencies

- None.

## Assumptions

- The boundary rule "not followed by a digit" is sufficient for all three kinds (REQ/BUG/LESSON ids are always `KIND-<digits>` followed by a non-digit in legitimate references — slugs, punctuation, whitespace, EOL).

## Open Questions

- [ ] None.

## Out of Scope

- The allocation/recheck derivation defects (REQ-523).
- Renumber support for new artifact kinds.

## Retrieved Context

- LESSON-397 (lesson, score 7): Artifact tools resolve root from caller cwd — renumber's prior fix in the same tool
- LESSON-016 (lesson, score 3): Balance-check substring buckets — substring matching miscounts
- LESSON-023 (lesson, score 3): Mirror the rationale, not just the mechanism
- LESSON-021 (lesson, score 2): str(OSError) embeds absolute path
- REQ-518 (spec, score 4): Collision-safe id allocation — BR-9 introduced `adlc renumber`
