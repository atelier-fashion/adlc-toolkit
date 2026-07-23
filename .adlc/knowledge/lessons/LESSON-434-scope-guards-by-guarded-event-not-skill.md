---
id: LESSON-434
title: "Scope cross-cutting guards by the guarded EVENT, not by the artifact-creating skill — enumerate every point the invariant can be violated"
component: "adlc/skills"
domain: "adlc"
stack: ["markdown", "bash"]
concerns: ["completeness", "process", "multi-user"]
tags: ["guard-wiring", "call-site-enumeration", "recheck", "br-4", "consumer-view"]
req: REQ-545
created: 2026-07-23
updated: 2026-07-23
---

## What Happened

REQ-518 BR-4 mandated a pre-push id recheck "before `/proceed` creates the
`feat/REQ-xxx` branch." Its wiring task (TASK-004) scoped the work to "the
three artifact-creating skills" (`/spec`, `/bugfix`, `/wrapup`) and noted the
`/proceed` call site as "documented at the consumer-view branch-creation
point" — and that consumer-view call site never landed. For ~27 subsequent
REQs, BUG and LESSON ids were recheck-guarded while REQ ids — the kind
multi-user teams collide on most — had no guard at the exact event the BR
named. The gap surfaced only when a real team hit duplicate REQ numbers;
REQ-545 shipped the missing one-block call site.

## Lesson

A cross-cutting guard's call-site list must be enumerated from the **events
that can violate the invariant** ("every point an allocated id becomes a
remote footprint"), not from a convenient skill taxonomy ("the skills that
create artifacts"). The taxonomy frame made the wiring feel complete — three
skills, three call sites, checklist satisfied — while the event frame would
have immediately listed branch creation in `/proceed` as a fourth site.
When a BR names an event in another skill, the wiring task must carry an
explicit acceptance criterion for THAT skill's edit, not a NOTE deferring it;
"documented at the consumer view" is where call sites go to die.

## Why It Matters

An invariant guarded at N-1 of its N violation points reads as "shipped" in
every status view (the REQ closed, the partial exists, tests pass) while the
protection is absent exactly where the highest-value failure occurs. The cost
of the omission compounds silently until a production collision reveals it —
here, months later, at another organization's install.

## Applies When

- Wiring any shared partial/guard into multiple skills (rechecks, telemetry,
  gates): list the guarded events first, then map each to a call site, and
  make each call site its own acceptance criterion.
- Reviewing a wiring task whose scope line says "the N skills that do X" —
  ask what OTHER skills host the guarded event.
