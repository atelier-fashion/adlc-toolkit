---
id: LESSON-719
title: "Decide resume from the progress record, not from whether a setup object exists — and check that a sub-step's state write survives the step's own closing rule"
component: "adlc/proceed"
domain: "adlc"
stack: ["markdown"]
concerns: ["correctness", "resumability", "pipeline-state"]
tags: ["pipeline-state", "resume", "gate-protocol", "completedPhases", "idempotency", "lite-lane", "REQ-652"]
req: REQ-652
created: 2026-10-27
updated: 2026-10-27
kind: "process"
evidence: "REQ-652 Phase 5: the reflector and correctness reviewer both found that the lite Step 0 addition appended phases 1-3 and set currentPhase 4, after which SKILL.md's unchanged 'After completing Step 0' rule appended 0 and reset currentPhase to 1; and that a resume re-ran the setup, rewinding a Phase-7 run to Phase 4. Fixed by having the lite setup replace the closing rule and guard on the lane object; the confirmation pass then found that guard strands a Step 0 interrupted after the object was written, fixed by keying the setup on lane.current == lite and 3 not in completedPhases (proceed/phases-lite.md Step 0 additions)"
confidence: "high"
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

REQ-652 added a lite branch to `/proceed` Step 0. It records Phases 1–3 as
skipped and moves `currentPhase` to 4. Three defects in that bookkeeping came
from two review passes:

1. The generic "After completing Step 0" rule, which nobody edited, ran after the
   new sub-step and reset `currentPhase` to 1. The run then either executed
   Phase 1 on a lite REQ or failed the Phase 4 gate.
2. The sub-step had no resume guard. A lite run resumed at Phase 7 re-wrote
   `approved` and rewound to Phase 4.
3. The first fix guarded on "does the `lane` object exist". That object is
   written before the commit and the phase record. A run interrupted in between
   resumed as "already set up", skipped the record, and could reach no phase's
   gate.

## Lesson

When a step gains a sub-step that writes pipeline state:

- Read the step's closing rule. If it writes the same fields, the sub-step must
  say it replaces that rule, and the closing rule must say so too.
- Make "has this already happened" a question about the progress record the
  gates read (`completedPhases`, `currentPhase`). Do not ask it of an object the
  same step creates earlier.
- Make each write in the sub-step idempotent on its own: skip a status write when
  the status is already there, and append only the phases that are missing.
  Then an interruption at any point resumes correctly.

## Why It Matters

`pipeline-state.json` is what a resumed or compressed run trusts over memory. A
guard keyed on the wrong signal either replays finished work or strands the
run where no gate can pass. Nothing reports either case: the pipeline is stuck
until someone edits the state file by hand.

## Applies When

Adding or changing a step in a multi-phase skill that writes `pipeline-state.json`
(or any resumable progress file), especially a branch that skips phases or a
setup that runs once.
