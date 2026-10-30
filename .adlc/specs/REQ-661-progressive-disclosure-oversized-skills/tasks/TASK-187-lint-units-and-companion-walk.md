---
id: TASK-187
title: "lint-skills: skill units, the companion walk, unit-scoped cross-fence checks, skill-line-budget and companion-templating"
status: complete
parent: REQ-661
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Teach `tools/lint-skills/check.py` the skill unit (architecture ADR-6 to ADR-8): one
companion helper derived from the `SKILL.md` walk, every per-file check over every
companion, `cross-fence-fn`/`cross-fence-var`/`canonical-helper` across the unit, the
`ethos-line` companion rule, `skills-ref` staging the companions, a `*/references/*.md`
surface for `no-harness-path` and `builtin-collision`, and the two new checks. Lands
before any content moves, so every move is checked by the widened walk (LESSON-019).

## Files to Create/Modify

- `tools/lint-skills/check.py` — `find_skill_units`, `skill_companions`, `find_companion_files`; `run()` walks companions; unit-scoped cross-fence and canonical checks; `check_skill_line_budget`, `check_companion_templating`; `ethos-line` companion mode; `skills-ref` staging; `*/references/*.md` surface; docstring
- `tools/lint-skills/tests/test_skill_units.py` — new: fixtures for AC-2, AC-5, AC-7, AC-8 and the BR-9 count
- `tools/lint-skills/tests/test_toolkit_path.py` — a plant for the new surface
- `tools/lint-skills/tests/test_builtin_collision.py` — a plant for the new surface
- `tools/lint-skills/tests/test_skill_text_portability.py` — read the placeholder from `check.ARGUMENT_PLACEHOLDERS`
- `tools/lint-skills/README.md` — document the two checks, the companion walk and the unit scope

## Acceptance Criteria

- [ ] A 500-line `SKILL.md` fixture reports `skill-line-budget` naming 500 and the budget; a 499-line one reports nothing
- [ ] A companion with `'<request>'`, and one with an inline bang line, each report `companion-templating`; the same text in a `SKILL.md` does not
- [ ] For each of the eleven per-file checks, a known-bad construct in `x/references/a.md` and in `proceed/phases-x.md` reports that check; a companion ETHOS line reports `ethos-line`; a clean companion reports no `description-budget`/`skills-ref` finding; `scanned` counts only `SKILL.md`
- [ ] A function defined in `SKILL.md` and called in `references/x.md` reports `cross-fence-fn` at the call site; same for a variable; a canonical literal only in a companion satisfies `canonical-helper`
- [ ] On the unsplit tree the lint reports only `skill-line-budget` on the three over-budget skills; after the splits it is clean and `pytest tools/lint-skills/tests` passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_line_budget_fires_at_500_not_499` | yes |
| BR-6 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_companion_templating` | yes |
| BR-7 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_every_per_file_check_walks_companions` | yes |
| BR-8 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_cross_fence_checks_span_the_unit` | yes |
| BR-9 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_scanned_counts_skill_md_only` | yes |
| BR-15 | structural-check | `tools/lint-skills`: posix-fence, arg-templating, unguarded-source over companions | no |
| AC-2 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_line_budget_fires_at_500_not_499` | yes |
| AC-5 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_companion_templating` | yes |
| AC-7 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_every_per_file_check_walks_companions` | yes |
| AC-8 | test-case | `tools/lint-skills/tests/test_skill_units.py::test_cross_fence_checks_span_the_unit` | yes |
| AC-14 | test-case | `pytest tools/lint-skills/tests` | no |
| AC-18 | structural-check | `tools/lint-skills/README.md`, `check.py` docstring: grep `skill-line-budget`, `companion-templating` | no |

## Technical Notes

- Companions come from the units `find_skill_files` yields, so the pruning a concurrent
  fix adds for nested `.claude/worktrees/` applies to them automatically. Keep
  `<root>/proceed/phase*.md` walked without a `proceed/SKILL.md` (existing fixtures).
- `find_phase_files` keeps its return value; `run()` gives its `partials/*.md` members the
  three checks they get today and skips the ones already walked as companions.
- Within-file cross-fence findings must be byte-identical to today's, so existing tests
  keep passing.
- `wc -l` is `text.count("\n")`.
