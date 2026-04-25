---
id: LESSON-003
title: "Sprint dispatch must declare each pipeline-runner's worktree path; deriving it lets siblings clobber each other"
component: "adlc/sprint"
domain: "adlc"
stack: ["claude-code", "git-worktree", "bash"]
concerns: ["concurrency", "data-loss", "developer-experience"]
tags: ["sprint", "worktrees", "parallel-pipelines", "race-condition", "dispatch-contract"]
req: REQ-263
created: 2026-04-24
updated: 2026-04-24
---

## What Happened

A multi-tier `/sprint` run launched several `pipeline-runner` agents in parallel against distinct REQs (REQ-295 through REQ-299). All three Tier 1 final reports independently flagged the same failure mode: **sibling pipeline-runners checking out other branches into the same worktree path mid-run**. Two REQ specs (REQ-296 and REQ-297) were destroyed by the collision before the user noticed.

The user manually worked around it for Tier 2 and Tier 3 by editing each agent's launch prompt to include an explicit absolute worktree path. With the path declared up front, the collision disappeared and Tier 2/3 ran clean.

The chain of fragility in the unfixed dispatch is:

1. **Shared parent cwd.** Every dispatched `pipeline-runner` inherits the orchestrator's cwd — the parent repo. Any operation that lands in the parent working tree (instead of a worktree) races siblings. The parent working tree is the only thing all parallel pipelines truly share, and it is unprotected.
2. **Worktree path is derived, not declared.** The original `/sprint` Step 3 dispatch prompt told each agent to run `/proceed` "in the repository at [current repo path]" without specifying a worktree path. Each agent then re-derived `.worktrees/REQ-xxx` itself inside `/proceed` Step 0. After context compression or a resume, an agent could re-derive against a stale cwd and end up pointed at the wrong path.
3. **No collision gate.** Neither `/sprint` Step 2 pre-flight nor `/proceed` Step 0 consulted `git worktree list` before adding a worktree, so an existing worktree owned by another live pipeline could be silently overwritten.

## Lesson

**For multi-agent orchestration, the orchestrator must own the isolation boundary and declare it explicitly to each agent — never let the agent re-derive its own boundary.** When N parallel agents all share the same launch context (cwd, env, repo path), any property an agent computes from that context is at risk of drifting against its siblings. Worktree paths are the canonical example: they look like a deterministic function of (repo, REQ) — but in practice, REQ identity, cwd, and which-repo-am-I-in can all shift mid-run, so "deterministic function of context" is a lie.

The fix has three coordinated parts. None of them in isolation is sufficient:

1. **Orchestrator computes and declares each agent's worktree path** as an absolute path in the dispatch prompt: `WORKTREE PATH (mandatory): /abs/path/to/repo/.worktrees/REQ-xxx`. The agent must use that exact path, not re-derive.
2. **Receiving skill validates the declared path** before `git worktree add`: consult `git worktree list --porcelain` and fail loud if the target path is already registered to a different branch. Never silently reuse an existing worktree.
3. **Pre-flight collision check at the orchestrator** scans for `.worktrees/REQ-xxx` paths already in use and refuses to dispatch overlapping REQs.

**Why all three:** (1) closes the in-flight derivation drift. (2) catches stale state from a prior crashed run. (3) prevents the user from launching a sprint that would collide before any agent is dispatched. Skipping any one leaves a recoverable hole.

**Operational rule for agents:** the agent's first action after reading state should be `cd <worktree>`; every subsequent Bash call should use absolute paths or `git -C <worktree>`. The only sanctioned operation in the parent repo path is `gh pr merge` in Phase 8 (single-repo topology), which requires the parent path to delete a branch checked out by a worktree.

## Why It Matters

Spec destruction is the worst-case symptom: the user lost two REQ specs (REQ-296, REQ-297) and had to rebuild them. A worktree clobber that destroys spec files also destroys the pipeline-state.json that would let `/sprint` resume cleanly — so a single race can take out both the work product and the recovery path. The blast radius scales with the number of parallel pipelines: an N=5 sprint has 5×4=20 concurrency edges per phase, and the cost of a collision compounds because every downstream tier inherits the corrupted base.

The cheap manual workaround (passing explicit paths) proved the fix; not codifying it leaves the next sprint operator to rediscover the bug.

## Applies When

- Designing multi-agent orchestration where N agents share a launch context
- Reviewing dispatch prompts for `/sprint`, `/proceed`, or any future parallel-pipeline skill
- Adding a new "compute path from context" pattern to any skill — prefer "declare path explicitly" instead
- Triaging "files mysteriously changed mid-run" reports during sprint or parallel-task execution

## Counter-pattern to avoid

Don't treat `.worktrees/REQ-xxx` (or any `<dir>/<unique-id>` derivation) as inherently collision-safe just because the unique-id is globally unique. The collision risk is not at the path level — it's at the **agent-derives-the-path** level. As long as the agent computes the path itself, any drift in the inputs (cwd, REQ identity, repo registry) produces a wrong path that may overlap with a sibling's correct path. Make the orchestrator declare the path; make the agent verify it.

## Related

- REQ-263 — bugfix REQ that codifies these three changes in `/sprint`, `/proceed`, and the `pipeline-runner` agent definition
- LESSON-002 — cross-repo primary-is-per-REQ; established that `pipeline-state.json` is the per-REQ runtime registry. This lesson extends that: the registry must be **orchestrator-populated**, not agent-derived
