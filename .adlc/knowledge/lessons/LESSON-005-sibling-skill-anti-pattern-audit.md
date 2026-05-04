---
id: LESSON-005
title: "When you remove an anti-pattern from one skill, audit sibling skills for the same code path"
component: "skills/bugfix"
domain: "adlc"
stack: ["markdown"]
concerns: ["skill-correctness", "developer-experience"]
tags: ["topology-mismatch", "cross-reference-rot", "deferred-followup", "canary", "phase-removal", "follows-REQ-380"]
req: REQ-381
created: 2026-05-04
updated: 2026-05-04
---

## What Happened

REQ-380 removed `/proceed` Phase 7.5 (in-pipeline auto-canary) and Phase 8a (snapshot promotion) because they misfit a dev → staging → main promotion topology — Phase 7.5 deployed a feature-branch image straight to production, defeating the staging gate. The architecture phase scoped REQ-380's diff to `proceed/SKILL.md` + `canary/SKILL.md` + `project-overview.md` + a wrapup lesson (REQ-380 AC #8) to keep the change reviewable, **explicitly deferring** any `/bugfix`-side audit. Two defects survived:

1. **Cross-reference rot.** `bugfix/SKILL.md:128` read `Steps (mirrors /proceed Phase 7.5):`. Phase 7.5 was now deleted — a dangling pointer.
2. **Topology hazard inheritance.** `/bugfix` Phase 6 (Canary Deploy — Optional) invoked `/canary` exactly the way `/proceed` Phase 7.5 used to, with the same fix-branch-to-prod side-effect on staging-gated topologies. The anti-pattern REQ-380 removed from `/proceed` was still present, unchanged, in `/bugfix`.

REQ-381 is the deferred follow-up: it deletes `/bugfix` Phase 6, renumbers Phase 7 → Phase 6, and updates the `/canary` manual-only annotation to acknowledge both removals.

## Lesson

Three rules:

### (a) Audit sibling skills before declaring an anti-pattern removed

When a REQ removes a misbehavior from one skill, the same misbehavior often lives in sibling skills built from the same template (here: `/proceed` and `/bugfix` both walked `services:` from `.adlc/config.yml` and called `/canary`). The architecture phase MUST add a "sibling skill audit" line to its scope decision — not as a separate REQ to defer, but as an explicit check whose result is either "no siblings have this code path" or "siblings X, Y do; this REQ either fixes them too or files a tracked follow-up."

### (b) Cross-reference rot is a deterministic side-effect of phase deletion

Any deletion of a numbered phase MUST be followed by a grep for that phase's number across the entire skill corpus (`bugfix/`, `wrapup/`, `canary/`, `sprint/`, anything that might say "see Phase X"). Dangling references aren't subtle — `grep -rn 'Phase 7\.5' .` finds them in seconds. Make this part of the architect-phase scope, not an afterthought.

### (c) Deferred follow-ups SHOULD become explicit REQ entries at architecture time

REQ-380's architecture phase carved out the `/bugfix` fix as out of scope, which was the right call for diff size. But the carve-out lived only in REQ-380's spec text; there was no automatic mechanism that would surface "REQ-381 is needed" the moment REQ-380 shipped. The follow-up only happened because a human noticed and filed it. Fix this by making architect-phase scope decisions emit a follow-up REQ stub (or at minimum a tracked TODO with an owner) at the same time the carve-out is decided — so the deferred work has the same visibility as the work that did ship.

## Why It Matters

When an anti-pattern lives in two skills and only one is fixed, every project that uses the unfixed skill keeps the foot-gun. Here, every consumer running `/bugfix` against a high-severity bug on a staging-gated project would have shipped a fix-branch image straight to prod — exactly the failure mode REQ-380 spent its budget eliminating from `/proceed`. The half-fix is worse than no fix because operators trust the cleanup landed. Cross-reference rot is the cosmetic version of the same problem: a skill that documents a phase that no longer exists is a skill that has lost the trust of its readers.

## Applies When

- A REQ removes a numbered phase, step, or behavior from a skill.
- A REQ removes an anti-pattern from a skill that has sibling skills (`/proceed` ↔ `/bugfix`, `/spec` ↔ `/architect`, etc.).
- An architect-phase scope decision narrows a diff by carving out work for a follow-up REQ.

In any of those cases: grep the skill corpus for the deleted artifact's name/number, audit sibling skills for the same code path, and either fix in scope or file a tracked follow-up REQ at the moment of the carve-out.
