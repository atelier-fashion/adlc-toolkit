---
id: LESSON-734
title: "To find your own Claude Code transcript, print a mark in one tool call and search for it in the next — a subagent has no id of its own and a running command is not yet in its transcript"
component: "adlc/wrapup"
domain: "adlc"
stack: ["sh", "claude-code"]
concerns: ["correctness", "knowledge-capture", "false-positive"]
tags: ["transcript-discovery", "session-jsonl", "subagents", "pipeline-runner", "self-identification", "claude-code-session-id"]
req: BUG-253
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "BUG-253: the REQ-423 walk, run from <repo>/.worktrees/REQ-647 against the subagent layout, chose old-2026-10-27.jsonl; adlc_transcript_find over the same layout returns subagents/agent-runner.jsonl (partials/tests/session-transcript.test.sh runner_finds_own_subagent_transcript). Probes 2026-10-29 on Claude Code 2.1.309: a grep for a literal in the running command found 0 hits in ~/.claude/projects, a mark printed by the previous call found exactly 1; a subagent's shell exported the parent's CLAUDE_CODE_SESSION_ID and no agent id."
confidence: high
enforcement: "test:partials/tests/session-transcript.test.sh"
generalizes: [LESSON-733]
supersedes: []
---

## What Happened

BUG-253 needed `/wrapup` to find the transcript of the run that is executing it,
including when that run is a `/sprint` pipeline-runner subagent. Directory and id
signals all failed. A subagent's transcript is
`~/.claude/projects/<orchestrator's encoded cwd>/<session>/subagents/agent-<id>.jsonl`,
away from its own cwd. Its shell sees only the parent's `CLAUDE_CODE_SESSION_ID`, so
concurrent runners share one. The REQ id also appears in the orchestrator's transcript,
in sibling runners' transcripts, and in older sessions. A literal inside the command
being run is not in the transcript yet. The output of an earlier tool call is.

## Lesson

To identify "my own transcript", don't infer it from location, session id or a work
id. Make the run write something unique into it and look for that. Print a random mark
in one tool call. In a **separate, later** call, search `~/.claude/projects/` (deep
enough for `subagents/`, recent files only) for the one file that holds it. Never
combine the two calls, because a command's own text is not flushed before it runs.
Treat zero matches or several (a forked copy) as a refusal, not a cue to guess.
`partials/session-transcript.sh` implements this; reuse it.

## Why It Matters

Each indirect signal picks a confidently wrong transcript in some layout: a sprint
runner, a parent-directory session, a fork. A wrong transcript produces a well-formed
lesson about other work, which poisons retrieval.

## Applies When

- Any skill step that reads or delegates the current session's transcript: `/wrapup`
  Step 4, lesson capture in other skills, the REQ-660 session-sidecar chain.
- Code that wants a "current agent id" from inside a Claude Code subagent's shell.
- Designing a hook or sidecar that must also cover subagents. Session-start hooks do
  not fire for them.
