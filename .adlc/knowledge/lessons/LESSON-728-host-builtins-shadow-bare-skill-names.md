---
id: LESSON-728
title: "A host's built-in command shadows a plugin skill of the same bare name — check skill names against the host's built-ins before trusting bare invocations"
component: "adlc/skills"
domain: "adlc"
stack: ["claude-code", "claude-skills", "markdown"]
concerns: ["portability", "developer-experience"]
tags: ["plugin", "namespace", "builtin-collision", "slash-commands", "init", "review"]
req: REQ-669
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "TASK-133 (REQ-669): the offline e2e case builtin_collision_static in tools/adlc/tests/e2e/plugin-sandbox.sh FAILed on 65 bare `/init` instruction lines, refuting ADR-5; after the dual spelling it PASSed. Shipped in 8ade64f."
confidence: high
enforcement: lint:builtin-collision
generalizes: []
supersedes: []
---

## What Happened

REQ-669's ADR-5 kept skill-to-skill references bare (`/init`, not `/adlc:init`)
on the plugin route, relying on the skills docs' rule that a bare name reaches a
skill unless another command already uses it. Claude Code 2.1.258 ships a
built-in `init` command, and its resolver prefers an exact command-name match.
So on the plugin install every "run `/init` first" line, whether a user typed it
or the model invoked it through the Skill tool, reached the built-in (which
writes a CLAUDE.md) instead of `/adlc:init`. `status` is also a built-in, and
`review` is an alias of the bundled `code-review` skill, with order-dependent
resolution. The offline sandbox caught it; no unit test could have, because the
collision lives in the host, not in the repo.

## Lesson

When skills ship under a namespace, a bare name is safe only if the host has no
built-in or bundled command with that name. List the host's built-in commands
for the version you target, intersect them with your skill names, and for every
match print both spellings wherever a line tells someone to run it
(`/init` (`/adlc:init` on the plugin install)). Keep the watched names in one
constant that a lint reads, and re-check it when the host version changes.

## Why It Matters

The failure is silent and destructive: the wrong command runs successfully and
does something else (here, overwriting project instructions), so nothing
reports an error.

## Applies When

Shipping skills or commands as a plugin or under any namespace, naming a new
skill, or upgrading the target Claude Code version.
