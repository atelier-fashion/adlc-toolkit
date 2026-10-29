---
id: LESSON-733
title: "/wrapup's transcript discovery cannot see a sprint runner's own transcript — it climbs from the worktree to the repo root and can match an older session that merely names the REQ"
component: "adlc/wrapup"
domain: "adlc"
stack: ["bash", "claude-code"]
concerns: ["retrieval", "knowledge-capture", "false-positive", "delegation"]
tags: ["transcript-discovery", "session-jsonl", "subagents", "pipeline-runner", "req-423", "wrapup-step-4"]
req: REQ-647
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "REQ-647 Phase 8, /wrapup Step 4 discovery (wrapup/SKILL.md:193): the walk from .worktrees/REQ-647 up to the repo root matched an older repo-root session from 2026-10-27 that names REQ-647 but none of TASK-140 to TASK-145. This run's transcript was a subagents/agent-<id>.jsonl file under the orchestrator session's project directory, which the walk never visits."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

REQ-647's `pipeline-runner` reached `/wrapup` Step 4 with delegation enabled.
Content-anchored discovery (REQ-423) started at the runner's worktree,
`<repo>/.worktrees/REQ-647`, and climbed toward `$HOME`, taking each ancestor's
`~/.claude/projects/<encoded>` directory. The repo root's directory held an
older session from 2026-10-27 that mentions REQ-647, so the anchor matched it.
The runner's own transcript was elsewhere: under the orchestrator session's
project directory, in `<session>/subagents/agent-<id>.jsonl`. A worktree path
is never an ancestor of the orchestrator's directory, so the walk can never
reach it.

## Lesson

**For a subagent, "the session that ran this work" is not under any ancestor of
its working tree.** An id anchor does not prove a transcript belongs to the run:
a spec-writing session, a planning sprint, or a bug that cites the REQ all name
the id too. Before delegating a discovered transcript, check that its tail
contains this run's own artifacts (its task ids, a file it created). If it does
not, look under the orchestrator's `<session>/subagents/` for the runner's
transcript. Failing that, draft from the conversation instead. The discovery
step itself should learn the subagents layout, or take the transcript path from
the orchestrator, which knows it.

## Why It Matters

`/wrapup` treats a gate pass plus a found transcript as mandatory delegation, so
a false match yields a confident, well-formed lesson about the wrong work, filed
under this REQ. That is the outcome REQ-423 named as worse than no delegation.
It poisons retrieval for every later REQ that touches the same surfaces.

## Applies When

- `/wrapup` Step 4 or `/bugfix` lesson capture running inside a `/sprint`
  `pipeline-runner` or any other subagent, with delegation enabled.
- A REQ whose id appears in earlier sessions in the repo root: the session that
  wrote the spec, a sprint that deferred it, a bug that cites it.
- Any change to the discovery walk in `wrapup/SKILL.md` Step 4.
