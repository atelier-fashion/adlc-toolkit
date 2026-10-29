---
id: BUG-252
title: "adlc_forge_pr_merge --delete-branch hands deletion to gh, which (2.103.3) removes the REQ's worktree and its untracked pipeline-state.json mid-Phase-8"
status: resolved
severity: high
created: 2026-10-29
updated: 2026-10-29
component: "adlc/partials/forge"
domain: "adlc"
stack: ["bash", "sh", "gh", "git", "markdown"]
concerns: ["reliability", "data-loss", "state-integrity"]
tags: ["forge-adapter", "pr-merge", "delete-branch", "worktree", "pipeline-state", "phase-8", "sprint", "pipeline-runner"]
introduced_by: []
attribution: none
---

## Description

During the REQ-647 `/sprint` run, the pipeline-runner's Phase 8 merge —
`adlc_forge_pr_merge <prUrl> --squash --delete-branch`, run from the parent repo
path as the contract says — deleted the REQ's worktree at `.worktrees/REQ-647`.
The worktree's `pipeline-state.json` is gitignored, so it went with it. The commits
were safe on the remote, but the state file (Phase 0 timing, `phaseHistory`, task
progress) was gone before Step 8b could write the terminal record, and the runner
had to rebuild the record by hand.

The runner contract says the opposite is safe: `agents/pipeline-runner.md`,
`proceed/phases-6-8-ship.md` and the workflow engine's merge prompts all justify
merging from the parent path with "git refuses to delete a branch checked out by
a worktree". That was true of `git branch -d`. It is not true of `gh pr merge
--delete-branch`.

## Reproduction Steps

1. gh 2.103.3. A primary checkout on `main`, a linked worktree
   `.worktrees/REQ-xxx` on `feat/REQ-xxx-…` with an untracked
   `.adlc/specs/REQ-xxx-*/pipeline-state.json`, and an open PR from that branch.
2. From the primary checkout: `adlc_forge_pr_merge <pr> --squash --delete-branch`.
3. The PR merges, then gh's local cleanup prints `Removed worktree
   <path>/.worktrees/REQ-xxx` and deletes the local branch.
4. `ls .worktrees/REQ-xxx` — gone, with the state file.

## Expected Behavior

Merging a PR never touches the local worktree that holds its branch. The worktree
survives until Step 8b tears it down by absolute path, after the terminal record
has been written to the primary path.

## Actual Behavior

`--delete-branch` is forwarded to gh verbatim. gh's `-d` means "delete the local
**and** remote branch", and since some recent release it removes a linked worktree
that has the branch checked out so that the local delete can succeed. The
adapter's caller loses the worktree and every untracked file in it.

## Environment

- Platform: macOS (Darwin 27.0.0)
- Version: gh 2.103.3 (2026-10-26); adlc-toolkit at 6600dd6

## Root Cause

Prior lessons consulted:
- LESSON-572 — A remediation is only real if its audience can execute it … finish the half you are able to finish (score 14)
- LESSON-626 — A rule written about one actor does not settle the case for another … (score 10)
- LESSON-575 — Squash is not a neutral merge style … (score 9)
- LESSON-465 — A partially-synced repo looks healthy — vendored-surface drift must be verified per-file … (score 8)
- LESSON-716 — A validator for a format another reader consumes must parse the way that reader does … (score 7)

`partials/forge.sh:455`, `adlc_forge_pr_merge`'s GitHub arm, forwards its argv to
`gh pr merge` verbatim, `--delete-branch` included. gh's `-d` is documented as
"Delete the local and remote branch after merge". The gh 2.103.3 binary carries
the strings `Removed worktree %s` and `Could not remove worktree %s; skipping local
branch delete`. Its local cleanup now removes the linked worktree that has the head
branch checked out, then deletes the local branch. `git branch -d` does refuse to
delete a checked-out branch, and the runner contract relied on that, but gh no
longer leaves the decision to git.

`/proceed` Phase 8 runs the merge from the primary checkout while
`.worktrees/REQ-xxx` still holds the branch, and Step 8b, which writes the
terminal record to the primary path and *then* tears the worktree down, runs
after the merge. So the merge destroyed the worktree, and the gitignored
`pipeline-state.json` in it, one step before the record that would have
preserved its contents.

LESSON-572 point 3 already names the instrument. `git push origin --delete`
touches no local ref, so it is structurally immune to gh's local cleanup. BUG-195
used it only as the fallback after gh's cleanup *failed*. This bug is the same
cleanup *succeeding* against a worktree the caller still needed. The remedy is to
take the local step away from gh entirely, not to tune when it runs.

Secondary: gh's `-d` short spelling has to be stripped too. A zero exit with
`--auto` or a merge queue does not mean the PR merged, and deleting the head of an
open PR closes it, so the adapter has to check the PR's state before it deletes
anything.

Attribution: none. The root-cause line was last changed in 3519e18 (BUG-150),
which carries no `REQ-` trailer. The trigger is an upstream gh behaviour change.

## Resolution

- `adlc_forge_pr_merge` (GitHub arm) strips `--delete-branch`/`-d` from the gh
  argv, so gh never runs a local cleanup. When deletion was requested it reads
  `state,headRefName,isCrossRepository` in one `gh pr view` call. For a `MERGED`
  PR that is not from a fork, it deletes the remote ref with
  `git push origin --delete`. This runs on the clean path and on the BUG-150
  partial-success path. A PR that is not `MERGED` after a zero exit reports its
  real `state=` and `branch_deleted=0` and keeps its branch. The local branch and
  the worktree are left for the caller's ordered teardown.
- The runner contract no longer claims git protects the worktree:
  `agents/pipeline-runner.md`, `proceed/phases-6-8-ship.md` (Step 8b now also
  deletes the local branch after removing the worktree), and the workflow engine's
  merge prompts and comment. `partials/forge.md` documents the new contract.
- Regression test: `partials/tests/forge.test.sh` §7c builds a real bare origin,
  a primary checkout on `main` and a linked REQ worktree with an untracked
  `pipeline-state.json`. A gh shim behaves like 2.103.3's `-d`. Before the fix:
  9 failures (worktree and state file removed, gh received the flag, local branch
  deleted, an open PR's head deleted). After it: all pass under bash, zsh and sh.

## Files Changed

- `partials/forge.sh` — GitHub `pr_merge` arm: strip the delete flag, delete only the remote ref, and only once the PR is `MERGED`
- `partials/tests/forge.test.sh` — §7c BUG-252 regression; byte-compat now asserts gh gets no `--delete-branch`
- `partials/forge.md` — document that `--delete-branch` is never forwarded to gh
- `agents/pipeline-runner.md` — replace the "git refuses" rationale; vendored-partials caveat
- `proceed/phases-6-8-ship.md` — same at Step 8a; Step 8b deletes the local branch after the worktree
- `workflows/adlc-sprint.workflow.js` — same rationale fix in the merge prompts

## Deployment

n/a — the toolkit has no deploy target. The fix is live for the symlink install on merge. Consumer projects get it when they re-sync `.adlc/partials/forge.sh` (`/template-drift`, then `/init`).
