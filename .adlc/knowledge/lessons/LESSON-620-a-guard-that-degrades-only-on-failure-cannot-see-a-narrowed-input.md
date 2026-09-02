---
id: LESSON-620
title: "A guard that degrades only on failure cannot see a narrowed input — when the scan root defines the namespace, resolving it wrongly redefines the question instead of failing to answer it"
component: "adlc/id-alloc"
domain: "adlc"
stack: ["shell", "git"]
concerns: ["reliability", "developer-experience"]
tags: ["worktree", "git-common-dir", "namespace", "silent-degradation", "scan-root", "bug-210", "root-cause"]
req: BUG-210
created: 2026-09-02
updated: 2026-09-02
---

## What Happened

`adlc_remote_high` derives the machine-global id high-water by scanning every
checkout under `$ADLC_REPOS_ROOT`, which defaults to the parent of
`git rev-parse --show-toplevel`. BR-11 states the design plainly: *the scan root
defines the namespace*.

`--show-toplevel` returns the **current** worktree. `/proceed` and `/sprint` run
every pipeline in `<repo>/.worktrees/<id>`, so the default resolved to the
worktree container — and the namespace collapsed from seven repos to one:

```
from ~/GitHub/teton-code                        -> root=~/GitHub        repos=7
from ~/GitHub/teton-code/.claude/worktrees/<wt> -> root=.../worktrees   repos=1
```

Three REQ ids were double-issued on one day against ids already held in sibling
repos. The recheck gate caught one of them three days and one merged spec later,
forcing a renumber of a spec already on `main`.

**The derivation never said anything was wrong.** `adlc_remote_high` sets its
`degraded` bit when a source *fails*: an `ls-remote` error, an absent `gh`, a
scan that could not run. Here nothing failed. A linked worktree has a perfectly
good `origin`, so every source succeeded against it and returned `608 0` —
high-water 608, degraded **0**. Confident, and wrong by two.

## Lesson

**A degradation signal that keys on failure cannot detect a narrowed input.** It
answers "did every source I consulted work?" — not "did I consult the right
sources?" When a parameter *defines the question* rather than merely feeding it,
a wrong value produces a well-formed answer to a different question, and every
health check passes.

So: for any input that scopes what a check can see — a scan root, a corpus glob,
a repo set, a branch list, a date window — **assert the scope itself**, not just
the success of the operations inside it. A count is usually enough: "I scanned N
repos" fails loudly at N=1 in a way that "all N scans succeeded" never can. The
regression test for this bug asserts `repos == 2`, not `scan succeeded`, and that
is the arm that goes red.

Two corollaries, both of which cost real work here:

1. **`--show-toplevel` means "this worktree", not "this repo".** Any tool that
   means the repo — a shared counter, a lock directory, a namespace root — must
   use `git rev-parse --path-format=absolute --git-common-dir` and take its
   parent. The `assume` **lock** in this same file had the identical defect and
   was found only by sweeping for the pattern: two worktrees of one repo took
   different lock paths, so `mkdir` mutual exclusion did not apply between them
   at all. One wrong idiom, six call sites.
2. **Trace an invariant to where it is READ, not where it is written.** Two
   plausible root causes were proposed and both were refuted by reading further:
   that the reservation push is per-repo (true, and irrelevant — the *read* fans
   out across every repo inside the same loop), and that reservation refs lagged
   merged artifacts (did not reproduce; both topped out at 619). The write side
   is where a defect *looks* like it should live; the read side is where the
   invariant is actually decided.

## Why It Matters

The mechanism that existed to prevent this — REQ-546's atomic reservation — was
working correctly the whole time. It had shipped five weeks before the collision.
It could not help, because it was being asked about one repo instead of seven,
and nothing in the system could tell the difference between a namespace with one
participant and a namespace it had failed to enumerate.

That is the expensive shape: not a broken check, but a correct check pointed at
the wrong corpus. It survives code review (the logic is right), it survives the
test suite (every test names its own scope), and it survives its own health
signal (nothing failed). It is caught only by asserting the scope.

The cost was not theoretical. Measured on the day of the fix, the pre-fix
derivation run from a worktree would have allocated `REQ-609` — already taken by
another repo — while reporting itself healthy.

## Applies When

- Writing or reviewing any check whose coverage is set by a path, glob, root, or
  member list resolved at runtime — especially one with a `${VAR:-<derived>}`
  default.
- Adding a `degraded` / `healthy` / `ok` signal: ask what it would report if the
  input set were empty or narrowed rather than erroring.
- Using `git rev-parse --show-toplevel` for anything shared across worktrees:
  counters, locks, caches, namespace roots.
- Investigating a defect in a mechanism that "should have prevented this" —
  check what it was pointed at before concluding it is broken.
