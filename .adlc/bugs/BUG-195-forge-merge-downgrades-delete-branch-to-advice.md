---
id: BUG-195
title: "adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion when gh's local cleanup aborts — the remote branch survives and no caller acts on the warning"
status: open
severity: medium
created: 2026-08-27
updated: 2026-08-27
component: "adlc/partials/forge"
domain: "adlc"
stack: ["bash", "sh", "gh", "markdown"]
concerns: ["reliability", "silent-failure", "developer-experience", "structural-enforcement"]
tags: ["forge-adapter", "pr-merge", "delete-branch", "worktree", "post-merge-cleanup", "partial-success"]
---

## Description

`adlc_forge_pr_merge <ref> --squash --delete-branch` reports `state=MERGED`, returns
0, and emits:

```
warn=merge completed remotely, but gh post-merge cleanup failed; the source branch
     is likely NOT deleted — remove it with: git push origin --delete <branch>
warn_class=local-git
raw=failed to run git: fatal: 'main' is already used by worktree at '<primary checkout>'
```

The merge is real. The requested branch deletion is not: `gh pr merge` aborts its
cleanup sequence at the failed local step, so the remote branch survives. The
adapter converts the caller's `--delete-branch` **request** into a prose
**instruction on stderr addressed to a human**.

BUG-150 fixed the *reporting* of this condition — the rc, the `state=MERGED`, the
`local-git` classification, the demotion of `error_class` to `warn_class`. It
deliberately left the outcome alone and told the caller to finish the job:
"the `warn=` line must say so explicitly — the caller needs to know to run
`git push origin --delete <branch>` itself."

No caller does. That is the residual defect.

## Reproduction Steps

1. From a git worktree (any `.claude/worktrees/<name>` session), with the primary
   checkout sitting on `main` — the normal state for every agent session.
2. Open a PR from a branch in that worktree and merge it through the adapter:
   `adlc_forge_pr_merge <pr> --squash --delete-branch`
3. Observe `state=MERGED` + the `warn=` block, rc 0.
4. `git ls-remote --heads origin <branch>` — the branch is still there.

Observed twice in one session on 2026-08-27 (PR #119 and PR #120, both BUG-194),
each requiring a manual `git push origin --delete`.

## Expected Behavior

`--delete-branch` is an instruction to the adapter, not a hint. When the merge
lands and deletion was requested, the source branch should end up deleted on the
remote — or, if it genuinely cannot be, the caller should be told in a form a
caller can act on. The adapter has everything it needs at that moment: it knows
the merge succeeded, it knows deletion was requested, and the branch name is one
`gh pr view` away.

## Actual Behavior

The remote branch survives. Every caller treats rc 0 as done and moves on to its
own cleanup step, which deletes only the *local* branch.

## Environment

- Platform: adlc-toolkit @ 170bddd, `partials/forge.sh` GitHub backend
- Version: behavior introduced by BUG-150's fix (the pre-BUG-150 code reported
  the whole merge as failed, so the branch survived then too — for a different reason)
- Trigger: the default agent-session topology (worktree + primary checkout on `main`)

## Root Cause

**Three layers, only the first of which BUG-150 addressed.**

**1. `gh pr merge` is two operations behind one flag.** It performs the remote
merge, then a local tidy-up (switch off the merged branch, delete local, delete
remote). Its cleanup is sequential and aborts at the first failure. When the local
step fails — because git refuses to check out `main` while another worktree owns
it — the remote deletion that would have followed never runs. BUG-150 documented
this precisely and fixed the *misreporting* it caused.

**2. The adapter's remediation is addressed to the wrong audience.** The `warn=`
line is imperative English naming a shell command with a `<branch>` placeholder the
adapter never substitutes. Every consumer of this partial is a skill following a
documented step sequence, and the normalized-output contract (`partials/forge.md`)
gives callers `state`, `url`, and `error_class` to branch on — there is no
`branch_deleted` field and no convention for reacting to `warn=`. A grep across
every call site (`bugfix/SKILL.md:140`, `wrapup/SKILL.md:62`,
`proceed/phases-6-8-ship.md:136`, `sprint/SKILL.md:218`,
`workflows/adlc-sprint.workflow.js:1541,2158`) finds **no** handling of `warn=`
whatsoever. The remediation is unreachable by design: it is human-readable output
in a machine-consumed channel.

**3. The one caller that does mitigate it does so by prose, and it did not
propagate.** `agents/pipeline-runner.md:105` carries the workaround —
"`adlc_forge_pr_merge --delete-branch` invoked from the worktree fails because git
refuses to delete a branch that's currently checked out … Always `cd` to
`repos[<id>].path` before invoking." That knowledge lives in exactly one agent
file. `/bugfix` Phase 6 Step 1 and `/wrapup` Step 9 both call the same op from
wherever the session happens to be, with no such note. This is the LESSON-012
pattern: a correctness requirement encoded as prose in one place, silently absent
from the other two.

Note that the `cd`-to-primary workaround is also **incomplete** for `/bugfix`: it
resolves the "`main` is used by another worktree" collision, but if the *fix
branch* is still checked out in the worktree, gh's local delete hits the same class
of refusal on a different ref. Mitigating at the call site fixes one topology at a
time; fixing at the adapter fixes all of them.

## Scope of impact (measured, not assumed)

A survey of the toolkit and all four consumer repos for remote branches fully
merged into their default branch found **no orphan attributable to this bug**.
The eight `promote/*` branches in atelier-fashion are deliberate REQ-380 promotion
snapshots, not leaks. So the honest claim is: this costs a manual step on every
worktree merge and leaves a latent leak whenever nobody reads the warning — **not**
that it has already accumulated damage. That is why this is `medium`, not `high`.

## Resolution

**Complete the request instead of describing it.** On the merged-but-cleanup-failed
path, when `--delete-branch` was requested, the adapter now resolves the head
branch and deletes the remote ref itself.

`git push origin --delete <branch>` is the right instrument: it updates a remote
ref and touches no local ref, so it is structurally immune to the worktree
collision that broke gh's cleanup in the first place. Only the *remote* ref is the
adapter's to clean up — the local branch stays the caller's own cleanup step,
since it may legitimately still be checked out.

**New normalized field `branch_deleted`**, emitted on both success paths whenever
deletion was requested:

| Value | Meaning |
|---|---|
| `1` | remote branch is gone — gh deleted it, the adapter completed it, or it was already absent |
| `0` | it survives; the `warn=` line names the exact command, with the real branch substituted |
| `skipped-fork` | the head lives on a fork and is never auto-deleted |

This is the part that actually closes the bug. The old remediation was an English
sentence in a channel every caller parses for `key=value`, containing a literal
`<branch>` placeholder the adapter never filled in. A field is something a caller
can branch on; a sentence is not.

Deliberate design choices:

- **Idempotent.** A remote ref that is already gone is the state we wanted, so
  `remote ref does not exist` maps to `branch_deleted=1`, not a failure. gh's
  cleanup ordering may differ by version; the fix must not care which step it
  reached.
- **Never touches a fork's branch.** `isCrossRepository` is checked before any
  deletion — auto-deleting a contributor's head branch would be destructive and
  unrecoverable by us.
- **Never converts a merge into a failure.** Every path here still returns 0 with
  `state=MERGED`; a delete failure downgrades to `branch_deleted=0` plus
  `delete_raw=` diagnostics. The merge landing and the branch being tidied are
  independent facts and are now reported independently.
- **Failure still names the real branch.** When the adapter genuinely cannot
  delete, the `warn=` line carries the substituted branch name, and a test asserts
  no unsubstituted `<branch>` placeholder can survive.

**Caller-side loop closed.** `/bugfix` Phase 6 Step 1 and `/wrapup` Step 9 now say
to check `branch_deleted` and act on `0` — the two call sites that lacked the
mitigation `agents/pipeline-runner.md` had carried alone.

## Verification

- `bash partials/tests/forge.test.sh` and `zsh partials/tests/forge.test.sh` — ALL
  CASES PASS under both shells (BR-9 cross-shell requirement), plus the
  `sh partials/tests/run.sh` wrapper.
- 20 new cases covering: the deletion actually firing (asserted against a recording
  `git` shim, not just the output text), `branch_deleted=1`, the absence of any
  manual-remediation instruction on the handled path, idempotence on an
  already-gone ref, `branch_deleted=0` with substituted branch name and
  `delete_raw=` diagnostics, no unsubstituted placeholder, fork heads skipped with
  no delete attempted, and no `branch_deleted` field or deletion when
  `--delete-branch` was not requested.
- `python3 -m pytest tools/` — 484 passed.
- `python3 tools/lint-skills/check.py --root .` — exit 0.

The pre-existing BUG-150 cases still pass unchanged — the reporting contract it
established is preserved, this only adds the outcome.

## Files Changed

- `partials/forge.sh` — GitHub `pr_merge` arm: complete the requested remote-branch deletion on the merged-but-cleanup-failed path; emit `branch_deleted` on both success paths; fork guard; idempotent already-gone handling
- `partials/forge.md` — documented the `pr_merge` partial-success contract and the `branch_deleted` field, with the "branch on the field, not the prose" rule
- `partials/tests/forge.test.sh` — 20 new cases (section 7c)
- `bugfix/SKILL.md` — Phase 6 Step 1: new sub-step 3 to check `branch_deleted`
- `wrapup/SKILL.md` — Step 9: check `branch_deleted`
