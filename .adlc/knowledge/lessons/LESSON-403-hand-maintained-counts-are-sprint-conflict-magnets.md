<!--
Filename MUST be `LESSON-xxx-slug.md`.
-->
---
id: LESSON-403
title: "Hand-maintained counts and enumerations in shared registry files are sprint conflict magnets — derive them from the registry, and expect parallel REQs that extend the same extensibility point to race at merge"
component: "adlc/sprint"
domain: "adlc"
stack: ["python", "git", "markdown"]
concerns: ["concurrency", "orchestration", "maintainability"]
tags: ["merge-conflict", "registry", "docstring-count", "sprint-waves", "extensibility-point", "trial-merge", "lesson-398", "REQ-522"]
req: REQ-522
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

In a five-REQ parallel sprint, REQ-522 and REQ-525 each added a new lint
check to `tools/lint-skills/check.py`. The check *registrations* were
additive and merged cleanly (the LESSON-398 data-driven-registry property
held), but both REQs also edited the module docstring's hand-maintained
headline — "six per-file checks" → each bumped it differently — and both
edited the prose enumeration beneath it. Result: the only real merge
conflict of the sprint, blocking REQ-522 at its Phase-8 trial-merge gate
(rc=1) until an orchestrator rebase resolved it. The same sprint produced a
second instance: `partials/README.md`'s partials catalog, edited by both
REQ-522 (de-brand wording) and REQ-526 (new entries). Resolution in both
cases was mechanical union — keep both additions, drop the count.

## Lesson

1. **A hand-maintained count or enumeration adjacent to a registry is a
   conflict magnet**: every REQ that extends the registry must edit the same
   line. Either derive the enumeration from the registry itself (LESSON-398's
   pattern, completed) or make the headline count-free ("orthogonal checks",
   not "seven checks"). This also fixes the staleness failure mode — the
   docstring had already drifted to claiming "seven" while enumerating six.
2. **Two in-flight REQs extending the same extensibility point will race
   predictably** — registries, catalogs, copy lists, CHANGELOGs. The sprint
   footprint/manifest overlap check is component/domain-coarse and won't see
   it. When planning a batch, scan the specs for shared registry files and
   either serialize those REQs' merges deliberately or accept one
   rebase-and-union cycle as the cost of parallelism.
3. **The machinery worked as designed**: the trial-merge gate caught the
   conflict, the runner halted without auto-resolving (Ethos #6), and the
   resolution was a 5-minute union. The lesson is about *reducing the
   frequency*, not distrusting the gate.

## Why It Matters

Parallel-by-default (Ethos #3) is only cheap when merges are conflict-free.
Each avoidable conflict converts an unattended batch into an attended one.
The fix is structural (registry-derived docs), not procedural (asking agents
to be careful).

## Applies When

- Adding any "list of all X" prose next to a registry, copy list, or check
  table that multiple REQs extend.
- Planning a sprint batch: grep candidate specs for edits to the same
  registry/catalog files before dispatch.
- Resolving a sprint merge conflict: prefer union-both-additions and remove
  the hand-maintained count while you're there.
