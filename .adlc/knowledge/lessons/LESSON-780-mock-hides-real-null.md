---
id: LESSON-780
title: "A mock returns the shape its author assumed: run each new forge field once, read-only, against the real CLI"
component: "adlc/partials/forge"
domain: "adlc"
stack: ["gh-cli", "sh", "python"]
concerns: ["verification", "testing", "correctness"]
tags: ["forge", "mock", "null", "normalization", "read-only", "gh"]
req: REQ-659
created: 2026-11-01
updated: 2026-11-01
kind: domain
evidence: "REQ-659 Phase-5 finding 'a null mergeCommit printed as None on the real backend': adlc_forge_pr_view 245 --fields mergeCommit on the real gh printed mergeCommit=None for an open PR, which the mock never did: its fixtures hold an oid or nothing. _adlc_forge_json_to_kv in partials/forge.sh, commit 562ebff, now prints it empty; piping {\"mergeCommit\":null} through the function printed mergeCommit= and an object printed its oid."
confidence: high
enforcement: none
generalizes: [LESSON-757]
supersedes: []
---

## What Happened

Every new `adlc_forge_pr_view` field passed against the mock, whose fixtures hold an oid or
nothing. One read-only call against the real `gh` showed an open PR's `mergeCommit` is JSON null,
which the adapter printed as the string `None`. A caller reading it as a commit would have
carried that string on.

## Lesson

When a new field or op enters a forge adapter, run it once, read-only, against the real CLI on a
PR in each state that matters (open, merged), before trusting the mock. The mock can only return
what its author already believed. Then add that case to the mock or the test: this fix has no
test yet, so the next normalizer edit can lose it.

## Why It Matters

A value that crosses a language boundary as text turns a null into a plausible string, and every
downstream check treats it as data.

## Applies When

Adding a field, op or normalizer to `partials/forge.sh`, or to any adapter whose tests run only
on a fixture of the backend's output.
