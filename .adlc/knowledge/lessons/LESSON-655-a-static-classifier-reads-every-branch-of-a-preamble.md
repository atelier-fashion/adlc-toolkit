---
id: LESSON-655
title: "A statically classified preamble is judged on every branch it could take, not the one that runs"
component: "adlc/skills"
domain: "skills"
stack: ["markdown", "sh"]
concerns: ["privacy", "developer-experience"]
tags: ["preamble", "ethos", "provenance", "teton-code", "fallback-chain", "sh", "tilde-path", "bug-218"]
req: BUG-218
created: 2026-09-06
updated: 2026-09-06
---

## What Happened

Every toolkit skill opened with `` !`sh .adlc/partials/ethos-include.sh … || sh ~/.claude/skills/partials/ethos-include.sh` ``.
Teton Code classifies a skill preamble **before running it** (REQ-614's shell
grammar, applied to preambles by REQ-619) and `sh <file>` is opaque by verb, so
typing any toolkit skill pinned the session to the local tier. The first
rewrite kept the toolkit-copy fallback as `cat ~/.claude/skills/ETHOS.md`, and
the daemon refused that too: a path outside the session root is one the
classifier cannot prove, and — the part that was not obvious — it classifies
the `||` arm whether or not the project copy exists, because it never runs the
line. The shipped block reads only the vendored `.adlc/ETHOS.md`, with `test`,
`cat` and `echo`, all in reach.

## Lesson

When a host judges a preamble **statically**, every segment of a `&&`/`||`
chain must be provable on its own. A fallback that "only runs when the first
copy is missing" still runs in the classifier every time. Write preambles so
that each segment names an in-root file or reads nothing; keep interpreters
(`sh`, `python`, `node`) and home-relative paths out of them, and put the
fallback behaviour in the vendored file (or a notice) rather than in a second
path.

## Why It Matters

The pin is silent to the skill author — the skill works, the session just
stops using the remote tier — and it was the "weird boundary error" a user
spent a diagnosis session on. Under the pre-BUG-214 daemon it was permanent.

## Applies When

Writing or reviewing a `` !`…` `` preamble in any skill, agent or partial that
may run under Teton Code or another provenance-classifying host; choosing
between an executable partial and a `cat` at the call site.
