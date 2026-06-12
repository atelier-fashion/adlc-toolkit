---
id: TASK-001
title: "Add tier: frontmatter field + derived-model header comment to all 18 agents"
status: complete
parent: REQ-516
created: 2026-06-11
updated: 2026-06-11
dependencies: []
repo: adlc-toolkit
---

## Description

Add a `tier:` frontmatter field to every agent definition in `agents/`, using the
class assignments in `architecture.md` (the shipped-default table). Add a one-line
HTML comment under the frontmatter marking `model:` as rendered output (BR-1). The
existing `model:` values stay byte-identical — only `tier:` and the comment are
added.

## Files to Create/Modify

- `agents/adversary.md` — `tier: reviewer`
- `agents/correctness-reviewer.md` — `tier: reviewer`
- `agents/reflector.md` — `tier: reviewer`
- `agents/security-auditor.md` — `tier: reviewer`
- `agents/architecture-reviewer.md` — `tier: reviewer`
- `agents/quality-reviewer.md` — `tier: reviewer`
- `agents/code-quality-auditor.md` — `tier: reviewer`
- `agents/test-auditor.md` — `tier: reviewer`
- `agents/api-cost-scanner.md` — `tier: scanner`
- `agents/db-perf-scanner.md` — `tier: scanner`
- `agents/latency-scanner.md` — `tier: scanner`
- `agents/architecture-mapper.md` — `tier: explorer`
- `agents/convention-auditor.md` — `tier: explorer`
- `agents/delegate-pre-pass.md` — `tier: explorer`
- `agents/feature-tracer.md` — `tier: explorer`
- `agents/integration-explorer.md` — `tier: explorer`
- `agents/task-implementer.md` — `tier: implementer`
- `agents/pipeline-runner.md` — `tier: orchestrator`

## Acceptance Criteria

- [ ] Every agent in `agents/` has a `tier:` frontmatter field with one of the five classes.
- [ ] The `tier:` value for each agent matches the architecture.md shipped-default table.
- [ ] Each agent file has exactly one `<!-- model: is rendered ... do not hand-edit. -->` comment immediately after the closing frontmatter `---`.
- [ ] No existing `model:` value changes; no other frontmatter key or body content is reflowed.
- [ ] Frontmatter still parses (the comment is OUTSIDE the `---` fences, in the body).

## Technical Notes

- Place `tier:` adjacent to `model:` in the frontmatter for readability (order within YAML is not significant).
- The header comment goes on the first body line, after the closing `---`. It must NOT be inside the YAML frontmatter (Claude Code's parser would treat `#`/`<!--` oddly).
- This task only edits the 18 files; the render engine (TASK-002) consumes the `tier:` values.
