---
parent: proceed
section: "Pipeline State Tracking"
---

# /proceed — Pipeline State Tracking

Companion to `proceed/SKILL.md` (REQ-661). Its "Pipeline State Tracking" section sends you here before Step 0. Read this file whole, then return to `proceed/SKILL.md` at "Run-outcome telemetry (REQ-648)". The Gate Protocol below is what every phase's **Gate** line applies.

## Pipeline State Tracking

**CRITICAL**: You MUST maintain a state file to track pipeline progress. This prevents phases from being skipped during long-running pipelines.

**State file location**: `.adlc/specs/REQ-xxx-*/pipeline-state.json`

**Schema**:
```json
{
  "req": "REQ-xxx",
  "branch": "feat/REQ-xxx-short-description",
  "startedAt": "2026-03-27T10:00:00Z",
  "completed": false,
  "currentPhase": 0,
  "completedPhases": [],
  "phaseHistory": [
    { "phase": 0, "name": "Create Worktree", "completedAt": "2026-03-27T10:01:00Z" }
  ],
  "repos": {
    "web": {
      "primary": true,
      "path": "/absolute/path/to/web",
      "worktree": "/absolute/path/to/web/.worktrees/REQ-xxx",
      "branch": "feat/REQ-xxx-short-description",
      "touched": true,
      "prUrl": null,
      "merged": false,
      "snapshotBranch": null,
      "snapshotPR": null
    },
    "api": {
      "primary": false,
      "path": "/absolute/path/to/api",
      "worktree": "/absolute/path/to/api/.worktrees/REQ-xxx",
      "branch": "feat/REQ-xxx-short-description",
      "touched": true,
      "prUrl": null,
      "merged": false,
      "snapshotBranch": null,
      "snapshotPR": null
    }
  },
  "mergeOrder": ["api", "web"],
  "phase4": {
    "currentTask": null,
    "completedTasks": [],
    "failedTasks": []
  },
  "conflictsResolved": [],
  "closeOut": { "status": "ok", "at": "2026-03-27T10:45:00Z" },
  "harness": { "version": "5.4.0", "sha": "c013262" },
  "validateAttempts": { "phase1": 1, "phase3": 2 },
  "verify": { "findings": [ { "severity": "Major", "file": "partials/forge.sh", "title": "…", "class": "unanchored-marker-regex", "lessonId": "LESSON-404", "fixed": true } ], "loops": 1, "consolidatedAt": "2026-03-27T10:36:00Z" },
  "lessonsWritten": ["LESSON-605"],
  "lane": {
    "initial": "lite",
    "current": "full",
    "forced": false,
    "skippedPhases": [1, 2, 3],
    "escalations": [ { "at": "2026-03-27T10:30:00Z", "phase": 5, "trigger": "blocked-path", "detail": "packages/domain/src/page.ts", "actor": "solo" } ],
    "overrides": []
  },
  "lessons": {
    "step0": { "query": { "components": ["adlc/proceed"], "domain": "adlc", "stack": [], "concerns": [], "tags": [] }, "lessons": [ { "id": "LESSON-604", "title": "…", "path": ".adlc/knowledge/lessons/LESSON-604-….md", "component": "adlc/proceed", "score": 11, "kind": "process" } ], "cap": 10, "retrievedAt": "2026-03-27T10:01:00Z" },
    "tasks": { "TASK-012": { "query": { "components": ["adlc/partials/forge", "adlc/partials"] }, "lessons": [ { "id": "LESSON-582", "newerThanSpec": true } ], "cap": 15, "retrievedAt": "2026-03-27T10:20:00Z" } },
    "phase5": { "query": { "components": ["adlc/proceed"] }, "lessons": [], "cap": 15, "retrievedAt": "2026-03-27T10:35:00Z" }
  }
}
```

`lane` is optional and additive (REQ-652): written at Step 0 only when the spec carries a `lane` key. Absent means the full lane, and a state file without it parses and runs unchanged. `initial` and `current` are the lane the run started on and the one it is on now; `skippedPhases` lists the phases a lite run recorded as skipped; `escalations` gets one entry per escalation, appended before the pipeline continues; `overrides` gets one entry, `{ at, phase, sha, triggers, pairs, actor }`, each time the operator answers halt #4 with "keep lite", where `pairs` are the exact `<trigger>: <detail>` strings the operator saw and `sha` the commit they saw them at; a later check halts again on any pair not listed or whose file changed since, and a `check-error` is never overridden. The spec frontmatter is the authority on the lane when a run starts, because state files are gitignored and machine-local; once the object exists, `lane.current` decides every lane branch of that run (each phase's "Lite lane" note included), so a lost escalation commit cannot put an escalated REQ back on the lite lane.

`lessons` is optional and additive (REQ-647): one LessonSet per retrieval point — `step0` at Step 0 item 7, `tasks["TASK-xxx"]` before each Phase-4 task, `phase5` before Phase 5 Step A — each `{ query, lessons[], cap, retrievedAt }` without the loaded text. `partials/lessons.sh` writes it, at the moment the set is computed, to the **primary repo path's** copy (`<repos[<primary>].path>/.adlc/specs/REQ-xxx-*/pipeline-state.json`, the same target as Step 8b's terminal record, because the worktree copy is deleted at teardown; when that spec directory does not exist on the primary checkout, the worktree's copy). Absent means "no lessons recorded"; `/status`, resume and both sprint engines read a file without it unchanged, and nothing reads it for control flow. Retrieval is never a gate: a `lessons: unavailable — <reason>` result is logged and the phase continues without lessons. Contract: `partials/lessons.md`.

`closeOut` is optional and additive (BUG-249): written by the Step 8b close-out
actor — `/wrapup --close-out` writes `status: "ok"`; the orchestrator that invoked it
writes `status: "failed", reason: "<why>"` when the mode exits non-zero. Absent means
"close-out not recorded"; nothing reads it for control flow. `/status` reports
`failed` under its Stale Pipeline State heading.

`harness`, `validateAttempts`, `verify` and `lessonsWritten` are optional and
additive (REQ-648): the facts the run-outcome line is derived from, each written
by code at the moment it occurs (**Run-outcome telemetry**, `proceed/phases-telemetry.md`), to the
primary-path copy, as `lessons` is. `harness` is the toolkit's `{version, sha}`
at Step 0, before any pull; `validateAttempts` the attempt counts at Phases 1 and
3; `verify` the consolidated Phase-5 findings, each with a `class` and a `fixed`
flag; `lessonsWritten` the `/wrapup` lesson outcome (recorded at the end of its Step 4) (`LESSON-` ids, or the string
`NO_ENTRY`). `lessons.acknowledged`, written by `ack-check --record`, belongs to
the same record. Absent means not recorded: the emitter prints `-` or `0` for
what it derives from a missing key, and nothing reads any of them for control
flow.

`status`, `approval` and `exec` are optional and additive (REQ-659): they exist only on a run of the `/sprint` exec engine, and absent means everything above behaves as it always did. `blockers`, `completed`, `currentPhase`, `completedPhases`, `phaseHistory`, `repos[*].merged`, `conflictsResolved` and `closeOut` keep their meanings. `status` is one of `running`, `awaiting_approval`, `approved`, `merging`, `merged`, `blocked`, `failed`, `rejected`, `stalled`. `approval` is `{ action, repos, prs, deploy, command, requestedAt, decision, decidedAt, decidedBy, channel, callerPid, reason, holdBehind }`: the model writes the first group as display data at the merge gate, and `action` is the closed value `merge`; the decision fields are a mirror of the orchestrator's ledger, which is outside every working copy and is the only record an approval is executed from. `exec` is `{ engine, harness, strategy, workingCopy, pid, closeOutPid, sessionId, startedAt, promptPath, logPath, stalledAt, trustMechanism, trustGrantedAt, trustRevokedAt, exitCode, exitClass, abortedBy, abortedAt }`, holding file names and never the run directory. While the harness process is alive the orchestrator never writes the working-copy file; its fields go to its own run directory and are merged into the primary-path copy after the process exits, and that copy is then authoritative. The engine's gate on a close-out's chore PR may also leave `closeOut.status` at `needs-review`, with the PR open.

The `repos` block is the canonical registry for this pipeline run. Every cd/commit/push/PR/merge operation reads the target repo's `path` or `worktree` from here — never from cwd inference. `touched: true` means at least one task targets this repo; untouched repos skip Phases 4–8. `mergeOrder` is the list of touched repo ids in the order Phase 8 will merge them (primary is always a member).

**Single-repo mode**: `repos` contains exactly one entry with `primary: true, touched: true`, and `mergeOrder` is `[that-one-id]`. All phase logic still reads from `repos` — there is no separate code path.

The `phase4` block tracks task-level progress during implementation so that a mid-Phase-4 context compression can resume from the exact task in progress rather than restarting the phase. `currentTask` holds the TASK-xxx ID being worked on right now; `completedTasks` holds IDs of tasks whose status is `complete` and whose commit has landed; `failedTasks` holds IDs that hit unrecoverable errors and were surfaced to the user. Other phases do not need sub-state.

The `conflictsResolved` array is the audit record for every merge or rebase conflict that was **resolved** during this run — by the runner, by the user on a halt, or by anyone else — one entry per event, appended **at the moment of resolution, before the pipeline continues** (BUG-212). It is not a control-flow input: nothing reads it to decide what to do next, which is exactly why it was never written before — the only record of a mid-run resolution was the runner's closing narrative, and a runner that said nothing left no trace. Entry schema is in `agents/pipeline-runner.md` ("Conflict resolution record"). **Additive and optional**: a state file without the key parses and processes unchanged, and absent reads as "no conflicts were resolved", never as a missing value. A *clean* auto-rebase is not a resolution and appends nothing; a `blocked` halt that was never resumed appends nothing either — the entry records that a conflict was *resolved*, not that one occurred (`blockers` already records that).

The `snapshotBranch` and `snapshotPR` fields on each `repos.<id>` entry are **deprecated as of REQ-380**. The skill no longer writes them; they remain in the schema for read-back compatibility with state files written between REQ-362 and REQ-380. A missing or null value is the expected state on all new runs. Snapshot promotion (the `staging → main` PR creation that previously ran in Phase 8a) is now handled out-of-band by a per-project workflow on staging-tip CI greenness; consult the project's CI configuration.

**Gate Protocol — follow exactly**:

1. **Initialize** the state file at the start of Step 0 with `currentPhase: 0, completedPhases: [], completed: false, repos: {...resolved from config...}, mergeOrder: [...], phase4: { currentTask: null, completedTasks: [], failedTasks: [] }`
2. **Before starting any phase**: read `pipeline-state.json`. Verify `currentPhase` equals the phase you're about to start AND the previous phase is in `completedPhases`. If either check fails, **STOP** — you skipped a phase. Go back and complete it.
3. **After completing any phase**: append the phase number to `completedPhases`, append an entry to `phaseHistory` with the completion timestamp, set `currentPhase` to the next phase number.
3a. **Skipped phases still pass through the gate (REQ-652 ADR-5)**: a lite run appends `1`, `2` and `3` to `completedPhases` at Step 0, each with a `phaseHistory` entry carrying `"skipped": "lite"`, so rule 2 holds unchanged at Phase 4. An escalation appends an `{ "event": "escalated" }` history entry, trims `completedPhases` to `[0]` and sets `currentPhase` to `1`; `phaseHistory` stays append-only.
4. **Phase 4 task-level writes**: When starting a task, set `phase4.currentTask` to its TASK-xxx ID. When its commit lands (in the task's target-repo worktree), append the ID to `phase4.completedTasks` and clear `currentTask`. On unrecoverable failure surfaced to the user, append to `phase4.failedTasks` instead.
5. **Worktree paths are immutable post-Step-0**: once Step 0 records `repos[<id>].worktree`, every subsequent phase (1–8) MUST read the path from state and MUST NOT re-derive it from cwd, the REQ id, or any naming convention. This applies on the happy path, not just on resume. (Step 0 itself reads cwd exactly once — at item 2 of Step 0 — to initialize the registry, then freezes the path into state; the prohibition starts from the moment Step 0 completes.)
5b. **Resume from interruption**: If the state file already exists when you start, read it and resume from `currentPhase`. Step 0's lane read still runs first (it is resume-safe): it reads `lane.current` from state rather than the spec, and it handles a `--full` passed on this invocation before the next phase starts. Trust `repos` as the source of truth for worktree paths. If `currentPhase` is 4 and `phase4.currentTask` is non-null, resume that specific task (re-read its file, use `repos[<task.repo>].worktree` for every git/file operation, re-check whether its commit already landed, continue or restart as appropriate) before moving to the next task in the dependency graph. Never replay tasks already in `completedTasks`.
6. **If context has been compressed**: re-read `pipeline-state.json` before doing anything and treat it as the source of truth for `currentPhase`, `repos`, and `phase4`. Do not rely on memory of which phase, task, or repo you're in.
7. **Per-repo writes during Phases 6–8**: when a PR is created, write its URL to `repos[id].prUrl`. When a PR merges, set `repos[id].merged = true`. These writes let a mid-Phase-8 interruption resume merges in order without double-merging.
8. **On completion**: After Phase 8 (Wrapup) finishes, set `"completed": true` in the state file.

Each phase in `proceed/SKILL.md` has a one-line **Gate** reminder. The full protocol above applies to every gate.
