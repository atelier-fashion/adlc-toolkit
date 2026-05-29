---
id: LESSON-313
title: "A global counter's namespace is its bootstrap scan root — seed from the live scan, not the doc's repo count"
component: "adlc/wrapup"
domain: "adlc"
stack: ["bash", "markdown"]
concerns: ["correctness", "cross-repo", "id-allocation", "verify"]
tags: ["global-counter", "lesson-counter", "scan-root", "high-water-mark", "cross-repo", "counter-seeding"]
req: REQ-473
created: 2026-05-29
updated: 2026-05-29
---

## What Happened

REQ-473 migrated LESSON-ID allocation to a machine-global
`~/.claude/.global-next-lesson`, mirroring the global REQ/BUG counters. The task
was framed — and the spec first written — as a **two-repo** change:
atelier-fashion (LESSON-233) + adlc-toolkit (LESSON-023), because that is the
"two GitHub repos sharing this ADLC instance" framing in atelier-fashion's
`CLAUDE.md`, and an initial collision survey only scanned those two trees. The
plan was to seed the counter to 234.

But the migration seeds from the same bootstrap scan the live skill runs:
`find <repos-root> -path '*/.adlc/knowledge/lessons/LESSON-*' -type f`. Running
that scan as a dry-run *before* seeding returned a high-water mark of **312**,
not 233. The repos-root (`~/Documents/GitHub`) actually holds **five** ADLC
repos — atelier-fashion (233), **infrastructure (312)**, atelier-web (67),
admin-api (34), adlc-toolkit (23) — whose per-project LESSON sequences overlap
heavily (LESSON-001..023 exist in four-plus repos at once). Seeding to 234 would
have minted LESSON-234 straight into infrastructure's live range — a collision
on the very next allocation. The seed was corrected to **313** and the spec's
premises rewritten mid-flight.

## Lesson

**A "global" counter's namespace is defined by its bootstrap scan root, not by
prose.** When introducing or seeding a machine-global counter, run the exact
scan the code will run and seed from *that* high-water mark — never from a
documented repo count, a hand-picked subset, or a narrower earlier survey. The
"two repos sharing this instance" line was a local, atelier-fashion-centric
description; the counter mechanism (keyed on an absolute `~/.claude/…` path plus
a repos-root scan) had always been machine-wide, and REQ/BUG ids already spanned
all five repos. A new sibling counter must match that reality or it collides on
day one.

## Why It Matters

Seeding a shared monotonic counter below its true cross-namespace max
*guarantees* the collision the counter exists to prevent. The gap between "what
the docs say the scope is" and "what the scan actually reaches" is invisible
until you run the scan: the two-repo grep looked clean; the machine-wide scan
was off by 79 lessons. This is the cross-repo analog of the local "trust the
broad scan, exhaust all repos" rule — a stale or narrow mental model of which
repos participate is a latent correctness bug.

The same dry-run surfaced a corollary: `~/.claude/.global-next-bug` had drifted
to 65 while the on-disk max was BUG-066 — so the next `/bugfix` would have
re-minted BUG-065. REQ-473 re-seeded it to 67. **Counters drift (worktrees,
parallel sessions, manual edits); the filesystem is the source of truth.
Re-derive the high-water mark from a live scan rather than trusting the stored
counter value.**

## Applies When

- Introducing a new global/shared counter, or migrating a per-project counter to
  global (ASSUME is the remaining per-project id type; onboarding a new repo is
  the same shape).
- Seeding or re-seeding ANY monotonic id counter: derive the max from a live
  scan over the real scan root (sibling repos AND worktrees), not from a doc or
  the stored counter value.
- Reasoning about cross-repo scope: "N repos share this" claims in one repo's
  `CLAUDE.md` are local descriptions; the machine-global mechanism may span more.
  Verify with `find <repos-root> -path '*/.adlc/…'`.
- Reviewing a spec whose premises include counts/maxes ("max is 233", "two
  repos", "ranges disjoint") — treat those as verifiable facts and run the scan
  before trusting them. (This REQ's spec was authored with the wrong max and
  corrected when the dry-run contradicted it — the verify gate earned its keep.)

## Related

- REQ-473 — this migration; canonical source is `/spec` Step 2 and `/bugfix`
  Phase 1.
- REQ-441 / LESSON-023 — the BUG-counter predecessor and its faithful-mirror
  retro (port the rationale comments + `-type` discipline, not just the
  mechanism), applied here.
- LESSON-004 / LESSON-002 — global-counter + cross-repo-uniqueness rationale.
- LESSON-014 / LESSON-015 — the mkdir-lock symlink pre-check and subshell
  parent-guard the ported block carries.
- REQ-380 — intentional-gap migration precedent (don't renumber; fast-forward
  past the max).
