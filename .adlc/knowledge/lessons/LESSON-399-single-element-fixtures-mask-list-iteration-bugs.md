---
id: LESSON-399
title: "Single-element fixtures mask list-iteration portability bugs — test with ≥2 candidates"
component: "partials/id-alloc"
domain: "testing"
stack: ["sh", "bash", "zsh"]
concerns: ["portability", "test-coverage", "reliability"]
tags: ["BUG-116", "REQ-518", "zsh", "word-splitting", "SH_WORD_SPLIT", "nullglob", "trailing-newline", "fixtures"]
req: REQ-518
created: 2026-06-11
updated: 2026-06-11
---

## What Happened

REQ-518's `adlc_remote_high` iterated newline-separated candidate-id lists with
`for x in $var`. zsh does not word-split unquoted parameter expansions
(`SH_WORD_SPLIT` off by default), so under the zsh executor any multi-candidate list
reached the `[ -gt ]` integer test as one newline-joined word — high-water came back
0 and allocation silently degraded to local-counter-only, disabling the collision
safety that was the REQ's entire point. The shipped bash+zsh test matrix passed 9/9
because every remote fixture pushed exactly ONE matching branch: a one-element list
is one word, so the broken loop accidentally worked under both shells (BUG-116).

Writing the multi-candidate regression test then exposed two MORE latent defects in
the same surface: (1) `adlc_recheck_id` normalized candidates with
`while read; do adlc_id_dec "$n"; done`, but `adlc_id_dec` prints no trailing
newline, so ≥2 candidates concatenated into one bogus number ("600650") and the
`grep -qx` exact-id collision probe never matched — on either shell; (2) zsh aborts
a no-match glob (`for repo in "$root"/*`, NOMATCH) and the resulting empty function
output was being silently coerced to 0.

## Lesson

When code reduces or iterates a LIST, its tests must exercise a list with at least
TWO elements — single-element fixtures make `for x in $var` word-splitting,
missing-trailing-newline concatenation, and first/last-element bugs all invisible.
For portable shell specifically: never `for x in $var` over newline-separated data
(reduce via `printf '%s\n' | sed/sort/tail` pipelines, or `while IFS= read -r`
when no caller state is mutated); remember per-item helpers built on
`printf '%s'` emit no trailing newline, so their outputs concatenate inside loops;
guard `for x in "$dir"/*` with zsh-only `setopt localoptions nullglob`; and guard
every `[ -ge/-gt ]` consuming derived data with a `case $v in ''|*[!0-9]*)`
loud-fail rather than letting `[` spam stderr and fall through to a silent default.

## Why It Matters

The failure mode was the worst kind: numerically-plausible output, passing tests,
and a silently disabled safety mechanism. Any toolkit partial claiming sh/bash/zsh
portability (BR-6) is one single-element fixture away from shipping the same class
of bug; the BR-6 checklist in id-alloc.sh now includes the word-split rule, and the
matrix includes multi-branch, leading-zero, stubbed-`gh` multi-entry-listing, and
garbage-input cases as the template for future list-consuming partials.
