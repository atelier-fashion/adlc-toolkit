---
id: ASSUME-015
title: "Every harness writes a tool's output to its transcript before the next tool call runs"
status: unresolved
req: REQ-660
created: 2026-10-30
resolved:
---

## Assumption

`/wrapup` finds a run's transcript by a mark printed in one tool call and searched for in
the next, on every harness.

## Context

BUG-253 measured this on Claude Code, and REQ-660 repeated it on this session's own
transcript. Codex, Copilot, Gemini and Cursor are not installed on the machine that built
REQ-660, so their flush timing is unmeasured. A harness that flushes later has no holder,
and `/wrapup` refuses into Fallback drafting. That is safe, so the failure mode is a lost
delegation and never a wrong transcript.

## Resolution

Open. Resolve per harness with one real session when its fixture is captured.
