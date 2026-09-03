---
id: LESSON-626
title: "A rule written about one actor does not settle the case for another — bound machine conflict-resolution to a property a machine can check, and write the audit record at the moment of the event"
component: "adlc/proceed"
domain: "adlc"
stack: ["bash", "git", "markdown", "claude-skills"]
concerns: ["process-compliance", "observability", "auditability", "reliability"]
tags: ["merge-conflict", "rebase", "sprint", "unattended", "pipeline-runner", "contract-scope", "append-point-collision", "diff3", "pipeline-state", "audit-trail", "bug-207", "bug-212"]
req: BUG-207
created: 2026-09-03
updated: 2026-09-03
---

## What Happened

In a three-REQ `/sprint` on 2026-08-31, two runners hit a rebase conflict in their own
Phase 7/8 — append-point collisions on `CHANGELOG.md` and `partials/tests/run.sh`, routine
when siblings merge mid-batch — and resolved them inline. Both resolutions were correct.
Both were volunteered in the runners' closing narrative. Nothing else recorded them.

The bug was first filed as "runners violated the contract". It was rewritten within the
day, because on the evidence the *rule* was what had never been settled. Two contract lines
bore on the case, written for different actors: `/proceed`'s "stop and ask the user" (the
solo rule — a human is at the keyboard) and REQ-485 BR-4's "rebase conflicts are always
human-resolved" — written about the orchestrator's unblock pass, inside the paragraph about
that pass. Read as binding the runner's own rebase, BR-4 would turn every unattended batch
into a babysitting job, which is the outcome REQ-485 exists to prevent. Read as not binding
it, nothing said what the runner may do. Two of three runners inferred one way; the third
never faced the question. That was BUG-207. The absent record was BUG-212.

The caution that shaped the fix: one of the resolutions was a both-sides-append on
`run.sh`'s harness list. Had the resolution taken one side, a whole test harness would have
stopped running with every downstream check still green — a harness that is no longer
enumerated does not fail, it ceases to exist.

## Lesson

1. **A rule about one actor does not settle the case for another.** When a contract says
   "always human-resolved", ask *whose action* the sentence governs. BR-4 was true and
   complete for the unblock machinery and silent about the runner — and the silence read
   differently to each reader. Write the rule per actor, and say which actor each line
   binds. The distinguishing question was **who is present**: solo means a human is at the
   keyboard; unattended means the contract must say what the machine may do instead of
   asking.

2. **A permission granted to a machine must be bounded by a property a machine can
   check.** "Looked mechanical" is a judgment; "every conflicted hunk is both sides purely
   adding lines" is a test — with diff3 markers it is exactly "every base section is
   empty". Prove the classifier on positive *and* negative fixtures before writing it into
   prose, and give it a benign path (refusal must touch nothing). Nothing-to-classify is a
   precondition error, never a pass. Then verify the resolution against evidence the
   resolution step did not itself produce (a sidecar of each side's lines), rather than
   trusting the step that just did the work.

3. **Keep-both with verification is the only resolution that cannot silently retire
   something.** Any resolution needing judgment about *which* side is right is a human's
   call. Bound the machine to the one strategy whose failure mode is loud.

4. **An audit record is written by the actor, at the moment of the event, and read by
   nothing for control flow.** `pipeline-state.json` had every field the orchestrator needed
   to *decide* and none it needed to *remember* — observation that is not load-bearing
   does not get built unless built deliberately. Make the field additive and optional
   (absent means "none", never "missing"), write it before continuing (a crash after the
   event must still leave the record; an entry written at close-out is narrative in JSON
   clothing), and surface it where humans look. The record is what makes the permission
   in (2) measurable — and what makes any future decision to tighten it a decision about
   data rather than about anecdotes.

## Why It Matters

Without (1), two runners in one batch make opposite inferences from the same text and both
are defensible. Without (2), the permission is "use your judgment", which is the failure
the caution describes. Without (4), the batch that resolved conflicts is indistinguishable
from the batch that hit none, so the rule cannot be enforced *or* relaxed on evidence.
The cost of the miss is not a crash; it is a test harness that quietly stops existing three
sprints later, with nothing to go back and re-examine.

## Applies When

- Writing halt, permission, or resolution rules that an unattended runner will read — ask
  which actor each sentence binds and whether a human is present.
- Granting any automated step permission to resolve, merge, or override: bound it to a
  fixture-proven checkable property with a benign path, and verify against independent
  evidence.
- Adding a field to `pipeline-state.json` or any state file: if it is for audit rather
  than control flow, it needs a deliberate write-at-event rule or it will never be written.
- Resolving append-point collisions on enumerating files (`CHANGELOG.md`, harness lists,
  registries): keep both, then prove both survived.
