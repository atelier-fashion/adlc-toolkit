---
id: LESSON-013
title: "BSD grep \\b word-boundary in -E silently fails on macOS — use -wF instead"
component: adlc/skills
domain: adlc
stack: [bash, markdown]
concerns: [portability, correctness, reliability]
tags: [grep, regex-portability, bsd-vs-gnu, macos, word-boundary, post-validation]
req: REQ-423
created: 2026-05-15
updated: 2026-05-15
---

## Context

REQ-423 replaced `/wrapup` Step 4's JSONL-discovery heuristic with a content-anchored
walk-up loop: enumerate candidate JSONLs across the encoded-path tree from `$ROOT` up
to `$HOME`, then pick the one whose last 200 lines mention the active `$REQ_ID`. The
critical question for the "mention" check was how to express "match `REQ-422` but
not `REQ-4220`". The first implementation used `grep -qE "\b$REQ_ID\b"` — extended
regex with word-boundary anchors — which is the canonical form on GNU systems.

## What Happened

Phase 5's correctness-reviewer flagged that `\b` in `grep -E` is not reliably
supported on macOS BSD grep (`/usr/bin/grep`). BSD grep's documented word-anchors
are `[[:<:]]` and `[[:>:]]`, not the Perl-style `\b`. On BSD grep with `-E`, the
`\b` is variously treated as a literal `b`, a no-op, or ignored — none of which
match anything in a JSONL line. The consequence: discovery's Phase 1 (id-match)
would have *never matched* on the dominant developer platform, silently falling
through to the Phase 2 "newest in closest dir" fallback every time. The fix's
entire purpose — picking the *id-matching* transcript rather than the newest one
— would have been defeated. The only visible signal would have been the stderr
line saying "REQ-XXX not mentioned in any candidate; using newest as fallback",
which a maintainer might dismiss as the genuine no-match case.

The fix was a one-flag swap: `grep -qwF "$REQ_ID"`. `-F` treats the pattern as a
fixed string; `-w` is supported by both BSD and GNU grep and applies word-boundary
semantics around the fixed token. Bonus: `-F` is also injection-safe against
regex metacharacters in `$REQ_ID`, closing a Phase 5 security finding from the
same review.

Verified live during this REQ's own `/wrapup`: discovery enumerated 73 candidate
JSONLs and correctly matched `REQ-423` in the parent-dir-encoded path, exactly
the scenario the fix targets.

## Why It Matters

Portability bugs in `grep` regex extensions are a recurring class of silent
failure — the script "works" (no syntax error, exit code 0 or 1 as expected),
just never matches. This compounds the problem REQ-423 was solving: a silent
failure mode in the JSONL discovery heuristic was being fixed by another silent
failure mode. Without Phase 5's multi-agent verify, the bug would have shipped
and the `/wrapup` Kimi delegation would have continued to draft from wrong
transcripts on every macOS user — invisibly.

Adjacent context: LESSON-009 captured how a hotfix-verify pass catches what the
original verify missed; this REQ confirms the symmetric principle — review
catches what implementation misses. LESSON-008 (skill delegation = untrusted
data) and LESSON-010 (delegated-model silent truncation) cover the related theme
of "silent failure modes in delegation paths" that REQ-423 was directly
addressing.

## Generalization

- **Never use `\b` in `grep -E`** for any script that may run on macOS. The
  portable forms are `grep -w` (word-regexp, BSD + GNU) or BSD-specific
  `[[:<:]]`/`[[:>:]]` (not portable to GNU).
- **Prefer `grep -wF "$VAR"`** for "find a fixed token bounded by word
  boundaries". Fixed-string + word-regexp is the simplest form, works on both
  greps, and is injection-safe against regex metacharacters in `$VAR`.
- **When verifying portability**, the test platform matters more than the man
  page. macOS bash 3.2, BSD grep, BSD sed, BSD awk all diverge from their GNU
  counterparts in non-obvious ways. The fact that an idiom "works on Linux CI"
  is not evidence it works on a developer's MacBook.
- **Trust the post-implementation review for the failure modes implementation
  misses.** This bug was invisible during implementation — the code looked
  textbook-correct. It became visible only when a reviewer specifically asked
  "does this work on the deploy platform?" Build that question into the verify
  agent prompts.
