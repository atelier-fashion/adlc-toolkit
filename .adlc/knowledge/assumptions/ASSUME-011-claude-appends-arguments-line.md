---
id: ASSUME-011
title: "Claude Code appends an ARGUMENTS line when no placeholder receives the arguments"
status: unresolved
req: REQ-666
created: 2026-10-29
resolved:
---

## Assumption

When a skill's text carries no `$ARGUMENTS` placeholder, Claude Code appends
`ARGUMENTS: <value>` to the skill content, and `$0`–`$9` are substituted
independently of `$ARGUMENTS`.

## Context

REQ-666 removed every `$ARGUMENTS` from the toolkit's skills and describes the
argument in prose instead (BR-1), so on Claude Code a skill now receives its
argument only through that appended line. The `${1}`/`$(0)` dodges and the
`arg-templating` lint stay because of the second half.

## Resolution

Unresolved. The plan's §6.10 evidence is REQ-664's `arg-substitution` probe,
and `.adlc/research/harness-probes/claude.json` records it as `unknown`
(`binary-exit-1`): the `claude` CLI on the probing machine was not logged in
(LESSON-747). The assumption rests on the Claude Code skills documentation as
read on 2026-10-27. Resolve it by running `adlc harness probe claude --only
arg-substitution` with a logged-in `claude`.
