---
parent: proceed
phases: "1-3"
---

# /proceed — Phases 1–3: Validation & Architecture

Companion to `proceed/SKILL.md`. These three phases establish a validated
spec, derive an architecture and task graph, then validate that breakdown
before any implementation begins. SKILL.md keeps a one-paragraph summary of
each; this file holds the step-by-step.

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
   - For each configured repo with no tasks (and not primary), set `touched: false` and remove its worktree using the absolute path recorded in state: `git -C <repo-path> worktree remove <repos[<id>].worktree>`.
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
