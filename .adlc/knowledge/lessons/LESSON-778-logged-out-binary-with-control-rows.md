---
id: LESSON-778
title: "Before writing 'owed a live run', list what a logged-out binary can settle, and give every row a control"
component: "adlc/harness"
domain: "adlc"
stack: ["claude-code", "sh"]
concerns: ["verification", "harness-agnostic", "cost"]
tags: ["live-verification", "logged-out", "control", "headless", "resume", "config-isolation", "throwaway-home"]
req: REQ-659
created: 2026-11-01
updated: 2026-11-01
kind: process
evidence: "REQ-659 tools/adlc/tests/e2e/claude-exec-manual.sh: logged out and at no cost, --resume returned the session id from a sibling worktree and an unrelated directory while a uuid that never ran gave No conversation found; --setting-sources user with --strict-mcp-config ran neither a planted hook nor an MCP server while --setting-sources project,local ran both; and the engine's whole 115-element argv was accepted before Not logged in."
confidence: low
enforcement: none
generalizes: [LESSON-759, LESSON-766]
supersedes: []
---

## What Happened

REQ-659's BR-14 and BR-25 looked like they needed a logged-in session. A throwaway `HOME` settled
both, because a logged-out `claude -p` still reads settings, starts servers, parses flags, writes
a transcript and finds a session. Only tool calls and model turns stayed owed.

## Lesson

Sort every live question by what it needs: argv parsing, config loading, session lookup and
process behaviour need the binary; a tool decision or a model turn needs a login. Run the first
group now, and pair each row with a control that would come out differently, because a row with
no control cannot tell "worked" from "did nothing". Keep the runs as a script, so the record can
be repeated. Then say plainly what those rows do not show.

## Why It Matters

"Blocked on a login" overstates the gap, and a design built on an unrun assumption is what a
ten-second check would have corrected.

## Applies When

An acceptance criterion or design decision depends on a harness you cannot log in to here, or
you are about to mark a behaviour unverified.
