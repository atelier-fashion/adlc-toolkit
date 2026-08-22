---
id: BUG-193
title: "Phase 8's terminal state write lives only on the cross-repo branch, so a single-repo pipeline never closes its own state file"
status: open
severity: medium
created: 2026-08-22
updated: 2026-08-22
component: "proceed/phase-8"
domain: "adlc"
stack: ["md"]
concerns: ["correctness", "observability", "resumability"]
tags: ["proceed", "wrapup", "pipeline-runner", "pipeline-state", "topology-fork", "single-repo", "pr-ready", "terminal-state", "sprint", "orchestrator-override"]
---

## Description

`pipeline-state.json` is the pipeline's own record of what happened, and the
gate contract in `/proceed` Phase 8 says plainly: *"After completion: append
`8`, set `"completed": true`."*

No actor on the single-repo path is actually told to do it.

The instructions that perform the terminal write — run `/wrapup`, tear down the
worktree, set `"completed": true` — are steps 2–5 of a numbered list sitting
under a heading that reads **"Cross-repo merge sequencing"**. The single-repo
bullet directly above it ends at *"Terminal claim is `merged`."* A run following
the document literally (ethos #5) merges its PR, claims `merged`, and leaves the
state file saying the pipeline never finished.

This was found by auditing all 36 `pipeline-state.json` files in `teton-code`
(which is single-repo mode, so **every** REQ there takes this path). 12 of 36
were inconsistent with reality — all 12 PRs were merged on GitHub.

## Reproduction Steps

1. Run `/proceed REQ-xxx` in a single-repo project (no `.adlc/config.yml`
   siblings, or one touched repo).
2. Let it reach Phase 8 and merge its own PR.
3. Read `.adlc/specs/REQ-xxx-*/pipeline-state.json`.

## Expected Behavior

`completed: true`, `currentPhase: 8`, `8 ∈ completedPhases`,
`repos[<id>].merged: true`, and a phase-8 `phaseHistory` entry.

## Actual Behavior

Which fields are wrong depends on which actor ran, and the three failure
signatures are distinguishable in the data:

| Signature | Cause | Observed in `teton-code` |
|---|---|---|
| `completed:false`, no phase-8 record, `merged:false` | single-repo path has no terminal-write step at all | REQ-556, 558, 559, 560, 564, 565, 571 |
| `completed:true` but `completedPhases` missing `8`, or `merged:false` | `/wrapup` Step 3.5 writes an *incomplete* record | REQ-555, 562, 568, 579, 585 |
| never reconciled | terminal was `pr-ready`; merge happened out of band | REQ-559, 560, 571 (orchestrator override) |

## Environment

- Platform: adlc-toolkit @ f067b16
- Version: skills installed at `~/.claude/skills` (identical to repo checkout)

## Root Cause

Three distinct gaps, each mapping to one signature above.

**A. The topology fork strands the terminal write on the wrong branch.**
`proceed/phases-6-8-ship.md` splits Phase 8 into a single-repo bullet and a
cross-repo bullet. The single-repo bullet covers only the merge call. Everything
after the merge — `/wrapup`, worktree teardown, `"completed": true` — is under
`**Cross-repo merge sequencing**:`, and the cross-repo bullet is the one that
points at it ("use the cross-repo merge sequencing block below"). The document
deliberately distinguishes the two paths, so a literal reader is *correct* to
skip that block in single-repo mode — and thereby skips the state write.

**B. `agents/pipeline-runner.md` repeats the omission, and its one mandatory
state write is scoped too narrowly.** The single-repo path says: merge, set
`repos[<id>].merged = true`, claim `merged`. It never mentions `completed`,
`completedPhases`, `currentPhase`, or `/wrapup`. The "State write is mandatory"
gotcha (worktree gotcha 3) names only `repos[<id>].merged`, which reads as an
exhaustive statement of the obligation. This is the actor `/sprint` dispatches —
REQ-559 and REQ-560 both record themselves as pipeline-runner runs.

**C. `/wrapup` Step 3.5 writes a partial record.** It sets `"completed": true`
and appends a `phaseHistory` entry, but not `completedPhases += 8`, not
`currentPhase = 8`, and not `repos[<id>].merged = true`. So even the path that
*does* close the file closes it inconsistently — which is exactly the
`completed:true` + `completedPhases:[0..7]` signature.

**Why the `pr-ready` case is systematic rather than incidental.** When an
orchestrator override or a user-reserved merge halts the run at `pr-ready`,
`completed:false` is *correct at that moment*. Nothing is specified to reconcile
it once the merge actually lands, so the state file stays permanently wrong. No
actor owns the post-`pr-ready` reconciliation.

**Why 24 files are nonetheless fine.** The write is not impossible, just
unspecified — runs that happened to invoke `/wrapup`, or that generalized the
cross-repo block, closed the file. That non-determinism is the tell: the errors
cluster by *kind* (always the same fields, matching the gap in whichever actor
ran), not randomly, which is what distinguishes a document defect from an
implementer lapse.

## Resolution

Fixed the topology fork so **topology decides who merges, never whether the
close-out runs**, and made every actor that writes the terminal record write
all five fields.

**A — `proceed/phases-6-8-ship.md`.** Split Phase 8 into `8a Merge` (the
topology fork, both branches ending in an explicit "continue to 8b"), `8b Close
out (runs in BOTH topologies)`, and `8c` for the `pr-ready` case. The `/wrapup`
call, worktree teardown and state write moved out from under the
`Cross-repo merge sequencing` heading into 8b, where a single-repo run reaches
them. Also **reordered 8b so the state write precedes worktree teardown**, and
named the write target as the primary repo's checkout — the original ordering
removed the worktree first, and a run that had targeted the worktree's copy
would have written to a directory it was about to delete.

**B — `agents/pipeline-runner.md`.** Added a "Close-out (single-repo path)"
section, and broadened worktree gotcha 3, which previously named
`repos[<id>].merged` as *the* mandatory write; it now says that flag is the
resume anchor and the terminal record is still owed. Also spells out the
`pr-ready` note obligation.

**C — `wrapup/SKILL.md` Step 3.5.** Expanded from "set `completed:true` and add
a `phaseHistory` entry" to the full five-field record, with a forge check on
`merged` since `/wrapup` may run standalone after an out-of-band merge.

**Detection — `status/SKILL.md`.** `/status` reads every state file already and
was reporting these as phantom "active pipelines". It now tests four offline
invariants and reports trips under a **Stale Pipeline State** heading with the
reconciliation as the action. This is the check that would have caught the bug
years of runs earlier.

**Considered and rejected:** an `adlc doctor` check. `Profile.repo_root` is the
*toolkit* checkout, so a doctor check would scan the toolkit's own specs, not
the project repo where pipelines actually run. Making doctor scan arbitrary
project repos needs a repo-discovery mechanism it does not have. `/status`
already runs in the right place.

## Files Changed

- `proceed/phases-6-8-ship.md` — Phase 8 restructured into 8a/8b/8c; close-out shared across topologies; state write moved before worktree teardown and given an explicit target
- `proceed/SKILL.md` — Phase 8 summary lists the five-field record and the topology rule, so summary and companion agree
- `agents/pipeline-runner.md` — single-repo close-out section; gotcha 3 no longer reads as the complete state obligation
- `wrapup/SKILL.md` — Step 3.5 writes the complete terminal record
- `status/SKILL.md` — Stale Pipeline State detection via four offline invariants
