---
id: TASK-001
title: "Author the dedicated adversary agent (agents/adversary.md)"
status: complete
parent: REQ-517
created: 2026-06-11
updated: 2026-06-11
dependencies: []
repo: adlc-toolkit
---

## Description

Ship the dedicated `adversary` agent definition (BR-8, the 18th agent). It encodes
the attack-lens + mandatory-self-refutation protocol so other skills/workflows can
dispatch it as a lens via the Agent tool. Read-only tools, reviewer-class model
tier, Finding-schema output.

## Files to Create/Modify

- `agents/adversary.md` — new agent definition

## Acceptance Criteria

- [ ] Frontmatter: `name: adversary`, `description` (when to dispatch), `model: opus`
      (reviewer-class tier; concrete fallback per BR-8 since REQ-516 tier map not landed),
      `tools: Read, Grep, Glob, Bash` (read-only — no Edit/Write).
- [ ] Body declares the read-only constraint explicitly (no Edit/Write; never mutate
      the target — BR-5).
- [ ] Body carries the artifact-type → attack-lens map mirroring BR-2 (spec / plan-or-
      architecture / diff-or-PR / prose).
- [ ] Body mandates self-refutation before any finding is reported; findings killed by
      their own refutation are dropped (BR-3).
- [ ] Output format documents the Finding schema: severity (critical/major/minor),
      confidence (high/medium/low), break_scenario (required), refutation_attempt (required).
- [ ] Verdict-phrasing rule: distinguish "could not find a problem" from the prohibited
      "there is no problem" (BR-4).
- [ ] Structurally consistent with the other 17 agents (same frontmatter shape as
      `correctness-reviewer.md` / `reflector.md`).

## Technical Notes

- Model on `agents/correctness-reviewer.md` (frontmatter + Constraints + Checklist +
  Output Format sections) and `agents/reflector.md`.
- This is the primary lens carrier; the `/adversary` skill (TASK-002) dispatches it
  when the Agent tool is available and degrades to single-context otherwise (BR-6).
- Dispatching it directly via the Agent tool on a sample spec must return findings in
  the Finding schema (final AC of the REQ) — keep the Output Format section explicit
  and self-contained.
