---
id: TASK-113
title: "lite-reviewer agent: one read-only pass covering five dimensions, AC/BR coverage and reversals"
status: draft
parent: REQ-652
created: 2026-10-27
updated: 2026-10-27
dependencies: []
---

## Description

The single review pass the lite lane runs in place of the reflector and the five-agent panel (architecture ADR-7).

## Files to Create/Modify

- `agents/lite-reviewer.md` — new. Read-only tools (Read, Grep, Glob, Bash). Inputs: diff vs `origin/<integrationBranch>`, the spec, the fresh retrieval set. Output: findings by dimension (correctness, quality, architecture, test coverage, security) with severity; a BR/AC table marking each met / partial / unmet; a `reversals:` list naming the REQ or LESSON id and the decision reversed. "Report findings only. Do not apply fixes."
- `tools/adlc/agents_render.py` — add `lite-reviewer` to `_SHIPPED_DEFAULTS` at the same tier as `correctness-reviewer`.
- `tools/adlc/tests/` — extend the agents-render test that enumerates shipped agents so `lite-reviewer` resolves a model.

## Acceptance Criteria

- [ ] The agent file's frontmatter renders with `adlc agents render` and resolves a model.
- [ ] The agent's instructions require an entry for every numbered BR and AC in the spec (LESSON-330), and a `reversals:` section that is present even when empty.
- [ ] `python3 -m pytest tools/adlc/tests -q` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | `tools/adlc/tests/test_agents_render.py::test_lite_reviewer_resolves_a_model` | no |

## Technical Notes

- Base the dimension checklists on the existing reviewer agents rather than writing new criteria; keep it to one page per dimension at most.
- The reversal check reads only the retrieval set it is handed; it does not run its own retrieval (ADR-8 owns that).
- Name the finding format so `/proceed` can branch on it mechanically: a non-empty `reversals:` list escalates (trigger `reversal`).
