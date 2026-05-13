---
id: LESSON-007
title: "Two privacy/correctness traps when shipping a 'send file contents to an external API' tool: whitespace in a base64 detector eats prose; basename-only must be applied at every leak point, not just the main one"
component: "tools/kimi"
domain: "developer-experience"
stack: ["python", "regex"]
concerns: ["privacy", "correctness", "testing"]
tags: ["kimi", "base64", "regex", "path-leak", "boundary-tests", "exfiltration"]
req: REQ-413
created: 2026-05-13
updated: 2026-05-13
---

## What Happened

REQ-413 hardened the REQ-412 Kimi tooling. Two issues that REQ-412 reviewers had flagged in
softer terms became sharp regressions when verified in REQ-413:

1. **`extract-chat` raw-base64 filter included `\s` in its character class** —
   `re.compile(r"[A-Za-z0-9+/=\s]+")`. The 500-char prose passthrough test was 12 chars under
   the 512-char threshold, so it passed for the wrong reason — masking the bug. Any 512+ chars
   of letters and spaces (i.e., normal English prose) would have been silently dropped from
   transcripts.
2. **`kimi-write` reference block kept the full `--context` path** even though `pack_corpus`
   had been rewritten to use `basename`. Privacy intent (BR-5) was partially fulfilled, but
   the same data leak existed in a sibling code path the original change author missed.

Both were caught only because Phase 5 dispatched six reviewers; multiple agents independently
converged on the same two issues.

## Lesson

1. **Whitespace and a base64-alphabet character class don't mix.** Base64 per RFC 4648 is
   alphanumeric plus `+/=` with NO interior whitespace. If your detector is supposed to filter
   "real" base64, do not add `\s` to the regex to be "forgiving" — you'll match every long
   prose passage. The right shape is a `re.fullmatch` over `[A-Za-z0-9+/=]+` (no `\s`) against
   a `.strip()`-ed string, gated by a length floor.
2. **Boundary tests must straddle the threshold, not sit comfortably below it.** A test at
   500 when the constant is 512 proves nothing; a test at 511 (pass) AND 512 (filter) proves
   the threshold value. Same rule for any "minimum N" detector.
3. **When a "scrub the path" change ships, audit every place the original path was
   interpolated.** `pack_corpus` was the obvious spot; `kimi-write`'s `<reference path='...'>`
   block was a second leak surface in the same PR. A privacy rule that holds for one code path
   but not the analogous sibling is a hole, not a partial win.
4. **Notice-before-error is better than notice-after-error for privacy notices.** Putting
   `emit_exfil_notice()` before `get_client()` means the user sees the warning even when their
   run will fail on a missing key. The notice is about *intent to send*, not *successful send*.

## Why It Matters

A silent drop in `extract-chat` corrupts every downstream `ask-kimi` invocation that depends on
it — including the doc-update pipeline. A leaked full filesystem path is a small leak per
request but is sent on every `kimi-write --context` call. Both bugs would have been very hard
to spot post-deploy because neither produces an error or an obviously-wrong output.

## Applies When

Writing a content classifier that filters one shape of input (binary, base64, JWTs) from
another (prose, code); shipping a multi-call API tool where path/identifier information needs
to be scrubbed before egress; writing boundary-condition tests for a magic-number threshold.
