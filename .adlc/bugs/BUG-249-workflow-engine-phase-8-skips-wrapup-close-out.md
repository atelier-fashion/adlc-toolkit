---
id: BUG-249
title: "Neither sprint engine's orchestrator-owned Phase 8 runs the Step 8b close-out: the workflow engine never does, and the legacy orchestrator skips it for cross-repo and fallback merges — no lessons, status stays approved, terminal record never written"
status: open
severity: high
created: 2026-10-26
updated: 2026-10-26
component: "adlc/sprint"
domain: "adlc"
stack: ["javascript", "markdown", "claude-skills"]
concerns: ["knowledge-compounding", "process-compliance", "silent-failure", "orchestration"]
tags: ["workflow-engine", "legacy-engine", "wrapup", "phase-8", "step-8b", "knowledge-capture", "pipeline-state", "ethos-2", "harness2", "bug-193", "REQ-647"]
introduced_by: ["REQ-474"]
attribution: manual
related: ["BUG-193"]
---

<!--
introduced_by is set manually and names who AUTHORED `wrapupAndMerge` (REQ-474,
commit 7995100, 2026-05-30). It is not a claim that REQ-474 dropped an existing rule:
Step 8b did not exist yet (see Root Cause). /bugfix Phase 2 should confirm via blame
per REQ-593 BR-2.
-->

## Description

`/proceed` Phase 8 has two halves. 8a merges; 8b closes out, and
`proceed/phases-6-8-ship.md` says of 8b: "**runs in BOTH topologies** … Do not skip any
of these because the REQ touched only one repo: 1. Run `/wrapup` with the REQ ID … 2.
Write the terminal state record — before any worktree is torn down." Step 8c adds the
ownership rule: *whoever performs the merge owns Step 8b*. `/wrapup` is where ETHOS #2
("Knowledge Compounds") is honoured: Step 3 flips the spec to `status: complete` and
(item 5) writes the terminal state record; Step 4 captures `ASSUME-*`/`LESSON-*`.
(`/bugfix` Phase 6 Step 4 is the other lesson writer; both are reached only through
close-out.)

**Workflow engine.** `workflows/adlc-sprint.workflow.js` implements Phase 8 as
`wrapupAndMerge` (L1960): for a single-repo REQ it dispatches `mergePrompt` (L1523),
whose steps are *confirm mergeable → `adlc_forge_pr_merge` → set
`repos[<repo>].merged = true`*, re-verifies with `gh pr view` via `verifyPrStates`, and
returns the `merged` terminal. For a cross-repo REQ it returns `pr-ready` and the ADR-12
barrier (`sequenceCrossRepoMerges`) merges. In neither path is `/wrapup` invoked or Step
8b performed inline, and nothing in `sprint/SKILL.md`'s workflow branch (L35–94) closes
out after `{results}` returns. The file contains no occurrence of `knowledge`; its
`wrapup` strings (L14, L967, L993, L1102, L1514, L1944, and the function name) are a
phase title, comments and a call. The engine reads `requirement.md` status for
eligibility (L1188) but never writes it; `completed: true`, `8` in `completedPhases`
and the phase-8 `phaseHistory` entry are never written.

**Legacy engine.** The `pipeline-runner` reaches Step 8b only when it merges its own
single-repo PR (`agents/pipeline-runner.md:85-92`). For a cross-repo REQ it returns
`pr-ready` and hands "the merge *and* the Step 8b close-out" to the orchestrator
(`pipeline-runner.md:96-97`); the same hand-off happens when a runner's merge fails
(LESSON-355 — background runners often cannot run `gh pr merge` at all). The legacy
orchestrator's Step 5 (`sprint/SKILL.md`) is then: merge the PR → pull main → move on.
No `/wrapup`, no terminal record. The ownership rule that would require it lives only
in `proceed/phases-6-8-ship.md` Step 8c, which the orchestrator never loads.

Found while mapping the toolkit's knowledge-capture surfaces against Google's Harness²
(`.adlc/research/harness2-adaptation.md` §2): lessons are written only inside
`/wrapup`/`/bugfix` close-out, and both sprint fast paths bypass it.

## Reproduction Steps

1. In a repo with an approved single-repo REQ, run `/sprint --workflow REQ-xxx` and let
   it reach the `merged` terminal.
2. `ls -t .adlc/knowledge/lessons/ | head -3` — no `LESSON-*` from this REQ.
3. `grep '^status:' .adlc/specs/REQ-xxx-*/requirement.md` — still `approved`.
4. `grep -E '"completed": *true' .adlc/specs/REQ-xxx-*/pipeline-state.json` — no match
   (`completed` is absent or `false`; `currentPhase` absent or `< 8`; only
   `repos[<repo>].merged` is `true`). The toolkit does not assume `jq`.
5. Static confirmation without a run:
   `grep -n -i 'knowledge\|wrapup' workflows/adlc-sprint.workflow.js` — no `/wrapup`
   invocation and no capture step.
6. Legacy path: run a cross-repo REQ under the legacy engine; after the orchestrator's
   Step 5 merge, repeat steps 2–4 — same result.

## Expected Behavior

After a verified merge, whichever actor performed it runs the Step 8b close-out. The fix
contract, for both engines:

1. **`/wrapup` gains a close-out mode** (`/wrapup REQ-xxx --close-out`) that runs Step 3
   (artifact updates + the terminal record), Step 4 (knowledge capture) and Step 5
   (summary) only. It skips Step 2 (branch/push/PR/merge — the merge already happened),
   Steps 6–8 (deploy, cleanup — nobody is present to confirm), and Step 4's REQ-423
   transcript discovery (the close-out actor is not the implementing session); it
   drafts from supplied inputs. Running the full `/wrapup` post-merge would push, open a
   PR, re-merge, delete branches and deploy to every listed device.
2. **The terminal stays `merged`.** `TERMINAL` gains `closeOut: ok | failed | skipped`
   (closed schema extended, structural test). `unblockHeldReqs` and the dispatcher treat
   `merged` as merged regardless of `closeOut`; a held REQ is released when its blocker
   merged even if the blocker's close-out failed. The close-out prompt receives
   `args.answers` on resume so a retry re-runs instead of replaying the journal's cached
   failure.
3. **Inputs are threaded in memory.** The script keeps a per-REQ evidence map
   (consolidated Phase-5 findings from `verify()`, implementer reports from
   `implement()`, the task list), rebuilt on replay, and passes it to the close-out
   leaf's prompt together with a read-leaf result for the task files and the merged PR's
   file list. The "no evidence ⇒ `NO_ENTRY: close-out had no run evidence`" decision is a
   pure-JS helper with a unit test. (`verify()` currently discards `consolidated`;
   `implement()` discards the report; the script has no filesystem or `gh`.)
4. **Close-outs are serialized per repo and never touch the live checkout.** Each runs
   in a dedicated `.worktrees/REQ-xxx-close-out` cut from the fresh integration tip, one
   at a time per repo (the same barrier that serializes merges — up to five single-repo
   REQs otherwise close out concurrently against one git index). Artifacts are committed
   as `chore(REQ-xxx): close-out — spec complete[, LESSON-nnn]` and merged through the
   forge adapter by the same serialized step; the worktree is then removed. Sibling
   worktrees cut afterwards see the new lessons.
5. **All five terminal-record fields** go to the primary repo path's
   `pipeline-state.json` before any teardown: `completed: true`, `currentPhase: 8`,
   `8` in `completedPhases`, a phase-8 `phaseHistory` entry naming the merge commit, and
   `repos[<id>].merged == true` for every touched repo — the BUG-193 list, not a subset.
6. **Legacy orchestrator**: `sprint/SKILL.md` Step 5 gains the same close-out
   (`/wrapup REQ-xxx --close-out` in the serialized close-out worktree) after any
   orchestrator-performed merge, and Step 8c's ownership rule is stated there.
7. A close-out failure is visible in the sprint summary (`close-out: failed — <reason>`)
   and in `/status`, never silent.

## Actual Behavior

Both engines return `merged` immediately after `gh pr view` confirms the merge. No
lesson is captured, the spec stays `approved`, `pipeline-state.json` never records
completion. `/status` already surfaces the *state-file* half via BUG-193's stale-state
check (`status/SKILL.md:81-86`: `completed:false` with every repo `merged:true`); the
*knowledge* half is silent — nothing reports "this REQ wrote no lesson". `/wrapup`'s
"Active specs" grep (`wrapup/SKILL.md:16`) matches `approved` and `complete` alike, so it
lists the REQ either way. The legacy sprint summary's "Knowledge Captured" section
(`sprint/SKILL.md:283-286`) can only be empty or hand-written for these paths; the
workflow branch has no summary step at all.

## Environment

- Platform: macOS (Darwin 27.0.0)
- Version: adlc-toolkit 5.3.1 at `cb177bc`; `workflows/adlc-sprint.workflow.js`,
  `sprint/SKILL.md`, `agents/pipeline-runner.md` as of that commit

## Root Cause

(to be confirmed in /bugfix Phase 2) When REQ-474 wrote `wrapupAndMerge` (commit
`7995100`, 2026-05-30), the legacy runner's single-repo Phase 8 was itself merge-only,
and the engine's comment "mirrors the legacy pipeline-runner Phase-8 rule" (L1946–1947)
was accurate. Step 8b was added later by **BUG-193** (commit `1e4c223`, 2026-08-22),
whose resolution "made every actor that writes the terminal record write all five
fields" — but its Files Changed list does not include the workflow engine, which had
existed for three months, and the legacy orchestrator's Step 5 was never given the
close-out either. So this is not a port that was missed at authoring time; it is a
rule added afterwards to the solo path and the runner's self-merge path only. Because
the script has no shell of its own (every file write runs inside an `agent()` leaf), the
omission cost nothing at the time and nothing checked for it — the same "observation
that isn't load-bearing for control flow doesn't get built" shape as BUG-212.

## Resolution

To be fixed through `/bugfix` as its own PR covering **both engines** per the Expected
Behavior contract. **REQ-647** (lessons reach every pipeline phase) depends on this fix
for its workflow-engine *capture* path and states so in its BR-9; **REQ-648**'s
post-terminal emit leaf is independent of it.

## Files Changed

- (pending)
