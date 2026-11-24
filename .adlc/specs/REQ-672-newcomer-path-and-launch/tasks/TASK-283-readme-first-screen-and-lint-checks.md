---
id: TASK-283
title: "README first screen and the two lint checks"
status: complete
parent: REQ-672
created: 2026-11-23
updated: 2026-11-23
dependencies: [TASK-278, TASK-280]
repo: adlc-toolkit
---

## Description

Restructure the README so its first screen leads with what ADLC is, what a run produces
and the install, and add the two `tools/lint-skills` checks that hold the README and the
quickstart true: `readme-first-screen` and `newcomer-docs` (architecture ADR-9).

## Files to Create/Modify

- `README.md` — the first screen above the first `##`: one sentence, the three outcomes, the two install commands, a link to `docs/quickstart.md`; `## Install` keeps what followed the commands; everything else stays where it is
- `tools/lint-skills/check.py` — the two check ids, their functions, their calls in `run()`, the module docstring
- `tools/lint-skills/README.md` — one numbered item per new check, continuing the numbering
- `tools/lint-skills/tests/test_newcomer_docs.py` — both checks on broken copies of the real files and on the real tree
- `tools/lint-skills/tests/test_manifest_parity.py` — re-pin the README install pin to its intent: the plugin commands come first, above `## Contributing and live install`
- `space/toolkit-data.js` — regenerate with `node space/build.mjs` only if `node space/build.mjs --check` reports drift

## Acceptance Criteria

- [x] Above the README's first `##`: the `what` marker over one sentence, the `outcomes` marker over exactly three list items naming a validated spec, a reviewed PR and a captured lesson, the `install` marker over a fence holding the two `claude plugin` lines, in that order, and no `recording` marker while `docs/demo.gif` and `docs/demo.cast` do not exist
- [x] The skill table's heading comes after the first `##`, and the loader and hook detail is below the first screen
- [x] `readme-first-screen` fails a copy of the README with: a marker missing, two markers out of order, an `outcomes` list of two items, an `install` fence missing a command, a `recording` marker with no `docs/demo.gif`, a `docs/demo.gif` with no `recording` marker, the skill table above the first `##`, and a Hugging Face Space, dataset or blog link while its checklist row is not `live`
- [x] `readme-first-screen` passes a copy whose checklist row is `live` and whose README links that item
- [x] `newcomer-docs` fails a README copy holding `<owner>`, a quickstart copy holding an angle-bracket token in a marked step, a copy naming `/adlc:nosuchskill`, a copy with a bare nonexistent skill opening a code span, and a quickstart whose first two steps differ from the README's install fence
- [x] `newcomer-docs` passes `REQ-xxx` in the quickstart's last step and passes every existing skill name
- [x] Both checks pass on the real tree, each reports the files it scanned, and each fails when it scanned none
- [x] `sh tools/lint-skills/check.sh` passes, and so do `python3 -m pytest tools/lint-skills -q`, `node --test 'space/tests/*.test.js'` and `node space/build.mjs --check`
- [x] No README line that another test pins is lost: the four `claude plugin` lines, `## Contributing and live install`, the harness sections and their `harness-loss` and `exec-residuals` markers, `git clone --branch <tag>`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/lint-skills/tests/test_newcomer_docs.py::test_first_screen_rules_on_broken_copies` | yes |
| BR-10 | test-case | `tools/lint-skills/tests/test_newcomer_docs.py::test_placeholders_and_nonexistent_skills_fail` | yes |
| BR-11 | test-case | `tools/lint-skills/tests/test_newcomer_docs.py::test_hugging_face_links_need_a_live_checklist_row` | yes |
| AC-1 | test-case | `tools/lint-skills/tests/test_newcomer_docs.py::test_real_tree_passes_both_checks` | yes |
| AC-4 | test-case | `tools/lint-skills/tests/test_newcomer_docs.py::test_owner_placeholder_and_nonexistent_skill_fixtures_fail` | no |
| AC-11 | test-case | `tools/lint-skills/tests/test_newcomer_docs.py::test_real_readme_has_no_hugging_face_link_while_rows_are_pending` | yes |

Lessons: LESSON-019, LESSON-020, LESSON-404, LESSON-581, LESSON-749, LESSON-763, LESSON-764

## Technical Notes

- Read these before touching the README, and keep every one green: `tools/lint-skills/tests/test_manifest_parity.py` (near lines 1060-1090, 1144-1171, 1257-1279), `test_plugin_manifest.py` (463-499), `test_harness_lints.py` (123-180), `test_harness_loss_table.py`, `test_builtin_collision.py` (385-403), `tools/delegate/tests/test_no_kimi_brand.py`, `space/build.mjs` (199-215) and `space/tests/build.test.js`.
- `check_harness_loss_tables` (`check.py` near line 5551) is the template for a README-reading check: an id constant, `Finding(rel, lineno, ID, msg)`, registration in `run()`.
- `test_skill_text_portability.py` (near 315) requires gapless numbering in the lint README and that each new id appears there.
- The lint reads the checklist table itself with a small row parser and does not import `tools/launch`. A missing checklist reads as every row not live.
- The marked-step grammar is `tools/launch/quickstart_steps.py`'s; mirror its marker regex in `check.py` in one constant, with a comment naming that file, and add a test that the two agree on the real page.
- A bare skill name is checked only where it opens an inline code span or a marked step and has no second slash, so paths such as `/bin/sh` are not candidates. Run the check on the real README first and read every hit before fixing the allowlist of harness built-ins: an allowlist entry must be a name the harness owns, not a way to silence a hit.
- Lines of the first screen that name a watched built-in must carry both spellings (conventions.md "Skill names Claude Code also owns"); `builtin-collision` scans the README.
- The one sentence: say what the toolkit is in plain words. The three outcomes are the spec's: a validated spec, a reviewed PR, a captured lesson.
- Do not add a Hugging Face link, a recording line, or any claim about adoption.
