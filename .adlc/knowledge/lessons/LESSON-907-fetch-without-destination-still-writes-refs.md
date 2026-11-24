---
id: LESSON-907
title: "A git fetch that names a source and no destination still writes refs: the configured refspec maps it to a tracking ref unless --refmap= says otherwise"
component: "adlc/partials/id-recheck"
domain: "adlc"
stack: ["shell", "git"]
concerns: ["reliability", "safety", "testing"]
tags: ["git-fetch", "refmap", "opportunistic-update", "fetch-head", "read-only-probe", "id-recheck", "reservation-ref", "adversarial-review"]
req: BUG-294
created: 2026-11-24
updated: 2026-11-24
kind: domain
evidence: "BUG-294: partials/tests/id-recheck-rewrite.test.sh case `BUG-294: the recheck creates no tracking ref under that refspec` sets remote.origin.fetch to +refs/*:refs/remotes/origin/* and compares git for-each-ref before and after adlc_recheck_id. With `--refmap=` removed from the fetch in _adlc_rc_reservation_nonce (partials/id-recheck.sh) the case fails: the working copy gains refs/remotes/origin/adlc/ids/req/700. With the flag it passes. The first version of the fix had no flag and its ref check passed, because the test repo had the default refspec."
confidence: high
enforcement: test:partials/tests/id-recheck-rewrite.test.sh
generalizes: []
supersedes: []
---

## What Happened

The BUG-294 fix needs the subject of a reservation commit that `git ls-remote` only gives
the SHA of, so the recheck fetches the ref: `git fetch origin refs/adlc/ids/<kind>/<num>`,
with no destination. The first version passed `--no-tags` and `--no-write-fetch-head`, and
its test compared `git for-each-ref` before and after and found no new ref. The comment
beside the fetch said the working copy's refs were as they were.

An adversarial review of the diff set `remote.origin.fetch` to
`+refs/*:refs/remotes/origin/*` in a throwaway clone and ran the recheck. The clone gained
`refs/remotes/origin/adlc/ids/req/700`. The recheck walks every repo under the repos root,
so it would have written that ref into repos the user was not working in. The same review
pointed out that `-c gc.auto=0` stops only the gc task of the maintenance a fetch can start.

## Lesson

`git fetch <remote> <src>` with no destination is not read-only for refs. Git still updates
any tracking ref that the remote's configured fetch refspec maps `<src>` to. A clone with
the default refspec maps only `refs/heads/*`, which is why a fetch of some other namespace
looks clean in a fresh test repo and is not in a clone whose refspec is wider.

A fetch that is meant to bring objects and change nothing else carries all of these:

- `--refmap=` (empty): no tracking ref is updated, whatever the configured refspec says;
- `--no-write-fetch-head`: `FETCH_HEAD` is left alone (git 2.29);
- `--no-tags`: no tag follows the fetched commits in;
- `--no-auto-maintenance`: no gc and no other maintenance task starts (git 2.29);
- `--no-recurse-submodules`, and `-c core.hooksPath=/dev/null`.

Test the claim under the configuration that breaks it. A "creates no ref" assertion in a
repo with the default refspec passes with or without `--refmap=`. Set
`remote.origin.fetch` to `+refs/*:refs/remotes/origin/*` in the test, and check once that
the case fails with the flag removed.

## Why It Matters

A probe that is documented as read-only and is not writes into every repository it walks,
and nothing fails: the refs it leaves behind are valid, and they show up later as
unexplained tracking refs, or as a `git for-each-ref` diff in some other tool's test. The
comment that says "no ref is written" then keeps the next reader from looking.

## Applies When

Writing or reviewing a `git fetch` that exists to read an object (a commit's message, a
tree, a blob) from a remote ref rather than to update the working copy; a helper that runs
git in repositories other than the one the user is in; a test that asserts a git command
leaves refs or `FETCH_HEAD` unchanged.
