---
id: ASSUME-023
title: "`claude -p --resume` continues a conversation from another working copy"
status: unresolved
req: REQ-659
created: 2026-11-01
resolved:
---

## Assumption

The exec engine resumes the implementing session in `.worktrees/REQ-xxx-close-out`, assuming the
resumed model holds the earlier conversation and can draft lessons from it.

## Context

A logged-out `--resume <id>` returned the same session id from a sibling worktree and from an
unrelated directory, and a uuid that never ran gave `No conversation found`, so the session file
is found. Nothing has continued from it: a logged-out run stops before the first turn. If it
does not continue, the close-out still has the run evidence in its prompt, and the lesson drafts
are thinner.

## Resolution

Open. Owed to a logged-in run, in REQ-659's `## Deferred`.
