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

**Lite lane (REQ-652):** a lite REQ has no task files, so nothing below
applies to it. It implements in the orchestrator's own context from the spec's
acceptance criteria, after a fresh retrieval: `proceed/phases-lite.md`
"Phase 4 (lite)".

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
   - **Compute the task's LessonSet (REQ-647 BR-1a) — the LESSON-604 mechanism.** The spec's `## Retrieved Context` and the Step-0 set are REQ-vintage; this set is chosen by the surface the task touches, so a lesson captured after the spec was written still reaches it. Infer the components of the task's `## Files to Create/Modify` paths as `/review` Step 1 item 7a does, passing the **most specific** component of each path (`partials/forge.sh` → `adlc/partials/forge`, `tools/lint-skills/check.py` → `adlc/tools/lint-skills`); the engine adds the ancestors, scores with the `/spec` Step 1.6 rule, takes the top 5, adds up to 3 lessons whose `created` is later than the spec's (most specific component first, each flagged `newerThanSpec`), then the Step-0 set's `kind: process` lessons, never past 15:

     ```sh
     ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
     if [ -f .adlc/partials/lessons.sh ]; then . .adlc/partials/lessons.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lessons.sh"; fi
     # <worktree> = repos[<task.repo>].worktree; <spec> = the primary worktree's requirement.md;
     # <state> = the primary-path pipeline-state.json (its lessons.step0 feeds the process carry-over).
     adlc_lessons select --set task --task-id "<TASK-xxx>" --root "<worktree>" --spec "<spec>" --state-out "<state>" --component "<component>"
     ```

     The first stdout line is the task's log line (`Lessons loaded (task TASK-xxx): …`); the rest is the loaded text, at most 15 lessons of at most 40 lines each. On a resume of this task, pass `--reuse` so the set recorded on the first attempt is kept. A return of 2 is one `lessons: unavailable — <reason>` line: log it and implement without lessons — retrieval never halts the phase.
   - Read the task's lessons, then implement the changes following project conventions (from `.adlc/context/conventions.md`). When a supplied lesson applies to a change, **acknowledge it** where Phase 5's acknowledgement check looks: a `Lessons: LESSON-xxx[, LESSON-yyy]` trailer in the task's commit message, or the id in the task's `## Verification` block (BR-2). An acknowledgement only in a report is invisible to the check.
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
- Each task-implementer agent (defined in `$ADLC_TOOLKIT_ROOT/agents/`) receives: the full task file, conventions.md, architecture.md, **the task's LessonSet loaded text** (computed in step 4, REQ-647 BR-2), **and the absolute path of the target repo's worktree** (from `repos[<task.repo>].worktree`). The agent must operate exclusively inside that worktree.

Agent names are bare on the symlink install and `adlc:`-prefixed on the plugin install (`adlc:<name>`). Before dispatching, check which form the Agent tool lists and use that one; do not wait for an error, because a name it does not list can silently run a generic agent without the checklist. If neither form is listed, say which agent is missing, then read `$ADLC_TOOLKIT_ROOT/agents/<name>.md` (the toolkit root is the parent of this skill's base directory) and run its checklist inline, or give its body to a general-purpose agent as the prompt, instead of skipping it; a review or audit agent stays read-only either way.

**Subagent mode** — sequential execution:
- Execute tasks one at a time in cross-repo dependency order
- Implement each task directly in your own context (do not dispatch agents), cd-ing into the target worktree for each task
- Compute each task's LessonSet before implementing it, exactly as in main mode, and follow the implementer's acknowledgement rule yourself

**End-of-phase log**: After each tier completes, emit one line listing finished tasks with their target repos (e.g., `TASK-003 [api] ✓`) and any task-level failures (failed tasks are also written to `phase4.failedTasks`), then each finished task's lessons line (REQ-647 BR-10), recomputed from the state record so it says whether lessons landed while the task ran:

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/lessons.sh ]; then . .adlc/partials/lessons.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lessons.sh"; fi
adlc_lessons log-line --state "<state>" --key "tasks.<TASK-xxx>" --root "<worktree>"
```

It prints, for example, `Lessons loaded (task TASK-012): LESSON-013, LESSON-335 [newer-than-spec: LESSON-582]`, with `(stale: N lessons newer than this set)` appended when N lesson files changed after the set was computed. Do not pause between tiers; advance to the next tier as soon as its dependencies are met.
