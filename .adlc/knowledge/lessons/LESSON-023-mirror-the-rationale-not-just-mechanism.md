---
id: LESSON-023
title: "When mirroring a hardened pattern to a sibling, port the rationale comments and type-discipline — not just the mechanism"
component: "adlc/bugfix"
domain: "adlc"
stack: ["bash", "markdown"]
concerns: ["correctness", "maintainability", "verify", "parity"]
tags: ["mirror-pattern", "global-counter", "wip-patch", "code-comments", "find-type", "canonical-parity"]
req: REQ-441
created: 2026-05-17
updated: 2026-05-17
---

## What Happened

REQ-441 migrated BUG-ID allocation to a global `~/.claude/.global-next-bug`
counter by replicating the canonical `/spec` Step-2 REQ-counter block. The
implementation was a captured WIP patch written *before* any review. It
reproduced every functional guard correctly (mkdir-lock, `[ -L ]` symlink
pre-check, unreadable/empty fail-loud, parent `[ -n ]` guard) — so it
"worked", and BUG-054/BUG-056 had already been allocated through it live.

But the Phase-5 multi-agent verify (correctness + quality + architecture +
security + test, all independently) found two faithful-mirror gaps the WIP
had silently introduced:

1. The four canonical **inline rationale comments** (why the lock-acquire
   hard-fails — REQ-416 verify C1; why the counter read fails hard — M2;
   the rmdir TOCTOU residual — LESSON-014; the subshell-`exit`-only-exits
   the subshell parent guard — LESSON-015) were dropped. The code still
   ran; the *why* was gone.
2. The bootstrap `find` dropped the canonical's `-type` discipline:
   `/spec` uses `-path '*/.adlc/specs/REQ-*' -type d` (specs are
   directories); the WIP used `-path '*/.adlc/bugs/BUG-*'` with no type
   filter, where the correct sibling-analog is `-type f` (bug reports are
   `.md` files).

## Lesson

**A patch that reproduces a hardened pattern's *behavior* is not the same
as a faithful mirror of the pattern.** The comments that encode *why* each
guard exists, and the small structural disciplines (`-type d`/`-type f`,
BSD-portable flags), are part of the pattern — dropping them is a real
divergence even when the happy path still works. When the design mandate is
"mirror the canonical block" (and especially for a WIP written before
review), verify **parity against the source block**, not just functional
equivalence: diff the new block against the canonical one and account for
every line that differs. A difference is either a correct
sibling-substitution (`REQ`→`BUG`, dir→file) that should be *documented as
deliberate*, or an accidental omission that should be restored.

## Why It Matters

The dropped comments are exactly the LESSON-014/LESSON-015 rationale that
stops a future maintainer from "simplifying" a guard back into the bug it
defends against — losing them re-arms those traps silently. The missing
`-type f` was benign here only by luck (the downstream `grep -oE` salvaged
a number); the next mirrored pattern's omission may not be. "It works, and
it's already been used in production" is the most dangerous form of green:
it is precisely how the WIP sat unshipped-but-live for days with these gaps.

## Applies When

- Porting/mirroring any proven pattern to a sibling: counters, mkdir-locks,
  the Kimi gate, telemetry blocks, retrieval scaffolds — the toolkit does
  this often.
- Reviewing a captured/stranded WIP patch authored before the review gate:
  treat "mirrors X" as a claim to verify line-by-line against X, not a
  given.
- Writing the verify prompt: explicitly frame it as "divergence from the
  canonical block is the bug; canonical-shared properties are accepted" so
  reviewers find the real gaps instead of re-litigating the reference
  pattern's accepted residuals.

## Related

- REQ-441 — this migration; the canonical source is `/spec` Step 2.
- LESSON-014 / LESSON-015 — the rationale the dropped comments encoded
  (mkdir-lock symlink TOCTOU; `exit 1` in `$(...)` only exits the subshell).
- LESSON-016 — sibling discipline: a regression-guard/parity artifact for
  the failure mode you are defending is load-bearing, not optional.
