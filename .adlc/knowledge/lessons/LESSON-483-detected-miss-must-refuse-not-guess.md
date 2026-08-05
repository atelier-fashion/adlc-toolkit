---
id: LESSON-483
title: "A detected miss must refuse, not fall back to the closest guess"
component: "wrapup/discovery"
domain: "adlc"
stack: ["sh"]
concerns: ["correctness", "knowledge-quality", "observability"]
tags: ["fallback-design", "content-anchor", "derived-keys", "silent-failure", "path-encoding"]
req: BUG-152
created: 2026-08-05
updated: 2026-08-05
---

## What Happened

`/wrapup` picks the session transcript to delegate by encoding the working directory into a
`~/.claude/projects/` directory name, then preferring the candidate that mentions the active
REQ id. Two things went wrong, and only the second one actually caused the damage.

The encoder replaced `/` but not `.`, so sessions inside a Claude Code harness worktree
(`<repo>/.claude/worktrees/<slug>`) computed a directory that does not exist. The key was
*derived by reasoning about the encoding rule* rather than checked against a real listing —
one `ls ~/.claude/projects/` would have shown `--claude` where the code produced `-.claude`.

That miss was then handled by falling back to "newest transcript in the closest candidate
directory." The content anchor had already done its job — it correctly reported that **no**
candidate mentioned the REQ — and the code proceeded anyway. It delegated an unrelated
transcript, and the delegate produced a fluent, correctly-formatted lesson about a feature
nobody had worked on. The only trace was a soft stderr line reading like an informational
note. Observed on `teton-code`: an Aug-1 transcript chosen to wrap up work from Aug-5.

## Lesson

**When a lookup has an anchor and the anchor misses, refuse. Do not substitute a nearby
candidate.** A miss that has been *detected* is the good case — the expensive failure is
converting that detection into a plausible wrong answer. Reserve "closest match" for when
there is no anchor to check against at all, and make the refusal path a first-class outcome
that downstream consumers already handle, not an error.

Two supporting habits:

- **Derived keys get verified against reality, not reasoned about.** If code computes a
  filesystem path, cache key, or id from a transformation rule, check a real listing before
  trusting the rule. Encoding tables are exactly the kind of thing that is 95% right.
- **Match on both sides through the same transform.** Comparing `encode(want)` against
  `encode(each_real_entry)` — rather than stat-ing one computed name — survives the parts of
  the rule you got wrong, and costs nothing behind an exact-match fast path.

## Why It Matters

A wrong-but-plausible artifact is worse than a missing one. `/wrapup` writes its output to
`.adlc/knowledge/lessons/`, where it is consumed by `/spec`, `/architect`, `/reflect`, and
`/review` as accumulated project truth. Nothing downstream marks a lesson as suspect, so a
transcript mix-up becomes permanent, cited, load-bearing misinformation — and it is far
harder to notice than an empty section, because it reads exactly like real work.

The failure was also structurally invisible: nothing threw, nothing exited non-zero, and the
one warning was worded as an FYI. Any fallback that can silently produce a wrong artifact
needs to be loud enough that a passing human notices, or removed.

Note the telemetry corollary — a refusal must be distinguishable from a skipped call.
`/wrapup`'s compliance rule mechanically rewrites unsanctioned gate-pass fallbacks into
`ghost-skip`. A legitimate refusal never reaches the call site, so it records
`gate=fail` and escapes that rewrite; that has to be *documented*, or the next reader
"fixes" the refusal back into a guess to satisfy the compliance rule.

## Applies When

- Designing or reviewing any content-anchored lookup: transcript/session discovery, cache
  lookup, fixture selection, "find the most relevant X" heuristics
- Any code path whose fallback is "newest", "closest", "first", or "best match" — ask what
  happens when the anchor is present and simply does not match
- Deriving a filesystem path, id, or key from an external system's naming rule
- Writing an artifact that lands in a knowledge base or other durable, trusted store, where
  a wrong entry is not self-correcting
