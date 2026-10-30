---
id: ASSUME-013
title: "Claude Code reads a plain `startup|resume|clear` SessionStart matcher as three alternatives"
status: unresolved
req: REQ-657
created: 2026-10-30
resolved:
---

## Assumption

The `claude` hooks render gives `session-start` the matcher `startup|resume|clear`
and compaction its own `compact` group, assuming Claude Code matches a plain
pipe-separated matcher against each source, so `ethos-inject` fires once per
session start and once after compaction.

## Context

A `SessionStart` group with no matcher matches every source, compaction included,
so a no-matcher group plus a `compact` group would inject ETHOS twice after
compaction. `harness/claude.yml` `hook_events` and the golden
`harness/claude/rendered/settings.json` depend on the alternation. If it does not
hold, the session-start group never fires (the skills' `!` ETHOS line still does).

## Resolution

Supported offline: the Claude Code 2.1.258 bundle splits a matcher of the form
`^[a-zA-Z0-9_|]+$` on `|` into alternatives. Not yet observed in a live, trusted
session (the standalone CLI was not logged in, LESSON-747). Resolve with one live
session start in a project carrying the render, then set `status: validated`.
