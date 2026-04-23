---
name: proceed
description: End-to-end ADLC pipeline that takes a requirement from spec through to deployed. Takes a REQ number as argument and runs validate → fix → architect → fix → implement → verify (reflect + review) → create PR → wrapup (merge, deploy, knowledge capture). Use when the user says "proceed", "proceed with REQ-xxx", "run the pipeline", "take REQ-xxx to completion", "implement REQ-xxx end to end", or wants to advance a drafted requirement all the way through to deployment in one shot.
---

# Proceed — Full ADLC Pipeline

You are an autonomous ADLC orchestrator. Given a requirement number (REQ-xxx), you drive it from validated spec all the way to a pull request — validating at each gate, fixing issues automatically, and only pausing when you're stuck or need human input.

## Execution Mode

This skill supports two modes:

1. **Main conversation mode** (default): Dispatches formal agents (defined in `~/.claude/agents/`) for parallelism at Phase 4 (task implementation) and Phase 5 (verify). Use this mode when running `/proceed` directly.
2. **Subagent mode** (when running as a `pipeline-runner` agent inside `/sprint`): Execute ALL phases sequentially in-context. Do NOT dispatch sub-agents. At Phase 4, implement tasks one at a time. At Phase 5, run the reflector + reviewer checklists sequentially in your own context using the criteria from the agent definitions. Subagents cannot spawn other subagents.

You are in subagent mode if you were explicitly told so in your launch prompt.

## Autonomous Execution Contract

`/proceed` is an **autonomous orchestrator**. It is designed to run end-to-end without human input. The skill has exactly **four** legitimate halt points; every other instruction below is a log step, not a pause:

1. **Validation fails 3 times at any gate** (Phase 1 or Phase 3) — surface blockers.
2. **Reflector surfaces user-facing questions** (Phase 5, Step C item 4) — surface as a numbered list and wait.
3. **Canary deploy fails** (Phase 7.5) — surface the failure and wait for direction.
4. **Merge conflicts during rebase** (Phase 8 / wrapup) — surface conflicts and wait.

For everything else — including every **End-of-phase log** block below, every agent dispatch, every commit, every PR creation, every CI wait — you **continue immediately** to the next step without asking the user. Prompt only for tool-level permissions on truly destructive operations (these are governed by `.claude/settings.json`, not this skill).

**Writing logs vs asking questions**: when the skill says "report X" or "log Y", emit a one-line status line to the conversation and continue. Do NOT phrase it as a question or wait for acknowledgment. A bad example: "Spec validated — shall I proceed to Phase 2?" A good example: "Spec validated. Moving to Phase 2."

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Arguments

The user provides a requirement ID, e.g., `/proceed REQ-023` or `/proceed 23`.

- Normalize to `REQ-xxx` format (zero-pad to 3 digits if needed)
- Locate the spec at `.adlc/specs/REQ-xxx-*/requirement.md`
- If the spec doesn't exist, stop and tell the user to run `/spec` first

## Repository Configuration (single-repo vs cross-repo)

Some requirements touch one repo; others (e.g., an admin control plane for an iOS feature that spans a mobile app, an API, and a web app) touch multiple repos. `/proceed` supports both.

**"Primary" is per-REQ, not a fixed role.** The primary repo for a given REQ is simply **the repo where you invoked `/proceed` from** — that repo's `.adlc/` holds the spec, tasks, and `pipeline-state.json` for this REQ. A different REQ can originate in a different repo; that REQ's primary is the other repo. Every repo that might host a REQ needs its own `.adlc/` structure (from `/init`) and its own `.adlc/config.yml` so it can act as primary when a REQ starts there.

**Single-repo mode** (the invoking repo's config has no siblings, or no config at all): existing behavior — one worktree, one PR, one merge. All phases run against the invoking repo. Used for work that's scoped to one repo.

**Cross-repo mode** (the invoking repo's config lists siblings): the invoking repo is primary for this REQ. Sibling repos are registered by id → path. `/proceed` creates a worktree in each touched repo, routes tasks by their `repo:` frontmatter field, opens one PR per repo, and merges in `merge_order`.

**Config schema** (`.adlc/config.yml`, present in every repo that can originate a REQ):

```yaml
repos:
  # Self — mark the current repo as primary. Path is implicit (it's this repo).
  # Each repo's config marks ITSELF as primary. The configs across repos end
  # up being mirror images of each other; that's expected and correct.
  admin-app:
    primary: true
  # Siblings — other repos this one might coordinate with. Path is relative
  # to THIS repo's root, or absolute. Every sibling must be cloned locally.
  admin-api:
    path: ../admin-api
  ios-app:
    path: ../ios-app

# Merge order for Phase 8 when this repo is primary. If omitted, defaults to
# the order repos appear above. Only touched repos (those with tasks in the
# current REQ) are merged; untouched ones are skipped.
merge_order:
  - admin-api
  - admin-app
  - ios-app
```

**Rules**:
- In each repo's own config, exactly one entry — that repo itself — has `primary: true`. Sibling entries describe other repos.
- Every repo that can originate a REQ needs `/init` run in it AND its own `.adlc/config.yml`. Repos that will only ever participate as siblings (never originate REQs) technically don't need a config, but it's cheap insurance — configure them anyway so any of them can host a REQ later.
- Task frontmatter must include a `repo:` field naming one of the invoking repo's configured repo ids. A task without `repo:` defaults to the invoking (primary-for-this-REQ) repo.
- "Touched repos" for a REQ = the set of distinct `repo:` values across its tasks.
- If the invoking repo's config has only itself (no siblings), or the file is absent, behave as single-repo.
- Sibling repo paths must exist and be git repositories. Fail fast in Step 0 if any are missing.

**Terminology used below**:
- **Primary repo** — for this REQ, the repo `/proceed` was invoked from. Hosts `.adlc/`, spec, state file. Always participates.
- **Touched repo** — any repo (primary or sibling) that has at least one task in this REQ.
- **Repo worktree** — `<repo-path>/.worktrees/REQ-xxx` for each touched repo, on branch `feat/REQ-xxx-short-description` (same branch name across repos).

## The Pipeline

Execute these phases in order. Each phase has a validation gate — if validation fails, fix the issues and re-validate. Loop up to 3 times per gate; if still failing after 3 attempts, stop and present the remaining issues to the user.

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
    "admin-app": {
      "primary": true,
      "path": "/absolute/path/to/admin-app",
      "worktree": "/absolute/path/to/admin-app/.worktrees/REQ-xxx",
      "branch": "feat/REQ-xxx-short-description",
      "touched": true,
      "prUrl": null,
      "merged": false
    },
    "admin-api": {
      "primary": false,
      "path": "/absolute/path/to/admin-api",
      "worktree": "/absolute/path/to/admin-api/.worktrees/REQ-xxx",
      "branch": "feat/REQ-xxx-short-description",
      "touched": true,
      "prUrl": null,
      "merged": false
    }
  },
  "mergeOrder": ["admin-api", "admin-app"],
  "phase4": {
    "currentTask": null,
    "completedTasks": [],
    "failedTasks": []
  }
}
```

The `repos` block is the canonical registry for this pipeline run. Every cd/commit/push/PR/merge operation reads the target repo's `path` or `worktree` from here — never from cwd inference. `touched: true` means at least one task targets this repo; untouched repos skip Phases 4–8. `mergeOrder` is the list of touched repo ids in the order Phase 8 will merge them (primary is always a member).

**Single-repo mode**: `repos` contains exactly one entry with `primary: true, touched: true`, and `mergeOrder` is `[that-one-id]`. All phase logic still reads from `repos` — there is no separate code path.

The `phase4` block tracks task-level progress during implementation so that a mid-Phase-4 context compression can resume from the exact task in progress rather than restarting the phase. `currentTask` holds the TASK-xxx ID being worked on right now; `completedTasks` holds IDs of tasks whose status is `complete` and whose commit has landed; `failedTasks` holds IDs that hit unrecoverable errors and were surfaced to the user. Other phases do not need sub-state.

**Gate Protocol — follow exactly**:

1. **Initialize** the state file at the start of Step 0 with `currentPhase: 0, completedPhases: [], completed: false, repos: {...resolved from config...}, mergeOrder: [...], phase4: { currentTask: null, completedTasks: [], failedTasks: [] }`
2. **Before starting any phase**: read `pipeline-state.json`. Verify `currentPhase` equals the phase you're about to start AND the previous phase is in `completedPhases`. If either check fails, **STOP** — you skipped a phase. Go back and complete it.
3. **After completing any phase**: append the phase number to `completedPhases`, append an entry to `phaseHistory` with the completion timestamp, set `currentPhase` to the next phase number.
4. **Phase 4 task-level writes**: When starting a task, set `phase4.currentTask` to its TASK-xxx ID. When its commit lands (in the task's target-repo worktree), append the ID to `phase4.completedTasks` and clear `currentTask`. On unrecoverable failure surfaced to the user, append to `phase4.failedTasks` instead.
5. **Resume from interruption**: If the state file already exists when you start, read it and resume from `currentPhase`. Trust `repos` as the source of truth for worktree paths — do not re-derive from cwd. If `currentPhase` is 4 and `phase4.currentTask` is non-null, resume that specific task (re-read its file, cd into its repo's worktree, re-check whether its commit already landed, continue or restart as appropriate) before moving to the next task in the dependency graph. Never replay tasks already in `completedTasks`.
6. **If context has been compressed**: re-read `pipeline-state.json` before doing anything and treat it as the source of truth for `currentPhase`, `repos`, and `phase4`. Do not rely on memory of which phase, task, or repo you're in.
7. **Per-repo writes during Phases 6–8**: when a PR is created, write its URL to `repos[id].prUrl`. When a PR merges, set `repos[id].merged = true`. These writes let a mid-Phase-8 interruption resume merges in order without double-merging.
8. **On completion**: After Phase 8 (Wrapup) finishes, set `"completed": true` in the state file.

Each phase below has a one-line **Gate** reminder. The full protocol above applies to every gate.

---

### Step 0: Resolve Repos + Create Worktrees + Preflight + Load Shared Context (ALWAYS FIRST)

**Before doing anything else**, resolve the repository set, isolate each touched repo in a git worktree, and prime the shared context so subskills don't re-read the same files:

1. **Preflight** — verify all prerequisite files exist in the **primary** repo (stop with a clear message if any are missing):
   - `.adlc/context/project-overview.md` — run `/init` if missing
   - `.adlc/context/architecture.md` — run `/init` if missing
   - `.adlc/context/conventions.md` — run `/init` if missing
   - `.adlc/specs/REQ-xxx-*/requirement.md` — run `/spec` if missing
2. **Resolve repo registry**:
   - Read `.adlc/config.yml` if it exists. If absent or has no `repos` block, use single-repo mode: the registry is `{ <cwd-repo-id>: { primary: true, path: <cwd>, touched: true } }` where the repo id is the basename of the cwd.
   - In cross-repo mode: the primary entry's `path` is cwd. Resolve each sibling's `path` to an absolute path (relative paths are relative to the primary repo root). Verify each path exists and is a git repo (`git -C <path> rev-parse --git-dir`). If any sibling is missing, stop with a clear error listing the missing repos.
3. **Determine touched repos** (best-effort at Step 0; confirmed after Phase 2):
   - If tasks already exist under `.adlc/specs/REQ-xxx-*/tasks/`, read each task's `repo:` field to compute the touched set.
   - If tasks don't exist yet (fresh pipeline), assume every configured repo is potentially touched and create worktrees in all of them. Post-Phase-2, untouched repos will be marked `touched: false` and their worktrees removed.
   - The primary is always touched (even if no primary tasks — it hosts the spec and state file).
4. Ensure main is up to date in each touched repo:
   ```bash
   git -C <repo-path> checkout main && git -C <repo-path> pull
   ```
5. Create a worktree in each touched repo on the same branch name:
   ```bash
   git -C <repo-path> worktree add .worktrees/REQ-xxx feat/REQ-xxx-short-description
   ```
   Record each repo's absolute `worktree` path and `branch` in the state file's `repos` block.
6. Change your working directory to the **primary repo's worktree** — orchestration (state file reads/writes, spec edits, PR coordination) happens there. Task implementation in Phase 4 will `cd` into the target repo's worktree per task.
7. **Load shared context ONCE from the primary** — use the Read tool to load these into conversation context so every subskill can reference them without re-reading:
   - `.adlc/context/architecture.md`
   - `.adlc/context/conventions.md`
   - `.adlc/context/project-overview.md`
   - `.adlc/specs/REQ-xxx-*/requirement.md`
   - `.adlc/config.yml` (if present)
8. **Initialize `pipeline-state.json`** in the primary's spec directory with `currentPhase: 0, completedPhases: [], completed: false, startedAt: <now>, repos: {...resolved registry with absolute paths, worktrees, branches, touched flags...}, mergeOrder: [...from config.yml or declared order, filtered to touched repos...], phase4: { currentTask: null, completedTasks: [], failedTasks: [] }`. If the file already exists, read it and resume from `currentPhase` (and from `phase4.currentTask` if mid-Phase-4) — do NOT recreate worktrees that already exist.
9. When the pipeline completes (all PRs merged in Phase 8), clean up every worktree:
   ```bash
   git -C <repo-path> worktree remove .worktrees/REQ-xxx
   ```

**Preflight verified** — when you invoke subskills in later phases, they may skip their own prerequisite checks (already validated here) AND they may skip re-reading `architecture.md` / `conventions.md` / `project-overview.md` (already in context). Treat the Step 0 loads as authoritative for the rest of the pipeline.

**After completing Step 0**: Update `pipeline-state.json` — add `0` to `completedPhases`, add Step 0 to `phaseHistory`, set `currentPhase` to `1`.

---

### Phase 1: Validate the Requirement Spec

**Gate**: `currentPhase` must be `1`. After completion: append `1`, set `currentPhase=2`.

**Goal**: Ensure the requirement is complete and well-formed before designing architecture.

1. Invoke the `/validate` skill with the REQ ID
2. If **APPROVED**: set requirement status to `approved` and move to Phase 2
3. If **NEEDS REVISION**: fix all FAIL items, then re-invoke `/validate` (up to 3 loops)

**End-of-phase log**: Emit one line — "Spec validated and approved." Continue to Phase 2 immediately; do not wait for user acknowledgment.

---

### Phase 2: Architect & Break Into Tasks

**Gate**: `currentPhase` must be `2`. After completion: append `2`, set `currentPhase=3`.

**Goal**: Design the technical approach and create implementation tasks.

1. Invoke the `/architect` skill with the REQ ID. In cross-repo mode, also pass the configured repo ids (from `pipeline-state.json` `repos`) and require that every generated task's frontmatter include a `repo:` field naming one of those ids.
2. This handles: reading context, designing architecture, creating task files with dependencies, and updating requirement status.
3. **Reconcile touched repos**: after `/architect` returns, scan all task files for distinct `repo:` values. Update `pipeline-state.json`:
   - For each configured repo with at least one task, ensure `touched: true`.
   - For each configured repo with no tasks (and not primary), set `touched: false` and remove its worktree: `git -C <repo-path> worktree remove .worktrees/REQ-xxx`.
   - Rebuild `mergeOrder` filtered to touched repos, preserving the configured order.
4. **Backfill missing `repo:` fields**: if any task omits `repo:`, default it to the primary repo id and write the field into its frontmatter. In single-repo mode this is the only valid value and can be set silently.

**End-of-phase log**: Emit a one-paragraph summary of the architecture approach, the task dependency graph, and the final touched-repo set with task counts per repo. Continue to Phase 3 immediately.

---

### Phase 3: Validate Architecture & Tasks

**Gate**: `currentPhase` must be `3`. After completion: append `3`, set `currentPhase=4`.

**Goal**: Ensure the architecture and task breakdown are solid before implementation.

1. Invoke the `/validate` skill with the REQ ID (it will auto-detect the architecture+tasks phase)
2. If **APPROVED**: move to Phase 4
3. If **NEEDS REVISION**: fix all FAIL items, then re-invoke `/validate` (up to 3 loops)

**End-of-phase log**: Emit one line — "Architecture and tasks validated." Continue to Phase 4 immediately.

---

### Phase 4: Implement

**Gate**: `currentPhase` must be `4`. After completion: append `4`, set `currentPhase=5`.

**Goal**: Execute all tasks, producing working code with tests. Each task runs in the worktree of its target repo (from `repo:` frontmatter).

1. Build the dependency graph from task frontmatter. Dependencies may cross repos — a frontend task can depend on a backend task.
2. Identify independent tasks (no unmet dependencies) — these can run in parallel, regardless of which repo they target.
3. On resume: read `pipeline-state.json`. Skip any task in `phase4.completedTasks`. If `phase4.currentTask` is non-null, start there (not at the dependency root).
4. For each task (or batch of independent tasks):
   - Write `phase4.currentTask` to the TASK-xxx ID before starting work
   - Read the task file for requirements, files to modify, ACs, technical notes, and `repo:` field
   - Resolve the target worktree: `repos[<task.repo>].worktree` from `pipeline-state.json`. All file reads/writes, tests, and git operations for this task happen inside that worktree.
   - Implement the changes following project conventions (from `.adlc/context/conventions.md`)
   - Write tests as specified in the task
   - Run the **target repo's** test suite (not the primary's, unless they're the same repo) to verify nothing is broken
   - Mark the task status as `complete` in its frontmatter (task files live in the primary's `.adlc/specs/REQ-xxx-*/tasks/`)
   - Commit inside the target worktree with message format: `feat(scope): description [TASK-xxx]`
   - After the commit lands, append the TASK-xxx ID to `phase4.completedTasks` and clear `phase4.currentTask`
5. If a task hits an unrecoverable failure surfaced to the user: append its ID to `phase4.failedTasks`, clear `phase4.currentTask`, and stop the phase.

**Main conversation mode** — parallel execution:
- Group tasks into tiers based on the cross-repo dependency graph
- Tier 0: tasks with no dependencies — launch a **task-implementer** agent for each
- Tier 1: tasks depending only on Tier 0 — launch after Tier 0 completes
- Continue until all tiers complete
- Each task-implementer agent (defined in `~/.claude/agents/`) receives: the full task file, conventions.md, architecture.md, **and the absolute path of the target repo's worktree** (from `repos[<task.repo>].worktree`). The agent must operate exclusively inside that worktree.

**Subagent mode** — sequential execution:
- Execute tasks one at a time in cross-repo dependency order
- Implement each task directly in your own context (do not dispatch agents), cd-ing into the target worktree for each task

**End-of-phase log**: After each tier completes, emit one line listing finished tasks with their target repos (e.g., `TASK-003 [admin-api] ✓`) and any task-level failures (failed tasks are also written to `phase4.failedTasks`). Do not pause between tiers; advance to the next tier as soon as its dependencies are met.

---

### Phase 5: Verify (Reflect + Review in Parallel)

**Gate**: `currentPhase` must be `5`. After completion: append `5`, set `currentPhase=6`.

**Goal**: Self-assess AND multi-agent review the implementation, then fix all findings in a single consolidated pass.

**Gather diffs per repo** (prerequisite): for each touched repo, compute the diff inside its worktree (`git -C <worktree> diff main...HEAD` plus the list of changed files). The reviewers receive per-repo diffs + file lists, plus the cross-repo architecture.md so they can reason about contracts spanning repos.

**Main conversation mode** — parallel agents:

**Step A — Single-gate parallel dispatch**. This whole step is ONE gate. In cross-repo mode, dispatch **6 agents × N touched repos** — all in a **single assistant message**. In single-repo mode, dispatch **6 agents** in a single message as before. Do NOT report findings, do NOT pause, do NOT log progress between agent returns — wait until all have returned, then consolidate in Step B.

The six agents match the dimensions covered by `/review` (correctness, quality, architecture, test coverage, security) plus the reflector self-assessment:

1. **reflector** agent — provide REQ-xxx, the repo id, the worktree path, changed files, diff, conventions.md, architecture.md. Tell it: "Report findings only. The parent pipeline will apply fixes."
2. **correctness-reviewer** agent — repo id, worktree path, changed files, diff, conventions.md. "Report findings only. Do not apply fixes."
3. **quality-reviewer** agent — same inputs. "Report findings only. Do not apply fixes."
4. **architecture-reviewer** agent — repo id, worktree path, changed files, diff, architecture.md, **plus a summary of the other touched repos' changes** (so it can flag cross-repo contract breaks). "Report findings only. Do not apply fixes."
5. **test-auditor** agent — repo id, worktree path, changed files, diff, conventions.md. "Audit test coverage only for the diff under review. Report findings only. Do not apply fixes."
6. **security-auditor** agent — repo id, worktree path, changed files, diff, conventions.md. "Audit security posture only for the diff under review. Report findings only. Do not apply fixes."

**Subagent mode** — sequential inline review:
For each touched repo, run the reflector checklist, then correctness, quality, architecture (with cross-repo context), test-auditor, and security-auditor checklists sequentially in your own context. Use the criteria from the agent definitions in `~/.claude/agents/`. Do NOT dispatch sub-agents.

**Step B — Consolidate**: When all agents return (or all checklists complete in subagent mode), dedupe overlapping findings **within each repo** and also flag cross-repo issues (e.g., API contract drift between admin-api and admin-web). Produce a single ranked list by severity, tagging each finding with the repo id it applies to.

**Step C — Fix in one pass**:
1. **Critical + must-fix Major** (bugs, security, convention violations, missing tests): fix immediately in the finding's target repo worktree, run that repo's test suite after each related cluster of fixes, commit inside that worktree with `fix(scope): address verify finding [REQ-xxx]`.
2. **Should-fix Minor** (code quality, naming): fix unless doing so would be a significant refactor — note those as follow-ups.
3. **Nit / observation**: fix trivial ones inline, skip the rest.
4. **User-facing questions from reflector**: if any, surface them to the user as a numbered list and wait for answers before continuing.

**Step D — Re-verify (conditional)**: Re-run ONLY the 5 reviewer agents (not reflector) if Critical or must-fix Major items were fixed — up to 1 confirmation loop. Skip if only minor fixes were applied. Scope re-verify to the (repo, dimension) pairs that had fixes: e.g., if correctness fixes landed only in admin-api, rerun correctness-reviewer for admin-api only. In subagent mode, re-run the corresponding reviewer checklists inline.

**End-of-phase log**: Emit the combined verify summary across repos — per-repo findings, dedupe count, how many fixed, any deferred. If reflector surfaced user-facing questions, halt here (legitimate halt #2). Otherwise continue to Phase 6.

---

### Phase 6: Create Pull Request(s)

**Gate**: `currentPhase` must be `6`. After completion: append `6`, set `currentPhase=7`.

**Goal**: Package the work into reviewable PRs — one PR per touched repo.

1. For each touched repo:
   - Inside that repo's worktree, ensure all changes are committed and push the feature branch: `git -C <worktree> push -u origin feat/REQ-xxx-short-description`
2. Set the requirement status to `complete` in its frontmatter (primary repo only).
3. Create a PR **in each touched repo** using `gh pr create` (invoke via `gh -R <owner/repo>` or by running `gh` from inside each worktree). In cross-repo mode, create the PR for the primary repo **last** so the primary PR body can link to all sibling PRs.
   - **Title (per repo)**: Short description referencing the REQ, tagged with the repo id when cross-repo (e.g., `feat(admin-api): outfit endpoint [REQ-023]`).
   - **Body (per repo)**:
     ```
     ## Summary
     [2-3 bullet points describing what was built in THIS repo]

     ## Requirement
     REQ-xxx: [requirement title]
     Primary repo: <primary-repo-id>

     ## Related PRs (cross-repo)
     [Populated for siblings and also in the primary once its PR is created last.
      Omit entirely in single-repo mode.]
     - admin-api: <url>
     - admin-web: <url>

     ## Tasks Completed (this repo)
     - [x] TASK-001: [title]
     - [x] TASK-002: [title]

     ## Architecture Decisions
     [Key ADRs or "No architectural changes needed"]

     ## Test Coverage
     [Summary of tests added/modified in THIS repo]

     ## Reflection Notes
     [Key observations from the reflect phase — risks, assumptions, follow-ups]

     ## Merge Order
     [Only when cross-repo. List the mergeOrder from pipeline-state.json so
      reviewers know which PR merges first.]
     ```
4. After each PR is created, write its URL to `repos[<id>].prUrl` in `pipeline-state.json`.
5. After the last PR is created, go back and edit sibling PRs' bodies (`gh pr edit`) to add the cross-repo "Related PRs" section now that every URL is known.
6. Report all PR URLs to the user, grouped by repo and in `mergeOrder` sequence.

---

### Phase 7: PR Cleanup & CI

**Gate**: `currentPhase` must be `7`. After completion: append `7`, set `currentPhase=8` (or `7.5` if canary will run).

**Goal**: Lightweight sanity check on each PR — the full code review already happened in Phase 5. Do NOT re-run `/review`.

Do all the steps below **for every touched repo's PR**:

1. Review the full PR diff using `gh pr diff <prUrl>` (use the URL stored in `repos[<id>].prUrl`).
2. Check for:
   - Stray debug logs, TODOs, or commented-out code
   - Files that shouldn't have been included (secrets, generated files, unrelated changes)
   - Commit message consistency and cleanliness
   - That the PR description accurately reflects the changes
   - Cross-repo consistency: if a sibling PR changes an API contract, verify this PR's corresponding consumer/producer code matches
3. If issues are found:
   - Fix inside the owning repo's worktree, commit with message: `fix(scope): PR cleanup [REQ-xxx]`
   - Push that worktree's branch: `git -C <worktree> push`
4. If CI checks are configured, verify each PR passes: `gh pr checks <prUrl>`. Wait for in-flight checks before moving on.

**End-of-phase log**: Emit one line per PR — "<repo-id>: clean, CI green" — followed by an aggregate "All N PRs ready for merge" or list any remaining concerns. Continue to Phase 7.5 (or Phase 8) immediately.

---

### Phase 7.5: Canary Deploy (Optional)

**Gate**: `7` must be in `completedPhases`. After completion: append `7.5`, set `currentPhase=8`. This phase is **optional** — only run it if the requirement's frontmatter includes `deployable: true`, OR if no `deployable` field exists and the changes include deployable API or web service code in any touched repo. Skip when `deployable: false` or for iOS-only, documentation-only, or infrastructure-only changes.

**Goal**: Deploy each affected service to a canary revision with zero traffic, run smoke tests, and promote only on success — ensuring every deploy works before merging.

1. Determine which touched repos map to deployable services (check each repo's conventions for deploy markers — e.g., a `Dockerfile`, a `service.yaml`, or a repo-level `deployable: true` flag in `.adlc/config.yml`).
2. For each affected service, invoke the `/canary` skill from that repo's worktree. Canaries can run in parallel across repos when services don't share infrastructure; run sequentially when they do.
3. If **all** canaries pass: proceed to Phase 8.
4. If any canary fails: stop and present the failure to the user (listing which repo failed, which passed). Options:
   - Fix the issue in the failing repo's worktree and re-run `/canary` for that repo only
   - Skip canary and proceed to merge (user must explicitly confirm)
   - Abort the pipeline

**End-of-phase log**: Emit canary results — one line per service with repo id, revision, and smoke test pass/fail. On all-pass, continue to Phase 8 immediately. On any fail, halt (legitimate halt #3).

---

### Phase 8: Wrapup

**Gate**: `currentPhase` must be `8` and `7` (or `7.5`) must be in `completedPhases`. After completion: append `8`, set `"completed": true`.

**Goal**: Merge, deploy, capture knowledge, and close out the feature.

**Cross-repo merge sequencing**:

1. Walk `mergeOrder` from `pipeline-state.json`. For each repo id in order:
   - Skip if `repos[<id>].merged == true` (already merged — recovering from an interrupted run).
   - Merge that repo's PR (`gh pr merge <prUrl> --squash` or the project's configured merge strategy).
   - Wait for the merge to land, then set `repos[<id>].merged = true` in state.
   - If the next repo's PR was opened against `main` and depends on the just-merged changes being present, trigger a rebase/retarget before merging it. When siblings were developed in parallel worktrees against the same pre-REQ main, this is usually a no-op — but surface any auto-merge failure to the user as a conflict halt (legitimate halt #4).
2. After all PRs are merged, run `/wrapup` with the REQ ID from the primary repo. In cross-repo mode, pass the list of touched repos so `/wrapup` can:
   - Update ADLC artifacts (spec, decisions, knowledge) in the primary
   - Trigger deploys for each deployable touched repo
   - Emit a ship summary spanning all repos
3. Remove the worktree in each touched repo: `git -C <repo-path> worktree remove .worktrees/REQ-xxx`.
4. Update `pipeline-state.json` with `"completed": true`.
5. The pipeline is now complete.

**End-of-phase log**: Emit the ship summary from wrapup including per-repo merge confirmations and deployment status. Pipeline complete.

---

## Error Handling

- **Test failures during implementation**: Stop the current task, diagnose the failure, fix it inside the task's target-repo worktree, and re-run tests before continuing. If you can't fix it after 2 attempts, pause and ask the user.
- **Validation stuck after 3 loops**: Present the remaining FAIL items and ask the user how to proceed (fix manually, skip validation, or abort).
- **Missing context files**: If `.adlc/context/` files don't exist in the primary repo, stop and tell the user to run `/init` first. Do not proceed without context files.
- **Missing sibling repo**: If `.adlc/config.yml` references a sibling whose path doesn't exist or isn't a git repo, stop at Step 0 and list the missing repos. The user must clone or fix paths before retrying.
- **Task with unknown `repo:` value**: If a task frontmatter names a repo id not in the registry, stop Phase 4 and surface the mismatch — either the config or the task is wrong.
- **Merge conflicts**: If any feature branch has conflicts with its base branch — during Phase 7 rebase or Phase 8 merge — stop and ask the user how to resolve. In cross-repo mode, state which repo conflicted; earlier repos in `mergeOrder` may have already merged (see `repos[<id>].merged`), so the user can resume mid-sequence rather than re-doing completed merges.
- **Partial merge recovery**: If the pipeline is interrupted mid-Phase-8, resume by reading `pipeline-state.json` — the merge loop walks `mergeOrder` and skips any repo where `merged: true`.

## Prerequisites

Verified by Phase 0 Preflight — see Step 0 above.

## What This Skill Does NOT Do

- It does not create the initial spec — run `/spec` first
