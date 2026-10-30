---
id: TASK-183
title: "description-budget and skills-ref lint checks; trim the two long descriptions"
status: complete
parent: REQ-666
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Add `description-budget` (512 code points) and `skills-ref` (optional PATH
validator, frontmatter-normalised staged copy, SKIP when absent) to
`tools/lint-skills` (ADR-7). Trim `/adversary` and `/template-drift`
descriptions without losing a trigger phrase.

## Files to Create/Modify

- `tools/lint-skills/check.py` — the two checks
- `tools/lint-skills/tests/test_description_budget.py` — new: one-over fires, code-points-vs-bytes fixture, tree clean, sum printed
- `tools/lint-skills/tests/test_skills_ref.py` — new: absent → one SKIP line, exit unchanged; fake validator on PATH → name-mismatch fixture fires, staged copy omits `argument-hint`
- `adversary/SKILL.md` — description
- `template-drift/SKILL.md` — description

## Acceptance Criteria

- [ ] a fixture one code point over the budget fires; one over in code points but under in bytes fires too; the tree is clean and the sum is printed
- [ ] with `skills-ref` absent the lint prints one SKIP line and exits 0
- [ ] with a fake `skills-ref` on PATH, a fixture whose `name:` differs from its directory produces a finding
- [ ] `/adversary` and `/template-drift` keep their "Use when" phrases

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-7 | test-case | `tools/lint-skills/tests/test_description_budget.py::test_repo_clean_and_sum_printed` | yes |
| AC-7 | test-case | `tools/lint-skills/tests/test_description_budget.py::test_one_code_point_over_fires` | yes |
| BR-11 | test-case | `tools/lint-skills/tests/test_skills_ref.py::test_absent_validator_skips` | yes |
| AC-10 | test-case | `tools/lint-skills/tests/test_skills_ref.py::test_name_mismatch_fires_with_validator` | no |

## Technical Notes

The fake validator in the test is a POSIX script that fails when `name:` differs
from its directory's basename and when an unknown key is present, so the test
also proves the staged copy dropped `argument-hint`.
