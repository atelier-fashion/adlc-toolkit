---
id: LESSON-398
title: "Concurrent additive registrations conflict textually even when logically independent — data-driven registries make the conflict mechanical, which is the win"
component: "adlc/toolkit"
domain: "adlc"
stack: ["python", "git"]
concerns: ["concurrency", "orchestration"]
tags: ["registry", "subcommands", "merge-conflict", "additive", "sprint-waves", "dispatch"]
req: REQ-518
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

Sprint Wave 3 ran REQ-516 and REQ-518 concurrently; both appended one entry to
the same `SUBCOMMANDS` dict in `tools/adlc/adlc.py` (REQ-519's data-driven
dispatch). When REQ-516 merged first, REQ-518's rebase hit a textual conflict
on those adjacent lines — resolved trivially by keeping both entries, exactly
as the launch guidance ("keep CLI changes additive") anticipated. No semantic
reasoning was required; the conflict carried no risk.

## Lesson

Two truths to hold together when parallel pipelines extend one extension
point: (1) git conflicts on adjacent additions are *unavoidable* — registry
design cannot prevent them; (2) registry design determines whether resolving
them is mechanical (keep both lines) or semantic (re-reason about dispatch
logic, ordering, shared state). REQ-519 BR-11's data-driven dispatch bought
the mechanical kind. Orchestrators should still note the shared file in
launch prompts so runners expect the rebase, and the registry's entries
should stay order-independent so "keep both" is always the right resolution.

## Why It Matters

Parallel-by-default (ethos #3) is only cheap when the merge tax is
mechanical. Extension points designed as code (if/elif chains, ordered
wiring) convert every concurrent addition into a semantic merge that needs a
human — quietly serializing the sprint that was supposed to be parallel.
