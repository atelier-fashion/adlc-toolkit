---
id: LESSON-737
title: "`git status` and `git diff` refresh the index, so a check that promises to write nothing must run git with --no-optional-locks"
component: "adlc/doctor"
domain: "adlc"
stack: ["python", "git"]
concerns: ["correctness", "read-only-guarantee"]
tags: ["git-index", "no-optional-locks", "read-only", "doctor", "consumer-sync", "side-effects"]
req: REQ-654
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "REQ-654 TASK-138: test_consumer_sync_writes_nothing failed, because the toolkit checkout's .git/index mtime changed after check_consumer_sync ran git status --porcelain -- partials and git diff --quiet HEAD origin/main -- partials. It passed once tools/adlc/checks.py:695 ran every probe as git --no-optional-locks. Merged in e642ccf."
confidence: high
enforcement: "test:tools/adlc/tests/test_checks_home.py"
generalizes: []
supersedes: []
---

## What Happened

REQ-654's `consumer-sync` doctor check names its baseline the way BUG-204 asks:
it reads the toolkit clone's branch, whether `partials/` is dirty, and how far it
is behind `origin/<default>`. The spec says the check "never writes to any repo".
The first version called plain `git status --porcelain` and `git diff --quiet`.
A test that snapshotted every file's mtime before and after the check failed. The
check had rewritten the clone's `.git/index`, because both commands refresh the
index's stat cache and write it back when they can take the lock. The fix was one
flag on the shared probe helper, `git --no-optional-locks`, after which the
snapshot was identical.

## Lesson

A git "read" is not read-only by default. `status`, `diff` against the working
tree, and anything else that compares the work tree with the index may refresh
the index and write `.git/index`. Any tool that promises not to touch a repo (a
doctor, a drift report, a status line, a pre-flight probe) runs every git call as
`git --no-optional-locks …`, or exports `GIT_OPTIONAL_LOCKS=0`, in the one helper
all its probes go through. Test that promise with a before/after mtime snapshot of
the whole tree, `.git` included, not only of the work-tree files.

## Why It Matters

The write is invisible in `git status`. But it changes mtimes and can contend
with another process's index lock (a concurrent `/sprint` runner, an editor's git
integration), which then fails with `index.lock exists`. A diagnostic that changes
the thing it diagnoses also breaks the "doctor mutates nothing" contract that
REQ-519 builds on, and you only find out when something else races it.

## Applies When

Writing a diagnostic, report or probe that shells out to `git` against a checkout
it does not own, or against any repo it promises to leave untouched. This applies
especially when the code runs `git status`, `git diff` (without `--cached`
between two commits) or `git describe --dirty`.
