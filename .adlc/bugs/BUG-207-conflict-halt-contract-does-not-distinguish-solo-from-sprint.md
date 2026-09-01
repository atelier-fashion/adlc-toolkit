---
id: BUG-207
title: "The conflict-halt contract does not distinguish solo /proceed from an unattended /sprint, and a machine-resolved conflict leaves no trace outside narrative prose"
status: open
severity: low
created: 2026-08-31
updated: 2026-08-31
component: "adlc/proceed"
domain: "adlc"
stack: ["bash", "git", "markdown", "claude-skills"]
concerns: ["observability", "process-compliance", "developer-experience"]
tags: ["rebase", "merge-conflict", "halt", "pipeline-runner", "sprint", "unattended", "audit-trail", "pipeline-state", "phase-8"]
introduced_by: []
attribution: none
---

<!--
attribution: none. This is a scope question the contract never settled and an
absent audit field — not a behavior a specific merge introduced. REQ-483/485
built the orchestrator-side machinery and wrote the rule as it stands; naming
them as the cause would be a false attribution (REQ-593 BR-3: refuse rather
than guess).
-->

## Description

> **This artifact was rewritten on 2026-08-31.** It was originally filed as
> "a pipeline-runner resolves Phase 7/8 rebase conflicts the contract reserves for humans",
> severity medium, arguing that two runners violated the contract and that the fix was to
> add an enforcement surface. That framing was wrong: on the evidence the runners' behavior
> is defensible and it is the *rule* whose scope is unsettled. The severity and the proposed
> direction changed with it. The original framing is preserved in git history (`8933121`).

In a `/sprint` batch of three REQs on 2026-08-31, two runners hit a rebase conflict during
their own Phase 7/8 and resolved it inline rather than halting. Both reported the deviation
in their final narrative. Both resolutions were verified correct: `partials/tests/run.sh:29`
retained all four harnesses and `CHANGELOG.md` kept both entries with no markers.

Two things are genuinely unresolved. Neither is "the runners misbehaved."

**1. The halt rule's scope was never settled for the mid-batch case.** Two contract lines
bear on it, and they were written for different actors:

- `proceed/SKILL.md:529` — "If any feature branch has conflicts with its base branch —
  during Phase 7 rebase or Phase 8 merge — stop and ask the user how to resolve." This is
  the **runner's** rule, and it reads naturally as written for solo `/proceed`, where a
  human is at the keyboard.
- `sprint/SKILL.md:308` (REQ-485 BR-4) — "Rebase conflicts are always human-resolved — the
  machinery only detects and restores, never resolves." This sits inside the *Scope (v1)*
  paragraph for the **orchestrator's post-merge unblock pass**, describing what that
  automated pass may do to a held REQ's worktree.

So it is not accurate to say nobody considered the sprint context — REQ-485 did, and said
"always". But it said it about the unblock machinery, in a paragraph about the unblock
machinery. Whether it also binds a runner rebasing its own branch after a sibling merged
mid-batch is genuinely ambiguous, and that is the case that actually occurs.

The tension is real either way. The same paragraph draws the distinction this bug is about,
for a *different* halt: "Solo `/proceed` (not under `/sprint`) is unchanged — manual resume,
**because the human is present** (BR-1)." In an unattended batch the human is by definition
not present, and `/sprint` merges siblings mid-batch by design — so append-point collisions
on `CHANGELOG.md`, `partials/tests/run.sh`, and `partials/README.md` are routine, not
exceptional. Two of three runners hit one in a single three-REQ sprint. A rule that halts on
every one converts an unattended batch into a babysitting job, which is the outcome REQ-485
exists to prevent.

**2. A machine-resolved conflict is invisible after the fact.** Nothing in
`pipeline-state.json`, the PR, or the merge record notes that a conflict occurred or that an
agent resolved it. The only record is the runner's closing narrative. Both runners here
volunteered it; a runner that said nothing would leave no trace at all. That is a real
observability gap regardless of how the scope question is decided.

## Reproduction Steps

1. Launch `/sprint` with two or more REQs whose diffs touch a common append-point file.
2. Let one REQ merge while another is between Phase 4 and Phase 8.
3. Observe the second runner hit a textual conflict in its Phase 7/8 rebase.
4. Observe that it resolves and continues — and that afterwards, nothing in
   `pipeline-state.json` records that this happened.

Observed on the REQ-593/594/595 batch: REQ-593 resolved a `CHANGELOG.md` conflict against
the freshly-merged REQ-595; REQ-594 resolved two against REQ-593 and REQ-595. REQ-595 merged
first and hit none.

## Expected Behavior

The contract states explicitly whether a runner's own Phase 7/8 rebase conflict is
human-only in an unattended `/sprint`, or resolvable by the runner under stated conditions —
rather than leaving a reader to infer it from a rule written about the unblock machinery.

Whichever way it is decided, a conflict encountered and resolved during a pipeline run is
recorded in `pipeline-state.json`, so it is auditable without relying on the runner having
chosen to mention it.

## Actual Behavior

The scope is inferred, and two of three runners inferred it one way while the third never
faced the question. The resolutions leave no machine-readable trace.

## Environment

- Platform: macOS (darwin 25.6.0), zsh executor
- Version: adlc-toolkit 5.0.0, `/sprint` legacy engine (background pipeline-runner)

## Root Cause

(filled during investigation — hypothesis below)

`proceed/SKILL.md:529` was written for the solo path and never revisited when `/sprint`
made mid-batch sibling merges routine. REQ-485 introduced the unattended-batch reasoning and
applied it to resume-after-blocker (BR-1) but stated its rebase rule (BR-4) in terms of the
machinery it was building, leaving the runner's own rebase outside the sentence's evident
subject. Neither document is wrong on its own terms; together they under-determine the case
that occurs most often.

## Proposed Direction

Small, and deliberately not an enforcement gate. Building machinery to stop runners
resolving conflicts would harden a rule whose scope is the open question.

1. **Settle the scope in the contract text.** Extend REQ-485 BR-1's solo-vs-sprint
   distinction to cover a runner's own Phase 7/8 rebase, and say plainly which behavior is
   expected in an unattended batch. If runner resolution is permitted, bound it — e.g. to
   conflicts where both sides only add lines — and require the runner to verify the
   resolution preserved both sides rather than asserting it did.
2. **Record it in `pipeline-state.json`.** A `conflictsResolved` entry (paths, phase, and
   how it was resolved) makes the behavior auditable and makes any future decision to
   restrict it measurable.

One caution for whoever takes this. One of REQ-594's conflicts was a both-sides-append on
`run.sh`'s harness list. Had the resolution taken one side rather than merging them,
`attribution.test.sh` (458 assertions) or `intake.test.sh` (116) would have silently stopped
running, with every downstream check still green — a harness that is no longer enumerated
does not fail, it ceases to exist. This argues for **verifying the resolution**, which both
runners did here, not for refusing to resolve. But it is why item 1 should bound the
permission rather than granting it open-endedly: "both sides only add lines" is a checkable
property, "the conflict looked mechanical" is not.

## Files Changed

(filled after fix)

- `proceed/SKILL.md` — Phase 7/8 conflict handling, solo vs unattended
- `sprint/SKILL.md` — REQ-485 scope paragraph
- `agents/pipeline-runner.md` — terminal-state contract
