---
id: LESSON-438
title: "git push outcomes are literal-distinguishable on stderr — '! [rejected] (non-fast-forward)' is a race, '! [remote rejected]' is policy; verify markers against real output, never guess"
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "git"]
concerns: ["correctness", "reliability"]
tags: ["git-push", "error-classification", "non-fast-forward", "pre-receive", "stderr-parsing", "degradation"]
req: REQ-546
created: 2026-07-23
updated: 2026-07-23
---

## What Happened

REQ-546 BR-5 requires distinguishing three reservation-push failures with
three different responses: a lost race (ref already exists → retry with the
next number), a server-policy rejection (pre-receive hook / forbidden
namespace → degrade loudly), and a transport failure (offline/auth → degrade
loudly). git's exit code is 1 for all of them, so classification must parse
stderr. Empirically (verified against real git output, not from memory):
a lost ref-creation race prints `! [rejected] ... (non-fast-forward)` while a
hook denial prints `! [remote rejected] ... (pre-receive hook declined)` —
and the string `[remote rejected]` does NOT contain the substring
`[rejected]`, so ordered substring matching separates the two cleanly.
Transport failures print neither marker. The implementation matches in that
order: remote-rejected → policy; rejected + non-fast-forward → race;
otherwise → transport.

## Lesson

When a tool folds semantically different failures into one exit code, the
classification markers must be pulled from **actually captured output** of
each induced failure — build the failure in a sandbox (a local bare remote
with a denying pre-receive hook; a concurrent ref creation) and copy the
literal text — never composed from documentation or recollection. Then pin
each marker with a test that re-induces the real condition, so a git version
change that rewords stderr fails the suite instead of silently
misclassifying (a race misread as policy would stop retrying; policy misread
as race would spin the retry bound).

## Why It Matters

The three responses diverge in user-visible behavior: retry is silent,
degradation is loud, and the wrong branch either burns numbers, hides a
server policy problem, or turns a working mechanism into noise. Error
classification is the part of the mechanism most likely to be "obviously
right" in review and wrong against the real tool.

## Applies When

- Branching on any CLI's failure text (git, gh, az, curl): capture the real
  output per failure mode first, and pin it with an induced-failure test.
- Reviewing retry loops: confirm the retry condition cannot match a
  non-retryable failure's output.
