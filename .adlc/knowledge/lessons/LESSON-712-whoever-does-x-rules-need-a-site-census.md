---
id: LESSON-712
title: "A rule phrased 'whoever performs X owns Y' reaches only the sites you edit — take a census of every X site when you write it, and keep the evidence Y will need"
component: "adlc/sprint"
domain: "adlc"
stack: ["javascript", "markdown", "claude-skills"]
concerns: ["process-compliance", "knowledge-compounding", "silent-failure", "orchestration"]
tags: ["step-8b", "close-out", "workflow-engine", "legacy-engine", "ownership-rule", "site-census", "bug-193", "bug-249", "lesson-626"]
req: BUG-249
created: 2026-10-27
updated: 2026-10-27
---

## What Happened

BUG-193 (2026-08-22) added the Step 8b close-out — `/wrapup`, spec status →
`complete`, the five-field terminal record — and the ownership rule in Step 8c:
"whoever performs the merge owns Step 8b in full". Its fix touched five files:
`proceed/phases-6-8-ship.md`, `proceed/SKILL.md`, `agents/pipeline-runner.md`,
`wrapup/SKILL.md`, `status/SKILL.md`. Those cover two of the four actors that
perform merges: solo `/proceed` and the runner's single-repo self-merge.

The other two — the workflow engine's `wrapupAndMerge` (`mergePrompt` →
`verifyPrStates` → return, authored by REQ-474 three months earlier as a faithful
mirror of the *then* merge-only runner rule) and the legacy orchestrator's Step 5
(merge → pull → move on) — were never edited. Neither loads
`proceed/phases-6-8-ship.md`, so the prose rule could not reach them. For two
months every REQ shipped through `/sprint --workflow`, and every cross-repo or
fallback merge on the legacy engine, captured no lesson, kept `status: approved`,
and never wrote the terminal record. Nothing reported it: `/status`'s BUG-193
stale-state check saw the state half, but "this REQ wrote no lesson" has no
signal at all. Found only while mapping lesson-capture surfaces against an
external framework (BUG-249).

The fix also had to recover evidence the engine had been throwing away:
`verify()` returned `true` and discarded its consolidated findings; `implement()`
discarded each implementer's report. A close-out actor that did not implement
the REQ has nothing to draft a lesson from unless the script keeps those in
memory.

## Lesson

1. **An ownership rule is only as wide as its edit list.** When a rule is
   phrased "whoever performs X owns Y", the fix that introduces it must take a
   **census of every site that performs X** — `grep` for the operation
   (`adlc_forge_pr_merge`, `gh pr merge`), across skills, agents *and* the
   workflow script — and edit each one, or the rule holds only where it was
   written. This generalises LESSON-626 (a rule about one actor does not settle
   the case for another) from *scope* to *propagation*: the sibling that mirrors
   the old rule is still correct by its own comment and will not come looking.
2. **Mirrors age.** A component written as "mirrors rule R" is a copy of R *at
   that time*. When R changes, the mirror does not; grep for "mirrors" and
   "same as" comments when the mirrored rule moves.
3. **Omissions have no signal — build one.** "Did not run" leaves no artifact to
   trip a check. A capture step that is owed must either run structurally (the
   engine's post-terminal pass over every `merged` terminal) or leave a
   negative record (`NO_ENTRY: …`, `closeOut: failed`) that a reader can count.
4. **Keep the evidence a later step is owed.** A leaf's return value that the
   script discards is gone for every later phase. If a close-out, audit or
   lesson will need it, hold it in memory (keyed by REQ, rebuilt on replay) at
   the point it is produced — not reconstructed at close-out from recollection
   (LESSON-626: a record written at close-out from memory is narrative).

## Why It Matters

ETHOS #2 ("Knowledge Compounds") was silently off on the toolkit's fastest path
for two months. The cost is not one missing lesson; it is every lesson the
workflow sprints would have produced, plus `/status` listing merged REQs as
in-flight indefinitely. A one-line census at BUG-193 time would have found four
merge sites instead of two.

## Applies When

- Writing or changing any rule of the form "whoever does X must also do Y"
  (merge → close-out, deploy → smoke-test, allocate → recheck).
- Reviewing a fix whose Files Changed list is shorter than the list of actors
  that perform the governed operation.
- Adding a workflow-engine phase: ask what later phases will need from each
  leaf's output before discarding it.
- Reading a comment that says "mirrors", "same as", or "faithful copy of" —
  check whether the original has moved since.
