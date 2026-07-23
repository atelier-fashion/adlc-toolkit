---
id: LESSON-440
title: "Every collision/anomaly detector needs a benign-path AC — a matrix that only tests adversarial shapes ships false positives through a green suite"
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "git"]
concerns: ["testing", "correctness"]
tags: ["false-positive", "benign-path", "acceptance-criteria", "detector", "self-identification", "bug-145"]
req: BUG-145
created: 2026-07-23
updated: 2026-07-23
---

## What Happened

REQ-546's acceptance-criteria matrix was thorough about every ADVERSARIAL
shape: two-clone races, same-object hazard, cross-machine visibility, policy
rejection, network blackhole, prefix siblings. All green — 140 pytest cases
plus the partials harness under two shells. Yet within hours of merge, the
recheck false-halted on the very first production allocations (LESSON-434–439,
then BUG-145's own id), and a second latent instance surfaced: `/proceed`'s
recheck halts on the REQ's own merged spec dir in the normal
spec-merges-before-implementation flow. Not one AC asked the symmetric
question: what does the detector say about the footprints the CURRENT actor
legitimately owns? The suite could not fail, because the benign path was
never a test case. This happened the same day LESSON-435 (number-keyed probes
cannot self-identify) was filed for the sibling instance one layer up — the
class was named, and the new detector still shipped without a self case.

## Lesson

A detector has two correctness surfaces: it must fire on the adversarial case
AND stay silent on the legitimate one — and the second surface needs its own
explicit acceptance criteria, enumerated per probe/source. When specifying
any collision check, duplicate detector, drift alarm, or integrity gate,
walk each detection source and write the "self/benign actor" AC alongside the
"attacker/collision" AC: who legitimately produces this footprint, at what
point in the normal flow does the detector run relative to it, and what must
the detector conclude? Corollary: when a NEW footprint source is added to an
existing detector (REQ-546 adding reservation refs to the recheck), every
existing caller inherits a new potential false positive — audit call sites
for the benign path at that moment, and plan migration for pre-existing
footprints that lack the new self-identification data (the ledger backfill).

## Why It Matters

A false-positive detector is worse than none at the exact moment it fires:
it halts a legitimate flow with a confident, actionable-looking instruction
(here, a renumber command that would have burned ids in an infinite
treadmill). And because false positives only manifest against real usage,
they sail through any suite that models the world as attacks — the greener
the adversarial matrix, the more convincing the broken detector looks.

## Applies When

- Writing ACs for any new detector, gate, or integrity check: require a
  benign-path case per detection source, not just failure-path cases.
- Extending an existing detector with a new signal source: audit every
  caller for inherited self false positives before merging.
- Reviewing a "detection" REQ whose AC list contains only adversarial
  scenarios — that absence is itself a finding.
