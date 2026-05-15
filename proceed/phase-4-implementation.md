---
parent: proceed
phase: 4
---

# /proceed — Phase 4: Implement

Companion to `proceed/SKILL.md`. Phase 4 executes the task graph produced
by Phase 2 across every touched repo, dispatching task-implementer agents
in parallel tiers (main mode) or running tasks sequentially (subagent mode).
SKILL.md keeps a one-paragraph summary; the gate-protocol details and
tier orchestration steps live here.

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

**End-of-phase log**: After each tier completes, emit one line listing finished tasks with their target repos (e.g., `TASK-003 [api] ✓`) and any task-level failures (failed tasks are also written to `phase4.failedTasks`). Do not pause between tiers; advance to the next tier as soon as its dependencies are met.
