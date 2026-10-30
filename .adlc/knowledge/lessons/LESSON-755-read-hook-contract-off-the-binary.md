---
id: LESSON-755
title: "Decide a hook capability from the installed binary's hook schema, not the event list: SessionStart with no matcher also fires on compact, and SubagentStart takes context only as JSON"
component: "adlc/harness"
domain: "adlc"
stack: ["claude-code", "json", "sh"]
concerns: ["portability", "harness-agnostic", "correctness"]
tags: ["hooks", "sessionstart", "subagentstart", "matcher", "compact", "additional-context", "multi-harness", "capability"]
req: REQ-657
created: 2026-10-30
updated: 2026-10-30
kind: domain
evidence: "REQ-657 Open Question 1 and harness/claude.yml hook_events: the Claude Code 2.1.258 bundle lists SubagentStart in its hook-event enum but reads its context only from hookSpecificOutput.additionalContext, treats an absent or '*' matcher as match-all (so a plain SessionStart group also fires on compact), and splits a plain 'a|b|c' matcher on '|'. Read offline; no live session was available (LESSON-747)."
confidence: low
enforcement: none
generalizes: [LESSON-747]
supersedes: []
---

## What Happened

REQ-657 had to decide whether Claude Code exposes `SubagentStart` and how to render
"re-fire after compaction". The event names were all present, which would have
suggested declaring `subagent_start_hook: yes` and a plain `SessionStart` group
plus a `compact` group. The bundle's own schema showed that `SubagentStart` reads
context only from JSON `additionalContext` (a plain-stdout command would inject
nothing), and that a `SessionStart` group without a matcher matches every source,
compaction included, so adding a `compact` group would double-fire.

## Lesson

Before declaring a harness capability, read how the installed binary delivers it,
not only whether the event exists: the payload and output contract per event, and
how matchers are evaluated. On Claude Code, give `SessionStart` an explicit
`startup|resume|clear` matcher when compaction has its own group, and treat
`SubagentStart` as unsupported for a plain-stdout command until a JSON-emitting
variant is verified live.

## Applies When

Writing or reviewing a harness adapter's `hook_events` or capability block, or any
hook whose output is meant to become model context.
