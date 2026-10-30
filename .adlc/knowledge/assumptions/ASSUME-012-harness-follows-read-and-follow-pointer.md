---
id: ASSUME-012
title: "An agent that reaches a read-and-follow pointer reads the named companion with its file tool and runs it before continuing"
status: unresolved
req: REQ-661
created: 2026-10-29
resolved:
---

## Assumption

When a `SKILL.md` step says "Read `<companion>` and follow it before you continue",
the model on Claude Code, Copilot CLI, Codex, Gemini CLI and Cursor reads that file
with its own file tool at that point and executes its fences and instructions, so a
step that lives only in a `references/` companion (or one of `/proceed`'s
read-and-follow phase files) is run exactly as it was when it lived in `SKILL.md`.
A second, smaller assumption sits beside it: the Agent Skills reference validator
(`skills-ref validate`) checks frontmatter, not body length, so `skill-line-budget`
is not a duplicate of it.

## Context

REQ-661 moved `/proceed` Step 0, Pipeline State Tracking and Run-outcome telemetry,
two `/spec` sub-steps and two `/template-drift` steps into companions (BR-4, ADR-5).
The Agent Skills specification describes `references/` files the agent reads on
demand; nothing in the toolkit forces the read. REQ-661's evidence is structural:
every fence is byte-identical and reached in the same order (AC-3, the reading-order
dogfood), and a contract test pins each pointer.

## Resolution

Unresolved. No run of a split skill on a harness other than Claude Code was made
(Out of Scope, P2), and no full `/spec`, `/template-drift` or `/proceed` run on the
split text was recorded (REQ-661 BR-16 was met at fence level). `skills-ref` was not
installed where REQ-661 ran, so the validator claim rests on its published
description. Resolve with one full run of each split skill on Claude Code and on one
other harness, checking that the companion's telemetry line and stderr lines appear,
and with one `skills-ref validate` run against a 500-line `SKILL.md`.
