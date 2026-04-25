---
id: REQ-263
title: "Enforce per-REQ unique worktree paths in /sprint dispatch and /proceed Phase 0"
status: draft
deployable: false
created: 2026-04-24
updated: 2026-04-24
component: "adlc/sprint"
domain: "adlc"
stack: ["claude-code", "git-worktree", "bash"]
concerns: ["concurrency", "data-loss", "developer-experience", "reliability"]
tags: ["sprint", "proceed", "worktrees", "parallel-pipelines", "race-condition", "dispatch-contract"]
---

## Description

Eliminate the worktree-collision class of bug observed in a recent multi-tier `/sprint` run, where parallel `pipeline-runner` agents stepped on each other's worktrees and destroyed two REQ specs. See [LESSON-003](../../knowledge/lessons/LESSON-003-sprint-worktree-collision.md) for the full incident and root-cause analysis.

The fix has three coordinated parts:

1. **`/sprint` dispatch contract** — the orchestrator computes each pipeline-runner's absolute worktree path and declares it in the launch prompt. Agents stop re-deriving.
2. **`/proceed` Phase 0 validation gate** — before `git worktree add`, validate the declared path against `git worktree list --porcelain` and fail loud on conflict. Never silently reuse.
3. **`/sprint` Step 2 pre-flight collision check** — refuse to dispatch when the target `.worktrees/REQ-xxx` is already owned by another live worktree.

A complementary `pipeline-runner` agent-definition update tightens the worktree-isolation contract so the agent can't accidentally write to the parent repo's working tree.

**Why this REQ exists.** The user manually patched the symptoms during the live sprint by editing each agent's prompt to include explicit worktree paths — Tier 2 and Tier 3 ran clean with that change. This REQ codifies that workaround so the next sprint operator doesn't re-encounter the bug.

**Scope is deliberately narrow.** This is a defensive-engineering REQ on the toolkit's orchestration layer. No new features; no behavior change for users running `/sprint` correctly today. Strictly: parallel pipelines that would have collided now either don't collide or fail with a clear error before any damage is done.

## System Model

_This is a tooling-defensiveness REQ. The "entities" are the orchestration skill files; the "events" are dispatch and worktree-creation operations._

### Entities (files modified)

| File | Purpose | Change |
|---|---|---|
| `sprint/SKILL.md` | Sprint orchestrator skill | Step 2 adds collision pre-flight; Step 3 dispatch prompt declares per-REQ absolute worktree path |
| `proceed/SKILL.md` | Per-REQ pipeline skill | Step 0 reads orchestrator-declared path (with fallback); validates against `git worktree list` before `git worktree add`; treats path as immutable for the rest of the run |
| `agents/pipeline-runner.md` | Pipeline-runner subagent definition | New "Worktree isolation" section: cd into worktree first; absolute paths or `git -C` for every Bash call; no writes to parent working tree |

### Events

| Event | Trigger | Behavior change |
|---|---|---|
| `sprint_preflight` | `/sprint` Step 2 runs | New collision check against `git worktree list`; ineligible REQs flagged with reason |
| `sprint_dispatch` | `/sprint` Step 3 launches a pipeline-runner | Prompt includes `WORKTREE PATH (mandatory): <abs-path>` line |
| `proceed_phase0` | `/proceed` Step 0 runs | Read orchestrator-declared path → validate against `git worktree list` → fail loud on conflict → write to `pipeline-state.json.repos[<id>].worktree` as the immutable source of truth |
| `proceed_phase_n_>0` | Any later phase needs the worktree path | Read from `pipeline-state.json.repos[<id>].worktree`; never re-derive from cwd |

### Permissions

_Not applicable — internal toolkit changes only._

## Business Rules

- [ ] BR-1: **Orchestrator declares, agent obeys.** When `/sprint` dispatches a pipeline-runner, the launch prompt MUST include a line of the form `WORKTREE PATH (mandatory): <absolute-path>`. The pipeline-runner MUST use that exact path; it MUST NOT re-derive a worktree path from cwd or any other inferred source.
- [ ] BR-2: **Backward-compatible fallback.** When `/proceed` is invoked directly (not via `/sprint`) and no `WORKTREE PATH` declaration is present, Phase 0 falls back to the existing derivation (`<repo-path>/.worktrees/REQ-xxx`). This keeps single-pipeline `/proceed` invocations unchanged.
- [ ] BR-3: **Validation is mandatory in Phase 0.** Whether the path was declared or derived, before `git worktree add`, `/proceed` MUST run `git -C <repo> worktree list --porcelain`, parse it, and fail loud if the target path is already registered to a different branch. Error message must name the conflicting branch and the REQ that owns it (best-effort, by reading any sibling `pipeline-state.json` in the conflicting worktree). This is a hard halt — no silent retry.
- [ ] BR-4: **State is the source of truth, post-Step-0.** Once `/proceed` Phase 0 records the worktree path in `pipeline-state.json.repos[<id>].worktree`, every later phase MUST read the path from state. No phase may re-derive a worktree path from cwd or recompute it from `<repo>/.worktrees/REQ-xxx`. This includes resume-from-compression paths.
- [ ] BR-5: **Pre-flight collision check.** `/sprint` Step 2 MUST run `git worktree list --porcelain` for each touched repo and flag any REQ whose target `.worktrees/REQ-xxx` is already in use by a different branch. Cross-repo REQs check the path in every touched repo. Flagged REQs appear in the pre-flight table with reason `"worktree path in use by branch <name>"` and are excluded from the dispatch unless the user explicitly cleans them up and retries.
- [ ] BR-6: **Worktree isolation contract for pipeline-runner.** The `pipeline-runner` agent definition MUST add an "Worktree isolation" section stating: (a) the agent's first action after reading state is `cd <worktree-from-state>`; (b) every Bash call uses absolute paths or `git -C <worktree>`; (c) the only sanctioned operation against the parent repo path is `gh pr merge` in Phase 8 single-repo topology (already documented under Worktree gotchas).
- [ ] BR-7: **Dispatch prompt is the contract.** The exact dispatch-prompt template in `sprint/SKILL.md` Step 3 is normative — the orchestrator MUST emit a `WORKTREE PATH (mandatory): <abs-path>` line per dispatched agent. The line format is fixed so the receiving `/proceed` skill can parse it deterministically.
- [ ] BR-8: **Cross-repo coverage.** For cross-repo REQs, the orchestrator declares the **primary repo's** worktree path in the dispatch prompt. Sibling worktree paths are still resolved by `/proceed` Step 0 from `.adlc/config.yml`, but each sibling path goes through the same BR-3 validation gate before `git worktree add`.
- [ ] BR-9: **Failure messages name the user-facing fix.** When BR-3 or BR-5 fires, the error MUST tell the user the cleanup command: `git -C <repo> worktree remove <path>` followed by `git -C <repo> branch -D <branch>` (with `--force` flagged as available if the branch is unmerged). No vague "worktree exists" errors.
- [ ] BR-10: **Existing `/proceed`-direct workflows unchanged.** A user invoking `/proceed REQ-xxx` directly (no `/sprint`) on a REQ with no existing worktree MUST see no behavior change. This REQ adds defenses, not friction; the only new failure mode is "would have collided" — which would have been a silent corruption before.

## Acceptance Criteria

- [ ] AC-1: `sprint/SKILL.md` Step 3 dispatch prompt includes a `WORKTREE PATH (mandatory): <abs-path>` line, with `<abs-path>` computed by the orchestrator as `<repo-path>/.worktrees/<REQ-id>`. Verifiable by reading the updated skill file.
- [ ] AC-2: `proceed/SKILL.md` Step 0 documents the parse-declared-path-then-validate sequence, including the fallback-to-derivation rule (BR-2) and the fail-loud rule (BR-3). Verifiable by reading the updated skill file.
- [ ] AC-3: `proceed/SKILL.md` Step 0 documents that `pipeline-state.json.repos[<id>].worktree` is the immutable source of truth post-Step-0 and that no phase may re-derive (BR-4). Existing language at Step 0.5 is updated, not replaced. Verifiable by reading the updated skill file.
- [ ] AC-4: `sprint/SKILL.md` Step 2 pre-flight section adds the collision check (BR-5) and shows it as a row in the example pre-flight table. Verifiable by reading the updated skill file.
- [ ] AC-5: `agents/pipeline-runner.md` adds a top-level "Worktree isolation" section per BR-6. The existing "Worktree gotchas" subsection under Phase 8 stays — the new section sits at the agent-definition level, not buried under one phase. Verifiable by reading the updated agent definition.
- [ ] AC-6: A repro test (manual or scripted): with a stale `<repo>/.worktrees/REQ-999` left behind from a prior run on a different branch, invoking `/proceed REQ-999` halts at Step 0 with an error naming the conflicting branch and the cleanup command (BR-3, BR-9). Verifiable by setting up the stale state and observing the halt.
- [ ] AC-7: Documentation: the LESSON-003 file (already drafted in this REQ's branch) links back to this REQ in its `## Related` section. Verifiable by reading the lesson file.
- [ ] AC-8: No behavior change for the happy path: invoking `/proceed REQ-xxx` directly on a clean repo with no existing worktree completes Phase 0 identically to the pre-change behavior — same worktree path, same state file initialization, same logs. Verifiable by spot-checking a `/proceed` run.

## External Dependencies

- None. All changes live in this toolkit repo (`sprint/SKILL.md`, `proceed/SKILL.md`, `agents/pipeline-runner.md`).
- No new tooling or libraries; uses existing `git worktree list --porcelain` output.

## Assumptions

- `git worktree list --porcelain` output is stable enough to parse with simple line-based logic. (It's been stable since git 2.7; this is safe.)
- The `WORKTREE PATH (mandatory):` line format is unique enough that a simple regex/substring check inside `/proceed` Step 0 won't false-positive on user-typed prose elsewhere in the launch prompt.
- The user runs sprints on REQ ids that are globally unique within their primary repo's `.adlc/specs/`. (This is already a documented invariant.)
- Existing pipeline-state.json schema is sufficient — no schema migration needed; the `repos[<id>].worktree` field already holds the absolute path.

## Open Questions

- [ ] OQ-1: Should BR-3's fail-loud halt offer an interactive cleanup option (e.g., "Type 'remove' to run `git worktree remove <path>` and continue"), or always halt and require manual cleanup? Default: always halt — interactive cleanup is too easy to autopilot through and lose work. Revisit if users find the manual step annoying after this ships.
- [ ] OQ-2: Does BR-5's pre-flight collision check need to scan sibling repos for cross-repo REQs in `/sprint` Step 2, or is it sufficient to defer the sibling-path collision check to `/proceed` Step 0 (BR-3)? Default: scan only the primary repo at pre-flight (Step 2 happens in the orchestrator's repo); rely on Step 0 to catch sibling collisions per REQ. This keeps the pre-flight cheap and avoids speculative work for REQs that may not be eligible.
- [ ] OQ-3: Should the dispatch prompt also declare the absolute path of `pipeline-state.json` to remove any cwd-dependency on state-file lookup? Default: defer — state file path is derivable from spec dir, which is derivable from REQ id; the failure mode here has not been observed. Add only if a future incident shows state-file race conditions.

## Out of Scope

- Schema changes to `pipeline-state.json` — the existing `repos[<id>].worktree` field is sufficient.
- Generalizing the "orchestrator declares boundary" pattern to other multi-agent skills (`/review`, `/architect` parallel dispatch). May be worth a follow-up sweep but is not required for this REQ.
- A `/sprint --clean` or `/sprint --cleanup` flag to auto-remove stale worktrees. Manual cleanup per BR-9's error message is sufficient for now.
- Changing the `.worktrees/REQ-xxx` path convention itself. The convention is fine; the bug is that agents derived it instead of being told.
- Adding worktree-locking primitives (e.g., a `.adlc/locks/REQ-xxx.lock` file). The combination of orchestrator declaration + Phase 0 validation + pre-flight check is sufficient; locks would add a recovery problem (stale locks after crash) without removing a real risk.
- Backporting this fix to consumer repos' lessons or specs. Consumer-repo capture of the same incident (referenced as LESSON-281 in the user's report) is a manual mirror exercise, not toolkit work.

## Implementation Notes

_Non-normative. Sketch for the implementer in Phase 4._

**`sprint/SKILL.md` Step 3 — dispatch prompt template change**:

```diff
 **Agent prompt for each REQ**:
 ```
 Run the /proceed skill for REQ-xxx in the repository at [current repo path].
+WORKTREE PATH (mandatory): [absolute path: <repo-path>/.worktrees/REQ-xxx]
+- Use this exact path for git worktree add. Do NOT re-derive.
+- After Phase 0, all phases read the worktree path from
+  pipeline-state.json.repos[<id>].worktree. Never re-derive from cwd.
+- The only sanctioned operation in the parent repo path is
+  `gh pr merge` in Phase 8 single-repo topology.
 You are in SUBAGENT MODE — execute all phases sequentially, do not dispatch sub-agents.
 ...
```

**`sprint/SKILL.md` Step 2 — pre-flight collision check**:

Add to the pre-flight table example a new column `Worktree path` and a new "Issue" reason `worktree path in use by branch <name>`. The check itself: parse `git worktree list --porcelain` output, build a set of in-use paths, intersect with `{<repo>/.worktrees/<REQ-id> for REQ-id in candidates}`.

**`proceed/SKILL.md` Step 0 — declared-path parse + validation gate**:

Insert between current Step 0.4 and Step 0.5:

```
4a. Parse orchestrator-declared worktree path (if present):
    - Scan the launch prompt for a line matching:
      ^WORKTREE PATH \(mandatory\): (.+)$
    - If found: use that absolute path for the primary repo's worktree.
    - If absent: fall back to <primary-repo-path>/.worktrees/REQ-xxx.

4b. Validate the worktree path against existing worktrees:
    - Run: git -C <repo-path> worktree list --porcelain
    - Parse the output for "worktree <path>" / "branch <ref>" pairs.
    - If <target-path> is registered to a different branch than
      feat/REQ-xxx-short-description: STOP with error:
        "Worktree collision at <path> (currently owned by branch <name>).
         Run: git -C <repo> worktree remove <path>
              git -C <repo> branch -D <branch> [--force if unmerged]
         Then re-invoke /proceed REQ-xxx."
    - If <target-path> is already registered to the correct branch
      (resume scenario): proceed to Step 0.5 without re-adding.
    - Otherwise: proceed to Step 0.5 and `git worktree add`.
```

**`agents/pipeline-runner.md` — new "Worktree isolation" section**:

Insert after the "CRITICAL: Subagent Mode" section, before "Pipeline Phases":

```
## Worktree Isolation

You operate exclusively inside your assigned worktree.

1. Read the WORKTREE PATH from your launch prompt (line format:
   `WORKTREE PATH (mandatory): <abs-path>`). If absent, /proceed Step 0
   will derive and record one in pipeline-state.json.repos[<id>].worktree.
2. After /proceed Step 0 completes, your first action in every later phase
   is to read pipeline-state.json and re-read repos[<id>].worktree —
   that path is the source of truth. Do NOT re-derive from cwd.
3. Every Bash call uses absolute paths or `git -C <worktree>` form.
   Shell cwd does not persist between Bash calls; do not rely on it.
4. The only sanctioned operation in the parent repo path
   (repos[<id>].path) is `gh pr merge` in Phase 8 single-repo topology
   — git refuses to delete a branch checked out by a worktree, so the
   merge must run from the parent. Every other write goes to the worktree.
```
