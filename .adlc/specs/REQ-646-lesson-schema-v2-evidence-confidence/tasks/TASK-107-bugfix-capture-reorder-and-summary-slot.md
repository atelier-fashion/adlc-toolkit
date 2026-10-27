---
id: TASK-107
title: "/bugfix Phase 6 Step 4: write before recheck, the same four capture rules, adlc_lesson_check fence + repair loop, Teton note; Step 6 NO_ENTRY slot"
status: complete
parent: REQ-646
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-105]
---

## Description

`bugfix/SKILL.md` Phase 6 Step 4 today allocates, rechecks, and only *then* says "Use the
lesson template" — the write comes after the recheck. REQ-646 BR-3 reorders it:
allocate → write (`<!-- lesson-write-point -->`) → check → recheck. The capture prompt
becomes the same marker-delimited rules block as `/wrapup` (byte-equal — TASK-109's
lint diffs them), with the BR-15 Teton line this step currently lacks. Step 6's summary
template gets the `NO_ENTRY: <reason>` form (BR-14).

## Files to Create/Modify

- `bugfix/SKILL.md` — Phase 6 Step 4:
  1. Replace the "Evaluate honestly … A surprising failure mode / pattern / check / assumption" bullets with the `<!-- lesson-capture-rules -->` … `<!-- /lesson-capture-rules -->` block, **byte-identical** to TASK-106's (copy from `wrapup/SKILL.md` after TASK-106 lands, or from the text in TASK-106's spec — same bytes either way). Keep the "did this bug reveal something a future implementer should know?" lead sentence above the block; the four original bullets become examples in one trailing sentence.
  2. Keep the allocation fence where it is.
  3. Move the "Use the lesson template (…) Filename format … Include `domain`, `component`, and `tags`…" paragraph to immediately after the allocation fence, extend it with `kind`, `evidence`, `confidence`, and precede it with a line that is exactly `<!-- lesson-write-point -->`.
  4. Insert the Teton line and the check fence (same text as TASK-106 item 5, with the `/bugfix:` wording where the skill name appears), then the repair-loop prose (bound 2 → `NO_ENTRY: schema check failed — <field>`; not a halt), then the existing pre-push recheck fence.
  5. Replace "If the bug genuinely produced no useful lesson (one-line typo, etc.), say so explicitly in the final summary — don't silently skip." with: "If nothing transferable survived, the summary's `### Lessons captured` carries exactly one line `NO_ENTRY: <reason>` — never a silent skip."
- `bugfix/SKILL.md` — Step 6 "Final ship summary" template: replace `(or "None — fix was straightforward and revealed no new pattern")` with `(or exactly one line: NO_ENTRY: <reason>)`.

## Acceptance Criteria

- [ ] In `bugfix/SKILL.md`, file order is: allocation fence → `<!-- lesson-write-point -->` → check fence (`adlc_lesson_check `) → recheck fence (`adlc_recheck_id lesson`)
- [ ] `diff <(sed -n '/<!-- lesson-capture-rules -->/,/<!-- \/lesson-capture-rules -->/p' wrapup/SKILL.md) <(sed -n '/<!-- lesson-capture-rules -->/,/<!-- \/lesson-capture-rules -->/p' bugfix/SKILL.md)` is empty
- [ ] The Teton line is within 30 lines above the check fence
- [ ] Step 6's template no longer contains "None — fix was straightforward" and does contain `NO_ENTRY: <reason>`
- [ ] `python3 tools/lint-skills/check.py` is clean for `bugfix/SKILL.md`; `source-guard.test.sh` passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | structural-check | `tools/lint-skills`: `lesson-check-order` (write-point → check → recheck in `bugfix/SKILL.md`) | no |
| BR-3 | structural-check | `tools/lint-skills`: `lesson-check-order` (the reorder is what the check proves) | yes |
| BR-4 | structural-check | `tools/lint-skills`: `lesson-check-order` (rules block byte-equal to wrapup's) | no |
| BR-5 | structural-check | `tools/lint-skills`: `lesson-check-order` | no |
| BR-14 | structural-check | `partials/tests/lesson-check.test.sh::bugfix_summary_uses_no_entry_form` | no |
| BR-15 | structural-check | `tools/lint-skills`: `lesson-check-order` (Teton line within 30 lines above the fence) | no |
| AC-4 | structural-check | `tools/lint-skills`: `lesson-check-order` | no |
| AC-6 | structural-check | `tools/lint-skills`: `lesson-check-order` | no |

## Technical Notes

- Same fence constraints as TASK-106: canonical guarded source line, literal path, no `# provenance-safe`, no `$<digit>`.
- Case `bugfix_summary_uses_no_entry_form` (greps Step 6's template for `NO_ENTRY: <reason>` and the absence of the old parenthetical) is added to the harness by **TASK-109**; this task does not touch `partials/tests/lesson-check.test.sh`.
- `/bugfix` has no delegated path; only the fallback-style prose exists, so there is one rules block and no `--question` copy here.
