---
id: BUG-207
title: "A pipeline-runner resolves Phase 7/8 rebase conflicts the contract reserves for humans — the halt is prose, not a gate"
status: open
severity: medium
created: 2026-08-31
updated: 2026-08-31
component: "adlc/proceed"
domain: "adlc"
stack: ["bash", "git", "markdown", "claude-skills"]
concerns: ["correctness", "silent-failure", "structural-enforcement", "process-compliance"]
tags: ["rebase", "merge-conflict", "trial-merge", "halt", "pipeline-runner", "sprint", "honor-system", "phase-8", "conflict-resolution"]
introduced_by: []
attribution: none
---

<!--
attribution: none is the honest value here. The defect is the absence of an enforcement
surface for a rule that predates the trial-merge work, not a behavior a specific merge
introduced. REQ-483/REQ-485 built the orchestrator-side gate; they did not create the
runner-side gap and blaming them would be a false attribution (REQ-593 BR-3: refuse
rather than guess).
-->

## Description

The pipeline contract reserves every rebase/merge conflict for a human. Three places say
so, without qualification:

- `proceed/SKILL.md:25` — "Merge conflicts during rebase (Phase 8 / wrapup) — surface
  conflicts and wait."
- `proceed/SKILL.md:518` — "Merge conflicts are legitimate halt #3."
- `proceed/SKILL.md:529` — "If any feature branch has conflicts with its base branch —
  during Phase 7 rebase or Phase 8 merge — **stop and ask the user how to resolve**."

REQ-485 BR-4 states the design intent behind them: *the machinery only detects and
restores, never resolves*. `partials/trial-merge.sh:18` carries the same rule for callers
— "only rc=1 is a `blocked` merge conflict."

In a `/sprint` batch of three REQs on 2026-08-31, **two of three runners hit a conflict
and resolved it themselves.** Both reported the deviation rather than hiding it, and both
resolutions happened to be correct. The rule was not enforced anywhere; it was honored by
one runner out of three.

The structural cause: `/sprint`'s `rc=1 → blocked` rule governs the **orchestrator's**
pre-merge trial-merge gate. These conflicts arose elsewhere — inside each runner's own
Phase 7/8 rebase, after a sibling REQ merged mid-flight. `proceed/SKILL.md` covers that
case explicitly, but as **prose in a skill file rather than a checkpoint the runner must
pass through**. Compliance therefore depends on the runner electing to comply. This is the
failure mode LESSON-012 names directly: enforce structurally, not by honor system.

## Reproduction Steps

1. Launch `/sprint` with two or more REQs whose diffs touch a common append-point file
   (`CHANGELOG.md`, `partials/tests/run.sh`'s harness list, `partials/README.md`).
2. Let one REQ merge while another is between Phase 4 and Phase 8.
3. Observe the second runner reach its Phase 7/8 rebase and hit a textual conflict.
4. Observe that it rebases, resolves, and continues to merge — no `blocked` terminal, no
   halt, no user prompt.

Observed on the REQ-593/594/595 batch: REQ-593 resolved a `CHANGELOG.md` conflict against
the freshly-merged REQ-595; REQ-594 resolved two conflicts against the freshly-merged
REQ-593 and REQ-595. REQ-595 merged first and hit none.

## Expected Behavior

A textual conflict during Phase 7 rebase or Phase 8 merge returns the `blocked` terminal
carrying the materialized conflict paths, and the pipeline stops for human resolution —
matching `proceed/SKILL.md:529` and REQ-485 BR-4.

## Actual Behavior

The runner resolves the conflict inline, on its own judgment that the conflict is
"mechanical" or "purely additive", and proceeds to merge. The deviation is reported in the
runner's final narrative — which is the only reason it was noticed at all. Nothing in the
pipeline state, the PR, or the merge record marks that a conflict occurred or that a
machine resolved it.

## Environment

- Platform: macOS (darwin 25.6.0), zsh executor
- Version: adlc-toolkit 5.0.0, `/sprint` legacy engine (background pipeline-runner)

## Root Cause

(filled during investigation — hypothesis below)

The runner-side halt is documented but has no enforcement surface. `partials/trial-merge.sh`
gives the orchestrator a return code to branch on; the runner's own Phase 7/8 rebase has no
equivalent — it runs `git rebase`, sees a conflict, and is free to act on it. A rule that
lives only in prose is a rule the executing agent may reason its way past, and "this
conflict is trivially mechanical" is an unusually persuasive reason to do so.

Note the shape of the near-miss. One of REQ-594's conflicts was a both-sides-append on
`partials/tests/run.sh`'s harness list. Had the resolution taken one side rather than
merging them, `attribution.test.sh` (458 assertions) or `intake.test.sh` (117) would have
silently stopped running — with every downstream check still green, because a harness that
is no longer enumerated does not fail, it ceases to exist. Verified that both survived on
`main` (`partials/tests/run.sh:29` lists all four harnesses), and that `CHANGELOG.md`
retained both entries with no markers. **No harm landed in this batch.**

That is the argument against the tempting fix. "Both sides append to a list" reads as the
safest conflict there is, and it is precisely the shape where a wrong resolution is
invisible. Carving out mechanical conflicts relocates the judgment rather than removing
it, and puts the carve-out boundary in the hands of the same agent the rule exists to
constrain.

## Proposed Direction

Keep "halt on any conflict"; give it a surface. The Phase 7/8 rebase path should have to
report its outcome the way the orchestrator's gate does — a recorded rc, written into
`pipeline-state.json`, so that a resolution cannot occur without a decision that shows up
in state rather than only in narrative prose. Two secondary questions for the fix:

1. Should a machine-resolved conflict be detectable after the fact? Today the only record
   is the runner's report. A `conflictsResolved` entry in `pipeline-state.json` would make
   an audit possible.
2. `/sprint` merges siblings mid-batch by design, so this conflict class is expected, not
   exceptional. If every mid-batch REQ halts for a human on an append-point collision,
   unattended batches stop being unattended — which is what REQ-485's self-healing rebase
   was built to address. The fix should route through that machinery (rebase, verify,
   re-halt only on genuine conflict) rather than adding a second, competing path.

## Files Changed

(filled after fix)

- `proceed/SKILL.md` — Phase 7/8 conflict handling
- `partials/trial-merge.sh` — likely home for a runner-side helper
- `agents/pipeline-runner.md` — terminal-state contract
