---
id: LESSON-739
title: "A safety property of one tool does not survive a wrapper that hands the operation to another — when your caller's local state must outlive a remote operation, take the local side effect away from the tool that does the remote one"
component: "adlc/partials/forge"
domain: "adlc"
stack: ["bash", "sh", "gh", "git"]
concerns: ["reliability", "data-loss", "state-integrity", "api-contract"]
tags: ["forge-adapter", "pr-merge", "delete-branch", "worktree", "pipeline-state", "phase-8", "upstream-behaviour-change", "gh"]
req: BUG-252
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "BUG-252; partials/tests/forge.test.sh §7c (9 failures against the pre-fix adapter, all pass after); gh 2.103.3 binary string 'Removed worktree %s'"
confidence: high
enforcement: test:partials/tests/forge.test.sh
generalizes: [LESSON-572]
supersedes: []
---

## What Happened

The `/proceed` Phase 8 contract merged from the primary checkout with
`--delete-branch`. Its stated reason: "git refuses to delete a branch checked out by a
worktree", so the REQ's worktree was safe. `adlc_forge_pr_merge` forwarded the flag to
`gh pr merge`, and gh 2.103.3's `-d` removes the linked worktree holding the branch so
its local delete can succeed. The REQ-647 runner lost `.worktrees/REQ-647` and its
gitignored `pipeline-state.json` one step before Step 8b would have copied the
terminal record to the primary path. BUG-195 had already used `git push origin
--delete` (LESSON-572), but only as a fallback when gh's cleanup *failed*. Here the
same cleanup *succeeded* against a worktree the caller still needed.

## Lesson

1. **Name the actor that actually performs an operation before relying on its safety
   property.** "git refuses" was true of `git branch -d`. The deletion ran inside gh,
   which is free to work around git, and from 2.103.3 it does. A wrapper that forwards
   a convenience flag inherits the forwarded tool's current semantics, not the
   semantics of the tool the contract author had in mind.
2. **When a remote operation must not disturb local state, keep every local side
   effect out of it.** Don't tune when gh's cleanup runs. Strip the flag, do the
   remote half with an instrument that cannot touch local refs
   (`git push origin --delete`), and leave the local teardown to the caller, which
   knows the order: record, then worktree, then branch.
3. **A deletion that acts on another object's state has to check that state first.**
   A zero exit from a merge command is not proof of a merge (auto-merge, a merge
   queue), and deleting an open PR's head closes the PR. Read `state` in the same call
   that resolves the branch name.
4. **Test the outcome against real local state, not against a recorded argv.** The
   regression builds a real bare origin, a primary checkout and a linked worktree with
   an untracked file, and asserts the file survives. A shim that only records argv
   would have passed the old code.

## Why It Matters

Pipeline state that lives in an untracked file in a worktree is lost silently and
cannot be recovered from git. The merge reported success, so nothing failed loudly.
The damage showed up later as a terminal record that had to be rebuilt by hand, with
the Phase 0 timing gone.

## Applies When

A wrapper forwards flags to a third-party CLI (gh, az, glab, cloud CLIs) whose
"convenience" options touch the local checkout, branches or worktrees. Or a contract
justifies an ordering with a safety property ("X refuses to…") that belongs to a
different tool from the one doing the work. Or a remote operation runs while
gitignored or untracked state the caller still needs sits in a worktree.
