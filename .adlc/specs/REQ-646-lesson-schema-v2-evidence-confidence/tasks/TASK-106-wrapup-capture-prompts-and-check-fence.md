---
id: TASK-106
title: "/wrapup Step 4: four capture rules in both prompt sites, write-point marker, adlc_lesson_check fence with the bounded repair loop, Teton note; Step 5 cross-repo Lessons-captured body"
status: complete
parent: REQ-646
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-105]
---

## Description

`wrapup/SKILL.md` carries REQ-646 BR-2, BR-3 (placement + repair loop), BR-4, BR-5,
BR-8, BR-12 (prompt guidance), BR-14 and BR-15. The capture rules are written **once
per skill as a marker-delimited block** so TASK-109's lint can diff it against
`/bugfix`'s copy, and repeated inside the delegated `--question` string (which is
double-quoted in a shell fence — no backticks, no `$`, no `"` in the rule text).

## Files to Create/Modify

- `wrapup/SKILL.md` — Step 4 "Lessons Learned":
  1. **Delegated path, item 2 (`--question`)**: extend the question so it also requires the six new frontmatter fields and carries the four rules verbatim (plain text; rule (3)'s `NO_ENTRY: <reason>` is fine inside double quotes; write "be thorough" without quotes).
  2. **Delegated path, item 4 (post-validation)**: add BR-8 — every `generalizes`/`supersedes` id the draft proposes must match `^LESSON-[0-9]{3,6}$` and exist (`find .adlc/knowledge/lessons -maxdepth 1 -name '<id>-*' | head -1`, not a bare glob — LESSON-335); drop otherwise, note the drop. Scope the existing path-citation sanitiser to *body* citations so a `path:line` in `evidence` is not rejected.
  3. **Delegated path, item 5 → the shared write point.** Replace "then writes the final lesson file using the file-naming + counter rules in **Fallback drafting** below" with a pointer to the new **Write and check** block; move the delegated success line (item 6) to *after* the check passes.
  4. **Fallback drafting bullets**: replace the three "Consider:" bullets with the marker-delimited rules block:
     ```
     <!-- lesson-capture-rules -->
     Lesson capture rules (REQ-646):
     0. Declare kind: process if the lesson is about how a skill, agent, partial or pipeline phase behaves; domain if it is about the codebase or stack the implementer works in.
     1. Cite the moment: a lesson you cannot trace to a specific commit, finding, bug, test or transcript line is speculation; put that moment in evidence (a commit sha, a BUG-/REQ-/LESSON-/TASK- id, a path:line, or a test name). Never a home-directory path: write ~/ for the home prefix rather than dropping the citation.
     2. Declare the contrast: confidence is decided by whether the evidence contains a contrast - a bug reproduced then fixed, a test failing then passing, a Phase-5 finding confirmed by its fix and re-verify, or two approaches or runs compared. high = a contrast was observed and the evidence names the mechanism (a specific line, command or finding); medium = a contrast was observed but the mechanism is inferred; low = a single observation with no contrast. An invented attribution poisons retrieval for every later REQ.
     3. NO_ENTRY is a valid answer: if nothing transferable survived, write NO_ENTRY: <reason> in the summary slot; never pad.
     Granularity: too generic never changes behaviour (be thorough); too specific never fires again (the fee rose on Jan 1) - aim between.
     <!-- /lesson-capture-rules -->
     ```
     Keep the existing template / filename / allocation / recheck bullets. The "Include `domain`, `component`, and `tags`" bullet also names `kind`, `evidence`, `confidence`.
  5. **Write and check** (new, shared by both paths; sits after the allocation fence and **before** the pre-push recheck fence): a line that is exactly `<!-- lesson-write-point -->` (own line, column 0), the instruction to write `LESSON-<id>-<slug>.md` from the template with every required field, then the Teton line `**Provenance-classifying harness (BUG-228):** … validate in-model against the rule table in partials/lesson-check.md and write "lesson check: in-model (provenance-classifying harness)" in the summary slot; run none of the fence below`, then the fence:
     ```sh
     if [ -f .adlc/partials/lesson-check.sh ]; then . .adlc/partials/lesson-check.sh; else . ~/.claude/skills/partials/lesson-check.sh; fi
     # <path> is the LITERAL path of the file you just wrote — thread it in; fenced
     # blocks share no shell state and LESSON_ID is not a sanctioned cross-fence var.
     adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md
     ```
     followed by the repair loop prose (ADR-4): on exit 1 repair only the named frontmatter field(s) and re-run the fence; at most two repairs; after the third failure delete the draft and write `NO_ENTRY: schema check failed — <field>` to the summary slot; this is not a pipeline halt — Steps 5–8 run regardless; then the existing recheck fence follows unchanged.
  6. **Step 5** cross-repo template: give `### Lessons captured` the same two-line body the single-repo template has.
- `wrapup/SKILL.md` — Close-out mode rule 4 already says NO_ENTRY on no evidence; add "and validate with `adlc_lesson_check` like any other write" (one clause).

## Acceptance Criteria

- [ ] `wrapup/SKILL.md` contains, in file order: `<!-- lesson-write-point -->` (own line), a fence whose non-comment line starts `adlc_lesson_check `, then a fence whose non-comment line starts `adlc_recheck_id lesson`
- [ ] The marker-delimited rules block exists once; the four rule lines also appear inside the delegated `--question` string; no backtick, `$` or `"` appears inside the question's rule text
- [ ] The repair-loop prose names the bound (2) and the `NO_ENTRY: schema check failed — <field>` fallback, and says it is not a halt point
- [ ] The Teton line sits within 30 lines above the check fence and names the in-model summary text
- [ ] `python3 tools/lint-skills/check.py` reports no `cross-fence-var`, `unguarded-source`, `arg-templating` or `balance` finding in `wrapup/SKILL.md`; `partials/tests/source-guard.test.sh` passes (the new sourcing line is extracted and executed)
- [ ] Manual dogfood (AC-8/AC-9): a `/wrapup` with nothing transferable ends with one `NO_ENTRY:` line under `### Lessons captured` and no file; one with a lesson writes `kind`/`evidence`/`confidence` and the check passes first try

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | structural-check | `tools/lint-skills`: `lesson-check-order` (write-point → check → recheck in `wrapup/SKILL.md`) | no |
| BR-3 | structural-check | `tools/lint-skills`: `lesson-check-order`; `cross-fence-var` clean (path is a threaded literal) | yes |
| BR-4 | structural-check | `tools/lint-skills`: `lesson-check-order` (rules block byte-equal across skills; each rule line present twice in wrapup) | no |
| BR-5 | structural-check | `tools/lint-skills`: `lesson-check-order` (the Granularity line is part of the compared block) | no |
| BR-8 | structural-check | `tools/lint-skills`: `unguarded-source`, `arg-templating` over the edited step; `partials/tests/source-guard.test.sh` executes the new sourcing line | yes |
| BR-14 | structural-check | `partials/tests/lesson-check.test.sh::wrapup_templates_carry_lessons_captured` (both Step-5 templates have the section with a body line) | no |
| BR-15 | structural-check | `tools/lint-skills`: `lesson-check-order` requires the `**Provenance-classifying harness (BUG-228):**` line within 30 lines above the check fence | no |
| AC-4 | structural-check | `tools/lint-skills`: `lesson-check-order` | no |
| AC-6 | structural-check | `tools/lint-skills`: `lesson-check-order` (block equality + question coverage) | no |

## Technical Notes

- The fence must keep the canonical one-line guarded source spelling (`unguarded-source`), take the path as a literal (`cross-fence-var`), and not be marked `# provenance-safe`.
- Do not put the rules text inside backticks in prose where it would be mistaken for a fence; the lint reads the block between the HTML markers at line start (LESSON-404).
- The `--question` string: keep it one line inside the existing double-quoted argument; the rule text is plain prose with `-` for dashes and parentheses only.
- `source-guard.test.sh` case (e) counts the retired `2>/dev/null || . ~/.claude/…` literal across `templates/*.md` and `.adlc/context/*.md` — do not introduce it in prose.
- Case `wrapup_templates_carry_lessons_captured` is added to the harness by **TASK-109** (Tier 2 runs alone, so the harness has one writer); this task does not touch `partials/tests/lesson-check.test.sh`.
