---
id: LESSON-572
title: "A remediation is only real if its audience can execute it. Handing a human-readable instruction into a machine-consumed channel is not a fix — it is a fix-shaped comment. When an operation half-succeeds, give each fact its own normalized field and finish the half you are able to finish."
component: "adlc/partials/forge"
domain: "adlc"
stack: ["bash", "sh", "gh", "markdown"]
concerns: ["reliability", "silent-failure", "structural-enforcement", "developer-experience", "api-contract"]
tags: ["forge-adapter", "partial-success", "remediation", "normalized-output", "worktree", "delete-branch", "audience-mismatch"]
req: BUG-195
created: 2026-08-27
updated: 2026-08-27
---

## What Happened

BUG-150 diagnosed `gh pr merge` correctly and completely: it is two operations
behind one flag — a remote merge, then a local tidy-up that aborts at the first
failure — and its exit code is a claim about both. Three real merges had been
reported as failures and classified `network`, the one class that invites a retry
against an already-merged PR. The fix asked the forge what actually happened,
returned 0 with `state=MERGED`, demoted `error_class` to `warn_class`, and added
a `local-git` class so a local failure would never again read as transient.

That fix was right. It stopped one step short.

Having established that the remote branch survives, it delegated the cleanup to
the caller — as a sentence:

```
warn=merge completed remotely, but gh post-merge cleanup failed; the source branch
     is likely NOT deleted — remove it with: git push origin --delete <branch>
```

Every consumer of that partial is a skill following a documented step sequence,
branching on the adapter's normalized `key=value` fields. `warn=` is not one of
them. A grep across all six call sites found **no handling of `warn=` whatsoever**,
and the sentence carried a literal `<branch>` placeholder the adapter never
substituted — so even a caller that wanted to obey it had nothing to run.

The trigger was not exotic. It is the *default* topology of an agent session: a
worktree, with the primary checkout sitting on `main`. Essentially every merge the
toolkit performed from a worktree needed a human to read stderr and finish the job
by hand. The one place that mitigated it — `agents/pipeline-runner.md`, with a
"cd to the primary checkout first" note — had not propagated to `/bugfix` or
`/wrapup`, and was in any case incomplete: it clears the `main` collision but not
a fix branch still checked out in the worktree.

## Lesson

1. **Identify who executes your remediation before you write it.** "Tell the
   caller" is only a fix when the caller is a thing that reads. Here the caller
   was a skill parsing `key=value`, and the remediation was English prose with an
   unfilled placeholder — a fix-shaped comment. Ask concretely: *what code path
   consumes this, and what would it have to do to act on what I am emitting?* If
   the honest answer is "a human would have to notice it," you have written
   documentation, not a fix.

2. **Every distinct fact in a partial success gets its own field.** "Merged" and
   "branch tidied" are independent outcomes and must be independently reportable.
   Collapsing the second into prose attached to the first makes it unbranchable.
   `branch_deleted=<1|0|skipped-fork>` is actionable; a sentence is not. This is
   the general shape: when one call does N things, the result surface needs N
   answers, not one answer and N-1 footnotes.

3. **Finish the half you can finish.** The adapter knew the merge had landed,
   knew deletion had been requested, and was one `gh pr view` from the branch
   name. Prefer completing the operation over describing the gap. And look for an
   instrument that sidesteps the original obstacle rather than retrying through
   it: `git push origin --delete` updates a remote ref and touches no local ref,
   so it is *structurally* immune to the worktree collision that broke gh's
   cleanup — not merely less likely to hit it.

4. **A correct fix can still stop short, and the leftover is hard to see
   precisely because the loud symptom is gone.** BUG-150 removed the false
   failures, so the surface went quiet and the surviving branch looked like a
   footnote rather than an unfinished requirement. When you fix the *reporting*
   of a partial failure, ask separately whether you also fixed the *outcome* —
   they are different bugs, and the second one hides behind the first one's fix.

5. **When a mitigation lives as prose in one call site, assume the others do not
   have it.** `pipeline-runner.md` held this knowledge alone while two sibling
   skills invoked the same op unguarded. A constraint that must hold at N call
   sites belongs at the choke point they all pass through — the adapter — not
   replicated into N documents where it can be N-1 kinds of missing.

## Why It Matters

Toil that a human absorbs silently is invisible in every metric: the merge
succeeded, the tests passed, the pipeline reported done. The cost showed up only
as a manual `git push origin --delete` after each merge, and as a latent leak
whenever nobody read the warning.

Worth stating precisely, because the temptation is to inflate it: a survey of the
toolkit and all four consumer repos found **no orphaned branch actually
attributable to this bug** — the `promote/*` branches in atelier-fashion are
deliberate REQ-380 snapshots. The claim is "this cost a manual step on every
worktree merge and could have leaked," not "this had already made a mess." That
is why it was filed `medium` and not `high`.

## Applies When

- Writing an error, warning, or remediation path — ask who reads this channel and
  what they can do with what you wrote
- Designing or extending a normalized result surface, especially for an operation
  that can partially succeed
- Fixing the *reporting* of a failure — check separately whether the underlying
  outcome is also fixed
- Wrapping a third-party CLI whose single command performs several operations with
  one exit code
- Reviewing a fix that ends with "the caller should …" — verify a caller exists
  that can, and that every caller does
- Finding a workaround documented in one call site for an op invoked from several
