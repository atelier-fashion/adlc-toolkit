---
id: LESSON-899
title: "A model runs a fence where it reads it, not where a later step names it: put the precondition and the meaning of its failure line beside the fence"
component: "adlc/proceed/telemetry"
domain: "adlc"
stack: ["markdown", "python"]
concerns: ["reliability", "unattended", "developer-experience"]
tags: ["exec-engine", "exec-prompt", "run-outcome", "telemetry", "step-0", "pipeline-state", "codex", "fence-order"]
bug: BUG-289
created: 2026-11-21
updated: 2026-11-21
kind: process
evidence: "BUG-289; .adlc/research/harness-probes/codex-exec-manual.md launches 7 and 8, fact 10 (codex-cli 0.166.0): both sessions ran R1 on reading proceed/phases-telemetry.md, before Step 0's lessons fence; launch 8 went on, launch 7 reported blocked / setup-error after 55 s on `state file not found`. tools/adlc/tests/test_bug289_early_harness_stamp.py failed before ff855d9 and passes after. One real launch since (launch 9, f53f322) ran the lessons fence before R1; the line's new wording has met no real session"
confidence: medium
enforcement: test:tools/adlc/tests/test_bug289_early_harness_stamp.py
generalizes: []
supersedes: []
---

## What Happened

`proceed/phases-telemetry.md` is read whole before Step 0 and holds five fences, each a ready
call. Where each runs was said once, in the file's opening line ("each is run where that step
says"), and in the step itself, later in the prompt. In two real Codex exec launches both
sessions ran the first fence, the harness stamp, the moment they had read it. Under exec the
session cannot create the primary path's state file; Step 0's lessons fence does, so the stamp
found none, exited 0 and printed `state file not found` and `record-harness failed`. The same
file already said telemetry never halts the pipeline. One session went on. The other reported
`blocked` / `setup-error` and the launch was lost.

## Lesson

A fence a model can read is a fence it may run, at once. Ordering stated in another section
does not hold it back, and a general rule ("never halts") does not outweigh the specific line
the tool has just printed.

- When a file is read ahead of the steps that use it, say beside the fences that none runs on
  reading, and name what each one needs to exist first and what creates it.
- Make the tool's own line say whether to stop. `not found` and `failed` read as a failed
  setup; the line should name the missing thing, say it is not a blocker when it is not, and
  give the next action.
- Do not fix an early call by making the tool create what was missing, when the first writer
  of that thing decides something (here, fresh or resume). Fix what the caller is told.
- A fake session that makes the model's wrong call, through the same entry point, pins that
  the engine tolerates it. It does not show that a real model now behaves: say so until a real
  launch has run.

## Why It Matters

The early call cost nothing by itself: the fence exits 0 and writes nothing. What it cost was
a whole launch, because the session read its output as fatal. Each lost launch is a real
harness run the operator pays for and has to abort by hand.

## Applies When

Writing or moving a companion file that a pipeline reads before the step it serves, adding a
fence whose input another fence creates, or wording the line a tool prints when its input is
absent, in any text an unattended session will read.
