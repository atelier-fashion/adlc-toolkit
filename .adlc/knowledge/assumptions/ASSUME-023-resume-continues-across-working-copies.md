---
id: ASSUME-023
title: "`claude -p --resume` continues a conversation from another working copy"
status: validated
req: REQ-659
created: 2026-11-01
resolved: 2026-11-02
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

Holds. Row `resume-sibling`: a session started in one worktree was resumed from a sibling worktree and recalled a word given in the first session.
