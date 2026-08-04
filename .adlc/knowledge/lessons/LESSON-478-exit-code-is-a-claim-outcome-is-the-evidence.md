---
id: LESSON-478
title: "A command that does a remote action plus local bookkeeping has two outcomes; its exit code reports only the AND"
component: "partials/forge"
domain: "adlc"
stack: ["sh", "gh", "az"]
concerns: ["reliability", "correctness"]
tags: ["exit-code", "outcome-verification", "error-classification", "wrapper", "cli", "idempotence"]
bug: BUG-150
created: 2026-08-04
updated: 2026-08-04
---

## What Happened

`adlc_forge_pr_merge` wrapped `gh pr merge` and returned its exit code. But that one
command performs two independent operations: a remote merge (API) and a local tidy-up
(switch off the merged branch, delete it). Its exit code is the **conjunction** — non-zero
if *either* fails — while the caller needs to know about them separately.

The local step fails whenever the repo's default branch is checked out in another worktree,
which is the normal state for any agent session working out of `.worktrees/` while the
primary checkout sits on `main`. So on `teton-code` the wrapper reported three consecutive
successful merges as failures. Each one had landed.

Two amplifiers made it worse than a cosmetic mislabel:

1. The unmatched stderr fell to the classifier's catch-all, which was named `network` — the
   one class that reads as transient and *invites a retry* against an already-merged PR.
2. `gh` aborts its cleanup sequence at the failed step, so the remote branch survived. A
   caller that believed the merge failed had no reason to clean it up either. Three merged
   branches had to be deleted by hand.

## Lesson

**When you wrap a command, ask how many outcomes it has. If more than one, the exit code
cannot express them, so verify the outcome you actually care about.**

The exit code is the command's *claim*; the system's observable state is the *evidence*.
For a merge, the evidence is one cheap call away — `gh pr view <ref> --json state` — and it
turns an ambiguous failure into a determinate answer. Report success, but never silently:
emit a warning naming precisely what did *not* happen, because the caller now owns the part
the tool abandoned.

Corollary, and the sharper half: **never name your catch-all error class after a specific
recoverable cause.** A default bucket means "we could not attribute this." Calling it
`network` silently asserts *transient, safe to retry* about every unknown failure — the
most dangerous possible default for a non-idempotent operation. Name the unknown bucket
something that reads as unknown, and give genuinely-attributable causes their own classes
(here: `local-git`).

## Why It Matters

The failure is invisible in the direction that matters. A wrapper that reports success as
failure produces no data loss on its own — but it corrupts every decision downstream:
retry logic reruns non-idempotent operations, cleanup is skipped, and an operator reading
the log concludes the opposite of what happened. It also erodes trust in the tooling far
out of proportion to the fix, because the tool is confidently wrong rather than merely
broken.

It went unnoticed because the *happy path in a single-worktree checkout works perfectly*.
The bug only appears in the layout agents actually use, which is not the layout the wrapper
was written and tested in.

## Applies When

Wrapping any CLI that combines a remote/authoritative action with local side effects (`gh
pr merge`, `git push` with hooks, `npm publish`, `terraform apply`, container push +
local tag cleanup); writing or extending an error classifier with a default branch;
deciding whether a non-zero exit justifies a retry of a non-idempotent operation; testing
a wrapper only in the topology the author happens to run.

## Related

- [[LESSON-447]] — a guard that does not hold on its degraded path. Same family: the
  behavior differs between the configuration you tested and the one that ships.
