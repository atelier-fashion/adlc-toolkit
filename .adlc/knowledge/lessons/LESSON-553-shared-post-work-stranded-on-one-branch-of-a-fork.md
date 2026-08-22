---
id: LESSON-553
title: "Post-work placed under one arm of a conditional is skipped by the other arm — put the shared close-out after the fork, not inside it"
component: "proceed/phase-8"
domain: "adlc"
stack: ["md"]
concerns: ["correctness", "observability", "instruction-design"]
tags: ["topology-fork", "shared-close-out", "pipeline-state", "terminal-record", "single-repo", "literal-reading", "partial-write", "clustering-as-evidence"]
req: BUG-193
created: 2026-08-22
updated: 2026-08-22
---

## What Happened

`/proceed` Phase 8 forks on topology: single-repo vs cross-repo. The fork was
meant to decide only **who performs the merge**. But everything that happens
*after* the merge — run `/wrapup`, tear down the worktree, write
`"completed": true` — was written as steps 2–5 of a numbered list under a
heading reading **"Cross-repo merge sequencing"**.

The single-repo bullet ended at "Terminal claim is `merged`."

So a single-repo run did exactly what it was told: merged, claimed `merged`,
and exited — leaving a `pipeline-state.json` that said the pipeline never
finished. In a single-repo project, *every* REQ takes that path. An audit of 36
state files found 12 contradicting their own merged PRs.

Two aggravating factors made it worse and harder to see:

- `/wrapup`, the actor the phase delegates to, wrote a **partial** record
  (`completed:true` + a `phaseHistory` entry, but not `completedPhases += 8`,
  `currentPhase`, or `merged`). So even the path that closed the file closed it
  wrong, in a *different* way.
- When the terminal was `pr-ready` (orchestrator override, user-reserved
  merge), `completed:false` was correct at that moment and became wrong the
  instant the PR landed. Nothing was specified to reconcile it, and nothing in
  the pipeline ever revisits a REQ after the run exits.

## Lesson

**When a conditional decides *who* does something, the work that follows
belongs after the branches converge — not inside one of them.** If both arms
owe the same close-out, give it its own step that both arms are explicitly
routed to, and say so in the step's own title ("runs in BOTH topologies").

Three supporting rules this cost us:

1. **A gate line is a contract, not an instruction.** "After completion: append
   `8`, set `completed:true`" appeared in the phase header the whole time. It
   described the obligation; no step performed it. Contracts need a step that
   discharges them.
2. **Name the whole obligation wherever you name part of it.** A note reading
   "State write is mandatory: set `repos[<id>].merged = true`" reads as
   exhaustive. It was the resume anchor, not the terminal record — and every
   reader treated it as the latter.
3. **Ordering inside the close-out matters.** The original list removed the
   worktree *before* writing state, without saying which checkout holds the
   file. Write the record first, and name its target.

## Why It Matters

The state file is the pipeline's only self-report. When it silently disagrees
with the repo, `/status` shows phantom "active pipelines," resume logic can
re-enter a finished REQ, and the record you would consult to reconstruct what
happened is the one thing you cannot trust. Nothing self-corrects: 12 files
stayed wrong across weeks and had to be reconciled by hand against the forge.

**The diagnostic worth keeping:** the errors *clustered by kind* — always the
same fields wrong, matching the specific gap in whichever actor ran. Random
forgetting scatters; a document defect clusters. When you see a systematic
field-level pattern in "the model forgot to…", suspect the instructions before
the implementer.

## Applies When

- Writing or reviewing any multi-branch skill phase where the branches share
  post-work (topology forks, platform forks, mode forks).
- Adding a step to one arm of an existing fork — check whether it belongs to
  both.
- Any workflow whose terminal state is written by a *delegated* actor: verify
  the delegate writes the complete record, and re-read after writing.
- Designing a halt state (`pr-ready`, `blocked`) that is correct on exit but
  goes stale later — name who reconciles it, in durable state, before exiting.
