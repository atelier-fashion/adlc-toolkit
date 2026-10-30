---
id: TASK-186
title: "Documentation: architecture, conventions, lint README, partials docs, README, CHANGELOG"
status: complete
parent: REQ-666
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-179, TASK-180, TASK-181, TASK-182, TASK-183, TASK-184, TASK-185]
repo: adlc-toolkit
---

## Description

Move the documentation with the code (BR-17): architecture.md "Skill anatomy"
items 3–5 and "Agent anatomy" (and the REQ-669 reconciliation bullet for this
REQ); conventions.md "Context loading pattern", "Ethos injection pattern",
"Agent dispatch patterns"; the lint README renumbered with the five new checks
and without the retired ones (BR-14); `partials/README.md`; `README.md`'s skill
catalog if it quotes a trimmed description; a CHANGELOG entry naming the
reversals (BUG-228, BUG-230 in part, REQ-646 BR-15/ADR-8, REQ-648 BR-3 in
part), telling consumers to re-run `/init`, and listing the allowlist additions.

## Files to Create/Modify

- `.adlc/context/architecture.md` — skill and agent anatomy, reconciliation bullet
- `.adlc/context/conventions.md` — context loading, ethos, dispatch
- `tools/lint-skills/README.md` — renumbered list
- `partials/README.md` — Teton lines gone, agents vendoring noted
- `README.md` — catalog descriptions, if quoted
- `CHANGELOG.md` — the entry

## Acceptance Criteria

- [ ] architecture.md and conventions.md describe the context block, the Input prose and the dispatch paragraph and hold no Teton paragraph
- [ ] the lint README lists the five new checks and none of the retired ones
- [ ] the CHANGELOG entry names BUG-228, BUG-230, REQ-646 BR-15 and REQ-648 BR-3 as reversed in part and tells consumers to re-run `/init`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-14 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_lint_readme_lists_new_checks_only` | no |
| BR-17 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_docs_describe_the_new_shapes` | no |
| AC-6 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_changelog_names_reversals` | no |
| AC-13 | structural-check | `tools/lint-skills`: full run exits 0; `pytest tools/lint-skills/tests tools/adlc/tests`; `sh partials/tests/run.sh` | no |
| AC-14 | structural-check | `tools/lint-skills`: telemetry fences unchanged (`canonical`, `cross-fence-*`); live runs recorded as a manual item in the PR | no |
| AC-15 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_docs_describe_the_new_shapes` | no |
