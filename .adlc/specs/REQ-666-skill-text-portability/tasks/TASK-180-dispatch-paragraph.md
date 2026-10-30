---
id: TASK-180
title: "One portable dispatch paragraph and the dispatch-has-fallback check"
status: complete
parent: REQ-666
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-179]
repo: adlc-toolkit
---

## Description

Replace REQ-669's dispatch sentence with the portable paragraph (ADR-4) in
conventions.md's `<!-- dispatch-fallback-sentence -->` block, add the
`<!-- dispatch-requires-subagents -->` block for `/sprint`, and copy the
paragraph into every dispatching step: `architect`, `review`, `optimize`,
`reflect`, `analyze` (condensed checklist dropped, read-only rule kept),
`adversary`, `proceed` (both modes) and its Phase 4 and lite companions,
`agents/pipeline-runner.md`. `bugfix` gets the leading clause with its
"trace the bug yourself" inline arm. `/sprint` gets the explicit-stop block and
its `pipeline-runner.md` references point at `.adlc/agents/` first. Rename the
check `dispatch-fallback` to `dispatch-has-fallback` and widen it to generic
dispatch instructions.

## Files to Create/Modify

- `.adlc/context/conventions.md` — the two blocks, Agent dispatch patterns prose
- `tools/lint-skills/check.py` — rename and widen the check, read the second block
- `tools/lint-skills/tests/test_check.py` — rename references
- `tools/lint-skills/tests/test_dispatch_has_fallback.py` — new: AC-11 fixtures (missing fallback, canonical paragraph, explicit stop, leading-clause-only for a built-in)
- `architect/SKILL.md` — paragraph
- `review/SKILL.md` — paragraph
- `optimize/SKILL.md` — paragraph
- `reflect/SKILL.md` — paragraph
- `analyze/SKILL.md` — paragraph, condensed checklist dropped
- `adversary/SKILL.md` — paragraph
- `bugfix/SKILL.md` — leading clause with the trace-it-yourself arm
- `proceed/SKILL.md` — paragraph in Phase 4 summary and Phase 5
- `proceed/phase-4-implementation.md` — paragraph
- `proceed/phases-lite.md` — paragraph
- `agents/pipeline-runner.md` — subagent-mode wording points at `.adlc/agents/`
- `sprint/SKILL.md` — explicit-stop block, `.adlc/agents/pipeline-runner.md` references

## Acceptance Criteria

- [ ] `dispatch-has-fallback` reports exactly one finding on "launch 3 agents using the Agent tool" with no fallback, none on the canonical paragraph, none on the explicit-stop block
- [ ] REQ-669's must-not-fire cases still do not fire
- [ ] every dispatch point in the named files carries the paragraph; `grep -rn '~/.claude/agents' */SKILL.md agents/ partials/` is empty
- [ ] the lint is clean on the tree, and the repo-clean test asserts each dispatching file has a mention (non-vacuous)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/lint-skills/tests/test_dispatch_has_fallback.py::test_repo_clean_and_non_vacuous` | yes |
| BR-4 | test-case | `tools/lint-skills/tests/test_dispatch_has_fallback.py::test_paragraph_names_init_and_toolkit_fallback` | no |
| BR-12 | test-case | `tools/lint-skills/tests/test_dispatch_has_fallback.py::test_generic_dispatch_without_fallback_fires_once` | yes |
| AC-4 | test-case | `tools/lint-skills/tests/test_dispatch_has_fallback.py::test_no_claude_agents_literal` | no |
| AC-11 | test-case | `tools/lint-skills/tests/test_dispatch_has_fallback.py::test_explicit_stop_is_clean` | yes |

## Technical Notes

Keep the marker names; only the block text changes. The paragraph contains
`/init` and must carry `(`/adlc:init` on the plugin install)` for
`builtin-collision`.
