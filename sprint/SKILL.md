---
name: sprint
description: Parallel pipeline orchestrator — launch multiple /proceed sessions concurrently across REQs, monitor progress, and report status. Use when the user says "sprint", "run these REQs in parallel", "proceed with all approved REQs", "launch a sprint", or wants to advance multiple requirements simultaneously.
argument-hint: REQ IDs to sprint (e.g., "REQ-091 REQ-092 REQ-093") or "all"; add --workflow to run on the Dynamic Workflows engine
---

# /sprint — Parallel Pipeline Orchestrator

You are a sprint orchestrator that launches multiple `/proceed` pipelines in parallel, monitors their progress, and reports a unified dashboard. Each pipeline runs in its own worktree with full isolation.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Current directory: !`pwd`
- Existing worktrees: !`git worktree list 2>/dev/null || echo "Not a git repo"`
- Available specs: !`ls .adlc/specs/ 2>/dev/null || echo "No specs found"`
- Pipeline states: !`find .adlc/specs -name "pipeline-state.json" -print 2>/dev/null | while read -r f; do echo "$f"; cat "$f"; done || echo "No active pipelines"`

## Input

Target REQs: $ARGUMENTS

## Prerequisites

Before proceeding, verify:
1. `.adlc/context/project-overview.md` exists — run `/init` if missing
2. `.adlc/context/architecture.md` exists — run `/init` if missing
3. `.adlc/context/conventions.md` exists — run `/init` if missing

## Instructions

### Step 0: Select the Sprint Engine

`/sprint` has two engines behind one command (ADR-1):

- **`workflow`** — the deterministic `adlc-sprint` Dynamic Workflows script, which restores each REQ's internal fan-out (explore trio, Phase-5 review panel) *while* keeping cross-REQ concurrency.
- **`legacy`** — the background `pipeline-runner` engine documented in Steps 1–6 below. Always available; the hard fallback.

**Decide which engine to run:**

1. **Detect Dynamic Workflows availability**: the engine is *available* only if the `Workflow` tool is invocable in this session. Dynamic Workflows is research-preview and plan-gated, so it can be absent (headless/cron runs, non-qualifying plans). If you cannot invoke the `Workflow` tool, treat it as unavailable.
2. **Read the `--workflow` flag** from `$ARGUMENTS`. Strip the flag token from the argument list before any REQ-ID parsing downstream, so it is never mistaken for a REQ id.
3. **Select the engine**: choose `workflow` only when *available* **AND** (`--workflow` was passed **OR** the workflow engine has graduated to the default). Otherwise choose `legacy` — with no behavior change from today's `/sprint`.

If the user passed `--workflow` but the `Workflow` tool is unavailable, say so explicitly and fall back to `legacy` rather than failing.

**If the engine is `workflow`:**

1. **Resolve the script path** with the standard two-level fallback (ADR-2): prefer the consumer-vendored copy, fall back to the toolkit copy.
   - First choice: `.adlc/workflows/adlc-sprint.workflow.js` (present after the consumer ran `/init`).
   - Fallback: `~/.claude/skills/workflows/adlc-sprint.workflow.js` (always present via the skills symlink).
   - Use whichever path exists; if neither exists, report the missing script and fall back to `legacy`.
2. **Invoke the `Workflow` tool** with the resolved script path and the documented args. The script itself is the orchestration engine (ADR-3) — this dispatcher is the only place the `Workflow` tool is invoked:
   ```
   Workflow({
     scriptPath: <resolved path from step 1>,
     args: {
       reqs: <normalized REQ-id list from $ARGUMENTS, with --workflow stripped>,
       integrationBranch: <resolved integration branch for the primary repo: "staging" in two-branch repos, else "main">,
       answers: {}
     }
   })
   ```
   `args.reqs` is the same REQ-id list the legacy Step 1 would normalize (`REQ-xxx` form; expand `all` to every eligible spec). `args.integrationBranch` is a hint — the workflow's Phase-0 agent re-resolves it per repo against `origin/<branch>` and never hardcodes `main`. `args.answers` is `{}` on a first run.
3. **The run returns `{results}` — one TERMINAL value per REQ.** Each result carries a `state` discriminant: `merged`, `pr-ready`, `blocked`, or `failed` (the workflow never throws on a halt — a halt is a *returned* `{state:'blocked', …}` value, so the run completes and the other REQs are unaffected). Inspect every result:
   - **`merged` / `pr-ready` / `failed`** — report them as-is. A `failed` REQ has no user-answerable question; surface its `reason`/`detail` and move on (do not attempt a resume).
   - **`blocked`** — this is a halt awaiting a human answer (a 3×-failed validation, a reflector `userFacing` question, or a merge conflict). Surface it to the user and **WAIT** for a reply — same "blocked → surface → re-engage" flow as the legacy engine's Step 4.6, but driven off the returned value rather than a state file. For each blocked REQ, print its `reason` and its `detail.questions` (when present) as a numbered list, e.g.:
     ```
     BLOCKER: REQ-091 is blocked (reflector-questions). The pipeline needs your answer before it can advance:
       1. <detail.questions[0]>
       2. <detail.questions[1]>
     Reply with your guidance and I'll resume only REQ-091 from its halt.
     ```
     Other REQs (merged/pr-ready/failed) are already terminal — report them in the same turn so the user sees the full picture, not just the blocker.
4. **Resume on the user's reply (`resumeFromRunId`).** When the user answers a blocked REQ, relaunch the SAME script with the prior run's id and the answer threaded through `args.answers[<REQ-id>]`:
   ```
   Workflow({
     scriptPath: <same resolved path>,
     resumeFromRunId: <the runId of the prior run>,
     args: {
       reqs: <same REQ-id list>,
       integrationBranch: <same hint>,
       answers: { '<blocked-REQ-id>': '<the user's reply>' }
     }
   })
   ```
   Keep `reqs` and `integrationBranch` identical to the prior run, and put the reply under the blocked REQ's id (answer multiple blocked REQs by adding more keys). The engine references `args.answers` **only** inside the blocked REQ's halt-prone agent prompts, so on resume only that REQ diverges from the journal cache and advances past its halt: every untouched REQ — and every already-`merged` REQ — replays from cache with **no re-executed side effects** (no recreated worktree, no re-implemented task, no double-merge). Re-inspect the returned `{results}` exactly as in step 3, repeating the surface→answer→resume loop until no REQ is `blocked`. (Steps 1–6 below do **not** apply to the workflow engine — they are the legacy engine.)

5. **Orchestrator `blocker-cleared` auto-resume (REQ-485 BR-8 — primary engine per OQ-1 default).** A REQ held by a Phase-8 trial-merge conflict against an ahead REQ is **not** resumed by a user reply — it is resumed by the **orchestrator** once it merges that blocker *within the run*. This is a distinct resume channel from `args.answers` (a user answer): the script threads an orchestrator-generated `blocker-cleared` signal for the held REQ. The held workflow REQ does NOT self-resume — it already returned `{state:'blocked'}` and the post-merge unblock pass (in `adlc-sprint.workflow.js`) drives its resume by relaunching the SAME script via `resumeFromRunId` carrying the cleared signal in `args` (e.g. `args.blockerCleared[<held-REQ-id>] = <blocker-id>`, parallel to `args.answers`). Like `args.answers`, the signal is injected **surgically** — only into the held REQ's Phase-8 / halt-prone path — so every untouched and already-`merged` REQ replays byte-identical from the journal cache (no recreated worktree, no double-merge). The unblock pass rebases the held REQ's own worktree first; a clean rebase resumes it (it re-runs the now-passing trial-merge gate and merges, clearing its `blockers` entry — BR-11), a conflicting rebase aborts non-mutatingly and re-halts `{state:'blocked'}` with the materialized conflict files (BR-4), retry-bounded (BR-10). Held REQs on one blocker resume in REQ-483's deterministic order, one at a time (BR-6). See the "Self-healing serialization" section below for the cross-engine behavior contract.

**Else (the engine is `legacy`)** — run Steps 1–6 below exactly as written. This is the existing background-`pipeline-runner` orchestration, unchanged.

### Step 1: Identify Sprint REQs

1. If given specific REQ IDs (e.g., `REQ-091 REQ-092`), normalize each to `REQ-xxx` format
2. If given `all`, scan `.adlc/specs/REQ-*/requirement.md` for all specs with `status: approved` or `status: draft`
3. If no argument, scan for all `status: approved` specs
4. Exclude any REQ that already has `pipeline-state.json` with `"completed": true`
5. Exclude any REQ that already has an active pipeline-runner — i.e., a worktree on its `feat/REQ-xxx-...` branch AND a `pipeline-state.json` whose `completed` is `false` and whose phase has advanced recently. (A stale same-branch worktree from a crashed prior run is **not** an active pipeline; it falls through to Step 2 item 4 below, which surfaces it with a cleanup recipe rather than silently excluding the REQ.)

If no eligible REQs found, report "No eligible REQs for sprint" and stop.

### Step 2: Validate Sprint Eligibility

**Precondition (LESSON-036):** each pipeline-runner branches its worktree from the integration branch (`origin/<integration-branch>` — `staging` in two-branch repos, else `main`), so a spec that exists only on an unmerged PR/feature branch is invisible to the pipeline even though it's on disk locally. `git fetch origin` first, then run the eligibility checks **against `origin/<integration-branch>`** (e.g. `git ls-tree -r --name-only origin/<integration-branch> | grep REQ-xxx`), not just the local working tree. If a freshly-`/spec`'d REQ isn't on the integration branch yet, mark it ineligible with issue `spec not on <integration-branch> — land its spec PR first`.

For each REQ, verify (against `origin/<integration-branch>` per the precondition above):
1. The spec file exists at `.adlc/specs/REQ-xxx-*/requirement.md`
2. Read the spec — confirm it has: Description, Acceptance Criteria (at least 1), and no unresolved Questions marked as blockers
3. Context files exist (project-overview, architecture, conventions)
4. **Worktree path collision check**: parse `git worktree list --porcelain` in the primary repo and intersect each candidate's target path `<repo-path>/.worktrees/REQ-xxx` against registered worktrees. If the path is already registered to a different branch (i.e., not the candidate's own `feat/REQ-xxx-...` branch), mark the REQ ineligible with the issue text `worktree path in use by branch <name>`. The surfaced message MUST name the cleanup commands the user can run to clear the stale worktree. **Quote the substituted `<branch>` and `<path>` values with single quotes** so a copy-paste cannot execute injected shell from a hostile branch name:
   ```
   git -C '<repo>' worktree remove '<path>'      # add --force if the worktree has uncommitted work you intend to discard
   git -C '<repo>' branch -D '<branch>'          # -D already forces deletion regardless of merge status; verify with `git log main..'<branch>'` first if you may have unmerged work to keep
   ```
   **Scope (OQ-2 default)**: this collision check scans only the **primary repo**. Sibling-repo collisions are caught at `/proceed` Step 0 by the per-repo `git worktree add` validation gate, so do not extend this pre-flight to siblings without a deliberate decision — see REQ-263 architecture.md ("Cross-repo behavior") for why.

Report a pre-flight checklist:
```
## Sprint Pre-Flight

| REQ | Title | Status | Eligible | Issue |
|-----|-------|--------|----------|-------|
| REQ-091 | Feature A | approved | Yes | — |
| REQ-092 | Feature B | draft | No | Status is draft, not approved |
| REQ-093 | Feature C | approved | Yes | — |
| REQ-094 | Feature D | approved | No | worktree path in use by branch feat/REQ-094-old-attempt |
```

Remove ineligible REQs. If no REQs remain, stop.

**In-Flight (cross-session) manifest (advisory, REQ-482).** Before confirming the lineup, build the cross-session manifest **once for the whole batch** (not per REQ — BR-14) and display it as a separate "In-Flight (cross-session)" section, so you can see other sessions' work on the shared remote and any coarse overlaps. Step 2 already ran `git fetch origin`, so invoke `/manifest` prefixing the same shell call with the hand-off vars `MANIFEST_SELF="REQ-a REQ-b …" MANIFEST_SKIP_FETCH=1` — `MANIFEST_SELF` lists **all** the batch's REQ ids (space-separated) so every batch member is marked self, and `MANIFEST_SKIP_FETCH=1` avoids a redundant fetch. Render the in-flight table plus any coarse `component`/`domain` overlaps among in-flight REQs. This is **advisory only** — it does NOT change eligibility, ordering, or scheduling, and a manifest-build failure is ignored (BR-7, BR-8, BR-9). It is separate from, and does not alter, the worktree-collision eligibility check above.

**Max concurrent pipelines**: 5. If more than 5 are eligible, prioritize by:
1. REQs explicitly listed in arguments (first priority)
2. REQs with `status: approved` over `status: draft`
3. Lower REQ numbers first (older specs)

Ask the user to confirm the sprint lineup before proceeding.

### Step 3: Launch Parallel Pipelines

For each eligible REQ, launch a **pipeline-runner** agent (defined in `~/.claude/agents/`) using the Agent tool with `run_in_background: true`.

**Agent prompt for each REQ** (the orchestrator computes `<absolute-path>` as `<repo-path>/.worktrees/REQ-xxx` and substitutes it verbatim):

> **BEFORE dispatching, substitute `<absolute-path>` and `REQ-xxx` and `[current repo path]` with the actual computed values.** Do **NOT** emit any of these placeholders literally — `/proceed` Step 0 will use the captured WORKTREE PATH verbatim, and a literal `<absolute-path>` would cause `git worktree add` to fail with an unhelpful error. The agent definition for `pipeline-runner` (canonical source for worktree-isolation rules) takes precedence over the in-prompt reminder below if they ever diverge.

```
WORKTREE PATH (mandatory): <absolute-path>

Run the /proceed skill for REQ-xxx in the repository at [current repo path].
You are in SUBAGENT MODE — execute all phases sequentially, do not dispatch sub-agents.
This is part of a parallel sprint — other REQs are running concurrently in separate worktrees.
Use the WORKTREE PATH above verbatim for `git worktree add` in Phase 0. All later phases MUST read the worktree path from `pipeline-state.json.repos[<id>].worktree` (set by Phase 0 from this contract line) — do not re-derive it. The only sanctioned operation against the parent repo path is `gh pr merge` in Phase 8 single-repo topology; every other read/write/cd belongs inside the worktree. (See `agents/pipeline-runner.md` "Worktree Isolation" section for the canonical rules.)
Follow all /proceed phases (0-8) exactly as documented.
If you encounter a blocker that requires human input, update pipeline-state.json with the blocker details and stop gracefully.
Phase 8 merge ownership follows REQ topology: single-repo REQs — you own the merge and report `merged`. Cross-repo REQs — stop after Phase 7 and report `pr-ready` so the orchestrator can sequence merges per `mergeOrder`. Your final report MUST lead with one of `{merged, pr-ready, blocked, failed}`.
```

The `WORKTREE PATH (mandatory): <absolute-path>` line is a contract fixed in REQ-263 architecture.md — **exactly one space after `WORKTREE PATH` (before the opening parenthesis), exactly one space after `(mandatory):`**, POSIX absolute path, no quoting, no trailing slash, line stands alone. `/proceed` Step 0 parses it with regex `^WORKTREE PATH \(mandatory\): (.+)$` and uses the **first** match if the prompt accidentally contains multiple. Do not reformat. The orchestrator MUST emit this line for every dispatched pipeline-runner; it is the producer side of the dispatch-line contract (BR-1, BR-7).

Launch all agents in a single message to maximize parallelism. Each pipeline-runner agent:
- Runs in subagent mode (all phases sequential, no nested sub-agent dispatch)
- Works in its own worktree (the absolute path declared in the `WORKTREE PATH (mandatory):` line — typically `<repo-path>/.worktrees/REQ-xxx` by convention) — isolation is handled by `/proceed` Phase 0
- Maintains its own `pipeline-state.json`
- Operates independently — failure in one does not affect others

### Step 4: Monitor Progress (Notification-Driven)

Background `pipeline-runner` agents send an automatic notification when they finish (complete, blocked, or failed). The orchestrator does **not** actively poll on a timer — attempting to `sleep`/loop mid-turn would block the conversation without any benefit. Instead, the orchestrator reacts to agent-completion notifications and refreshes state whenever the user takes a turn.

1. **Immediately after launch**: read every `pipeline-state.json` that was just initialized and print the initial sprint dashboard (see below). This confirms all agents launched and shows their starting phase.

2. **When an agent-completion notification arrives** (the platform delivers one per background agent): re-read every `pipeline-state.json` under `.adlc/specs/REQ-*/` and update the dashboard. Only redraw when state has actually changed — don't spam the user with identical dashboards.

   **Verify the agent's terminal-state claim before accepting it.** A pipeline-runner's final report MUST lead with one of `{merged, pr-ready, blocked, failed}` (see `~/.claude/agents/pipeline-runner.md` Terminal state contract). The orchestrator MUST NOT trust the claim at face value:
   - For `merged` and `pr-ready` claims: run `gh pr view <prUrl> --json state,mergedAt` against every touched-repo PR before updating the dashboard.
     - If the agent claimed `merged` but the PR is `OPEN`: treat the claim as `pr-ready` and merge the PR per Step 5.
     - If the agent claimed `pr-ready` but the PR is `MERGED`: just move on (agent was conservative, no harm done).
     - If the PR is `CLOSED` (not merged) or in any other unexpected state: surface as a blocker.
   - For `blocked` and `failed`: read `pipeline-state.json.blockers` / `notes` and surface to the user per the existing blocker-handling flow (Step 4.6).
   - **Untagged claims** (e.g., a vague "Pipeline complete" without one of the four tags) are protocol violations. Treat as `blocked` and surface to the user — do not assume the agent finished cleanly.

3. **When the user takes a turn during the sprint** (asks a question, issues a command): re-read all `pipeline-state.json` files first, so any answer reflects current pipeline state rather than a stale snapshot from launch.

4. **Dashboard format**:

```
## Sprint Dashboard — [timestamp]

| REQ | Phase | Status | Duration | Last Update |
|-----|-------|--------|----------|-------------|
| REQ-091 | 4/8 Implement | Running | 12m | Tier 1 tasks in progress |
| REQ-092 | 5/8 Verify | Running | 18m | 2 findings, fixing |
| REQ-093 | 2/8 Architect | Running | 5m | Creating tasks |

Completed: 0/3 | Blocked: 0 | Running: 3
```

5. **Stall detection**: stalls are detected on dashboard refreshes (triggered by notifications or user turns), not on a timer. If a pipeline's `pipeline-state.json` has not advanced between two consecutive refreshes AND the gap between refreshes is >10 minutes of wall clock, flag it as potentially stalled in the next dashboard and check whether its background agent is still alive.

6. **Blocker handling**: if a pipeline's state file reports a blocker (e.g. `phase4.failedTasks` is non-empty, or validation has failed 3 times), surface it immediately on the next refresh:
   ```
   BLOCKER: REQ-091 is stuck at Phase 5 (Verify) — validation failed 3 times.
   Remaining issues: [list from pipeline-state.json]
   Options: (1) Fix manually, (2) Skip validation, (3) Abort this REQ
   ```
   Wait for the user's choice before taking action on that pipeline. Other pipelines continue running.

### Step 5: Handle Merge Sequencing

**Default policy: merge as each pipeline completes.** When a pipeline finishes Phase 7 and is marked merge-ready, merge it immediately — don't wait for the batch. Faster feedback, less idle time, and the rebase cost on subsequent pipelines is paid as they reach merge-ready anyway (each one runs its own `/wrapup` Step 2 rebase-onto-main guard, so main drift is handled automatically).

**Ordering enforcement (REQ-483).** When `/manifest`'s verdict (Step 2 pre-flight) shows footprint overlaps in the batch, merge the overlapping REQs in its **deterministic order** (earliest-published first, lower REQ tiebreak — BR-8) instead of as-they-complete, and gate **each** merge: `git -C <worktree> fetch origin <integrationBranch>` (refresh the tip), source `partials/trial-merge.sh`, then `adlc_trial_merge "<worktree>" origin/<integrationBranch>` before `gh pr merge`. **rc=1** → hold that REQ (`blocked`, surfaced for rebase); **rc=0** → merge; **rc=2/3** → `failed` (setup error, not a conflict). For overlapping **single-repo** REQs (whose pipeline-runners would otherwise self-merge as they complete), the orchestrator MUST hold the later-ranked one until the earlier merges — do not let both self-merge, or both could pass a stale-tip gate and collide at merge. Non-overlapping REQs still merge as they complete (parallel-by-default). Serializes **merges**, never implementation; computed in orchestrator code, not delegated (BR-10).

**Who actually performs the merge depends on REQ topology** (see `~/.claude/agents/pipeline-runner.md` Phase 8):

- **Single-repo REQ** (one touched repo in `pipeline-state.repos`): the pipeline-runner agent already merged its own PR in its Phase 8 and reports `merged`. The orchestrator's job here is to **verify** (per Step 4 verify gate) and move on — do NOT re-merge. If verification shows the PR is still `OPEN` despite the `merged` claim, fall through to the cross-repo flow below and merge it yourself.
- **Cross-repo REQ** (multiple touched repos): the pipeline-runner stops at Phase 7 and reports `pr-ready`. The orchestrator owns merge sequencing and walks the per-REQ `mergeOrder` itself.

The sequential flow when the orchestrator is the merge actor (cross-repo, or single-repo fallback after a failed agent merge):
1. Merge the PR: `gh pr merge --squash --delete-branch`
2. Pull main: `git checkout main && git pull`
3. Move on — other pipelines keep running in the background

**Post-merge unblock pass (REQ-485 — self-healing serialization).** REQ-483 holds a REQ with a `blocked` terminal when its pre-merge trial-merge conflicts (rc=1) against an ahead REQ. Today that held REQ is surfaced for a human to rebase + resume. For an unattended `/sprint` batch, **immediately after the orchestrator confirms REQ-A merged** (the merge above landed AND `repos[A].merged = true` was written), run an unblock pass so the batch self-heals — in place of parking the held REQ for a human:

1. **Find held REQs (BR-2, BR-11 anchor).** Scan every other in-flight REQ's `pipeline-state.json` for a *still-present* `blockers` entry with `blockedBy == A`. Consider ONLY REQs whose `blockers` entry exists — a cleared entry means already-resumed-and-merged, so it is never re-processed (the BR-6 idempotency anchor). With nothing newly merged, this scan finds nothing and the pass is a no-op (deterministic + idempotent).
2. **Order + serialize (BR-6).** If more than one REQ is held on A, order them by REQ-483's deterministic rule (earliest-published PR first, lower REQ tiebreak) and process them **one at a time** — the held REQs may themselves overlap, so resuming two concurrently would re-introduce the merge race REQ-483 eliminated.
3. **Degrade-safe pre-check (BR-7).** For each held REQ, read its worktree path from its own `pipeline-state.json.repos[<id>].worktree` and its `currentPhase`. If the worktree has been torn down OR `currentPhase` is unrecorded, **skip with a one-line advisory** `manual resume needed for REQ-x (worktree gone / phase unrecorded)` — never an error or a batch crash.
4. **Rebase ONLY the held REQ's own worktree (BR-2, BR-5).** Fetch and rebase in the held REQ's worktree — mutate nothing else (never REQ-A's branch/PR, never a third REQ's worktree):
   ```sh
   # held=<held REQ id>, hw=<its repos[<id>].worktree>, ib=<integrationBranch>
   git -C "$hw" fetch origin "$ib" >/dev/null 2>&1
   if git -C "$hw" rebase "origin/$ib" >/dev/null 2>&1; then
     echo "rebase-clean: $held"          # → step 5 (auto-resume)
   else
     git -C "$hw" rebase --abort >/dev/null 2>&1 || :   # non-mutating restore
     echo "rebase-conflict: $held"       # → step 6 (re-halt)
   fi
   ```
   (Write any list-iteration over held REQs split-free — `printf '%s\n' "$held_ids" | while read -r held`, every path quoted — so it behaves identically under the executor shell, LESSON-329.)
5. **Clean rebase → auto-resume (BR-3).** Re-dispatch a fresh `pipeline-runner` for the held REQ exactly as in Step 3, using its existing worktree (its `pipeline-state.json` already records `currentPhase`, so the runner resumes from there). The runner re-runs the now-passing Phase-8 trial-merge gate and proceeds to merge; on that merge it sets `repos[<id>].merged = true` AND clears its `blockers` entry (BR-11). Treat this re-dispatched runner like any other Step 3 pipeline (verify its terminal claim per Step 4). **Legacy-engine degrade (OQ-1 default / BR-7):** the common halt is the Phase-8 pre-merge gate, and a fresh runner from `currentPhase` resumes it cleanly — so the common case auto-resolves. If a held REQ halted mid-phase in a way the legacy engine cannot cleanly re-dispatch from, degrade to the surface-to-human advisory rather than forcing a resume.
6. **Conflicting rebase → re-halt, never auto-resolve (BR-4, BR-10).** The `rebase --abort` already restored the worktree. Increment the held REQ's `blockers.rebaseAttempts`. If it is **below** the retry bound (default 1, overridable via `.adlc/config.yml` key `auto_rebase_max_attempts`; missing → 1), re-halt with `holdState: "held"` carrying the NOW-materialized conflict files and surface a human-resolution prompt. If it is **at/above** the bound, mark `holdState: "needs-manual-rebase"`, set `resolvedBlocker: A`, switch `blockedBy` to a `manual`/`self` sentinel (so this scan never re-picks it up — REQ-485 OQ-6), and surface for manual handling. Never auto-resolve, `-X` force, or "merge anyway" (ethos #6). BR-10 counts attempts **per blocker-merged event**.

**Blocker-failed release (REQ-485 OQ-5 / ADR-8).** A blocker can also end **`failed`/abandoned** within the run — its PR will never merge, so no merge event fires the pass above and a REQ held *solely* on it would sit `blocked` to batch-end. When a REQ-A terminal is `failed`, for every held REQ whose ONLY live `blockedBy` is A (no other live blocker), treat the dead blocker as cleared and run the SAME rebase+resume path (steps 3–6 above) — its ordering constraint has dissolved. A REQ with *other* live blockers stays held. This is the in-run analogue of REQ-483's stale-PR safety. (Place this check where Step 4.6 / the merge loop observes a REQ's terminal state.)

**Batch mode (only when N ≥ 3)**: when the sprint has 3 or more pipelines AND the orchestrator has strong prior knowledge that their diffs overlap (same files, same modules), switch to batching:
1. Wait for all pipelines to reach merge-ready state (Phase 7 complete, blocked, or stopped)
2. Sort merge-ready pipelines by:
   - Independent changes first (no overlapping files), then
   - Lower REQ numbers first (tie-breaker)
3. Merge sequentially from the sorted list:
   - Merge the first PR
   - Pull main
   - For each subsequent pipeline, its `/wrapup` Step 2 will re-fetch and rebase onto the new main before merging
   - If any rebase hits conflicts, skip that pipeline and surface to the user — continue with the rest

Batch mode is the exception, not the rule. If you're uncertain whether diffs overlap, default to merging as each completes.

### Step 6: Sprint Summary

After all pipelines complete (or are stopped), produce a sprint summary:

```
## Sprint Summary — [date]

### Completed
| REQ | Title | PR | Duration | Tasks | Lessons |
|-----|-------|----|----------|-------|---------|
| REQ-091 | Feature A | #42 | 25m | 4/4 | 2 |
| REQ-093 | Feature C | #44 | 18m | 3/3 | 1 |

### Blocked / Stopped
| REQ | Title | Phase | Blocker |
|-----|-------|-------|---------|
| REQ-092 | Feature B | 5/9 | Test failure in auth middleware |

### Knowledge Captured
- LESSON-048: [title from REQ-091 wrapup]
- LESSON-049: [title from REQ-091 wrapup]
- LESSON-050: [title from REQ-093 wrapup]

### Metrics
- Total duration: 32 minutes
- REQs shipped: 2/3
- Tasks completed: 7
- Lines changed: +420 / -85
- Lessons captured: 3
```

## Self-healing serialization (REQ-485)

REQ-483 made a `/sprint` batch **enforce** merge ordering: a REQ whose pre-merge trial-merge conflicts (rc=1) against an ahead REQ is held with a `blocked` terminal. REQ-485 makes the batch **self-heal** that hold, so an unattended batch ("launch it and walk away") does not sit idle behind a human nudge. The contract, across both engines:

- **The trigger is blocker-merged → rebase-held-REQ → resume (BR-1, BR-2, BR-3).** Immediately after the orchestrator merges REQ-A *within the run*, it runs the post-merge unblock pass (legacy: Step 5; workflow: `unblockHeldReqs` after the merge barrier) over every REQ held with a still-present `blockers` entry where `blockedBy == A`. Each held REQ's OWN worktree is rebased onto the refreshed integration branch; a **clean** rebase resumes it from its recorded `currentPhase` (re-running the now-passing trial-merge gate, which proceeds to merge).
- **A conflicting rebase is never auto-resolved (BR-4).** The rebase is `--abort`ed (worktree restored, non-mutating) and the REQ is re-halted carrying the NOW-materialized conflict files, surfaced for human resolution. Nothing is force-merged or "merged anyway" (ethos #6).
- **Only the held REQ's own branch/worktree is mutated (BR-5).** The pass never touches the blocker's branch/PR (already merged) or any third REQ's worktree. Ordering is derived from merge events, never asserted by mutation.
- **Deterministic, idempotent, serialized (BR-6).** With nothing newly merged the pass is a no-op. Multiple REQs held on one blocker unblock in REQ-483's deterministic order (earliest-published PR, lower REQ tiebreak) and are processed **one at a time** — held REQs may themselves overlap, so concurrent resume would reintroduce the merge race. The pass considers ONLY REQs whose `blockers` entry is still present (cleared on a successful resume — BR-11), which is the idempotency anchor.
- **Degrade-safe (BR-7).** A held REQ whose worktree has been torn down or whose `currentPhase` is unrecorded is skipped with a `manual resume needed for REQ-x` advisory — never an error or a batch crash. Per OQ-1, the **workflow engine is the primary auto-resume path**; the **legacy engine** auto-resumes the common Phase-8-gate halt by re-dispatching a pipeline-runner from `currentPhase` and degrades to surface-to-human for any halt it cannot cleanly re-dispatch.
- **Retry-bounded (BR-10).** A persistently-conflicting rebase stops after `auto_rebase_max_attempts` (default 1, overridable in `.adlc/config.yml`) and is marked `needs-manual-rebase` — not auto-re-triggered by future merges. Attempts are counted per blocker-merged event.
- **Blocker-failed release (OQ-5).** If a blocker ends `failed`/abandoned within the run (its PR will never merge), a REQ held *solely* on it is released and re-attempted on the same rebase+resume path — its ordering constraint has dissolved. A REQ with other live blockers stays held.

**Scope (v1).** Within-`/sprint`-run only (BR-9): the orchestrator merged the blocker itself, so "blocker-merged" is a known local event — there is **no cross-session watch/poll**. A blocker merged by a *different* session stays manual. **Solo `/proceed`** (not under `/sprint`) is unchanged — manual resume, because the human is present (BR-1). **Rebase conflicts are always human-resolved** (BR-4) — the machinery only detects and restores, never resolves.

## Error Handling

- **Agent crash**: If a background agent stops unexpectedly, check its last `pipeline-state.json` state. Report the failure and offer to relaunch from the last completed phase.
- **Worktree conflict**: If a worktree already exists for a REQ, check if there's an active pipeline. If abandoned (no recent state update), offer to clean up and restart.
- **Resource exhaustion**: If the system is slow or agents are timing out, reduce concurrency — pause lower-priority pipelines and let active ones finish first.
- **Merge conflict during sequencing**: Stop the conflicting pipeline, surface the conflict to the user, and continue merging other completed pipelines.

## Cross-Repo Sprints

`/sprint` supports sprints that include cross-repo REQs. Cross-repo handling is delegated entirely to each `/proceed` pipeline — `/sprint` itself still originates every pipeline from the same repo (the one it was invoked in), but each `/proceed` reads `.adlc/config.yml` and may create worktrees in sibling repos as needed.

**Collision avoidance**: concurrent cross-repo REQs that share a sibling each create their own worktree at `<sibling-path>/.worktrees/REQ-xxx` (different REQ numbers → different paths → no collision). If two REQs accidentally try to use the same REQ number, `git worktree add` fails loudly on the second — surface that in the pre-flight report.

**Pre-flight check for cross-repo sprints**: for each REQ whose frontmatter or tasks declare sibling repos (via `repo:` values from `.adlc/config.yml`), verify in Step 2:
- Every declared sibling is present on disk and is a git repo
- Each touched sibling's `main` is clean or has no conflicting branch

**Sibling-repo worktree collisions are deferred to `/proceed` Step 0** (per REQ-263 architecture.md "Cross-repo behavior" + OQ-2 default). The `/sprint` Step 2 collision check (item 4 above) intentionally scans **only the primary repo**; sibling collisions are caught by `/proceed` Step 0's per-repo `git worktree add` validation gate, which runs the same fail-loud halt with the same error format. Do not extend Step 2 to scan siblings without a deliberate decision — it would duplicate the validation logic ADR-1 was designed to keep in one place.

If any check fails, mark the REQ ineligible with a specific issue in the pre-flight table. The user may choose to clean up and retry, or exclude that REQ from the sprint.

**Dashboard**: the sprint dashboard's per-REQ row should show "primary repo → N touched" when a REQ is cross-repo (e.g., `api → 3 touched`) so the user sees fleet-wide activity at a glance, not just local work.

**Merge sequencing**: cross-repo REQs produce multiple PRs, merged in the REQ's own `mergeOrder` (by its `/proceed` Phase 8). `/sprint` still merges REQs "as each pipeline completes" — a completed cross-repo pipeline means all its per-repo PRs have landed. Only the next REQ's pipelines need to re-fetch main.

## What This Skill Does NOT Do

- It does not create specs — run `/spec` first for each REQ
- It does not replace `/proceed` — it orchestrates multiple `/proceed` sessions
- It does not originate REQs from different primary repos in a single sprint — every REQ in one `/sprint` invocation is assumed to originate from the repo the command was run in. Cross-repo REQs whose primary is a sibling must be sprinted from that sibling instead.
- It does not require the workflow engine. Dynamic Workflows is a research-preview, plan-gated capability that can be absent (headless/cron runs, non-qualifying plans), so the workflow engine is never assumed present: `/sprint` runs the workflow engine only when the `Workflow` tool is invocable **and** the run opts in (`--workflow`, or once it graduates to default), and otherwise runs the legacy background-runner engine — the always-available, behavior-unchanged fallback. A `--workflow` request with the tool unavailable does not fail the sprint; it falls back to legacy with an explicit notice.
- It does not make the two engines diverge in outcome. The workflow engine only changes *how* the pipeline is dispatched (restored per-REQ fan-out); it does not add, skip, or reorder pipeline phases relative to the legacy engine, and it does not gate the legacy engine behind the workflow engine.
- It does not auto-resume a REQ blocked by a **cross-session** merge (REQ-485 BR-9). Self-healing serialization triggers only on a blocker this `/sprint` run merged itself — a known local event. There is no cross-session watch/poll; a blocker merged by a different session stays manual until a human resumes it.
- It does not auto-resume a **solo `/proceed`** (not under `/sprint`) that hit a trial-merge block (REQ-485 BR-1). The human is present in that path, so the held REQ keeps today's manual rebase-and-resume behavior; only an orchestrated `/sprint` batch self-heals.
- It does not auto-resolve a rebase conflict (REQ-485 BR-4). A conflicting auto-rebase is `--abort`ed and re-halted for human resolution; the machinery only detects and restores, never resolves, forces, or merges-anyway.
