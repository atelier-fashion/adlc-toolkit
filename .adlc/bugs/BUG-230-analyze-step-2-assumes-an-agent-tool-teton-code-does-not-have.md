---
id: BUG-230
title: "/analyze Step 2 assumes an agent-dispatch tool Teton Code does not have, and Step 2a's hygiene shell would pin"
status: open
severity: medium
created: 2026-09-26
updated: 2026-09-26
component: "adlc/analyze"
domain: "skills"
stack: ["markdown", "sh"]
concerns: ["portability", "developer-experience"]
tags: ["teton-code", "analyze", "subagents", "harness-agnostic", "shell-provenance", "session-pinned", "bug-228"]
introduced_by: []
attribution: none
---

## Description

Found while verifying BUG-228. `/analyze` Step 2 says "In a single message,
launch the 4 audit agents" (`code-quality-auditor`, `convention-auditor`,
`security-auditor`, `test-auditor`, defined under `~/.claude/agents/`). Teton
Code's tool set is `docs`, `edit`, `glob`, `grep`, `mcp`, `projects`, `read`,
`shell`, `skill` and `web`
(`crates/tetond/src/harness/tools/`). It has no agent-dispatch tool and no
`~/.claude/agents` registry, so Step 2 cannot run as written, and the skill
gives no alternative. `/proceed` already has one for its own agent phases:
"Subagent mode … run the … checklists sequentially in your own context using
the criteria from the agent definitions".

Step 2a (repo hygiene) is written as bash with `$(…)`, quoted `--format='…'`
strings, `awk` programs and pipes. On Teton each of those classifies
`unknown_shell` and pins the session to the local tier (the BUG-220/BUG-228
class), so the hygiene pass would kill the turn the same way Step 1.5 did.

## Reproduction Steps

1. In a Teton Code session rooted at a project with `.adlc/`, run `/analyze`.
2. After Step 1 (and the BUG-228 skip of 1.5/1.6), the model reaches Step 2.

## Expected Behavior

On a harness without agent dispatch, the skill tells the model to run the four
audit checklists one at a time in its own context, reading the checklists from
the agent definitions. On a provenance-classifying harness, Step 2a's checks
either use pin-free spellings or are skipped and named as skipped.

## Actual Behavior

In session `sess-cy6w6jagfw5b0tynjda7x150t8` (2026-09-26) the turn ended right
after Step 1's reads, without starting Step 2. That particular stop was
Teton-side (teton-code BUG-229: the call spent its 1,024-token cap reasoning).
But even with that fixed, Step 2 has no path the model can follow on Teton, and
Step 2a's shell would pin.

## Environment

- Teton Code v0.1.36; adlc-toolkit `main` at `5fdb5b1`

## Root Cause

(to confirm during investigation) The skill assumes Claude Code's harness: an
`Agent` tool plus `~/.claude/agents/`, and a shell that runs unclassified.

## Resolution

(filled after fix)

## Files Changed

(filled after fix)
