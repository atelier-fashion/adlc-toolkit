# Architecture — REQ-485: Auto-rebase and resume a blocked REQ after its blocker merges

## Context

REQ-483 added the *enforcement* half of multi-human coordination: a `/sprint` /
`/proceed` pipeline-runner that hits a real pre-merge trial-merge conflict (rc=1)
against an ahead REQ returns the `blocked` terminal, populating
`pipeline-state.json.blockers` with `{blockedBy, conflictFiles, unblockCondition}`.
Today that held REQ is **surfaced to a human** for manual rebase + resume
(sprint/SKILL.md Step 5 L216 "hold that REQ — `blocked`, surfaced for rebase").

REQ-485 closes the unattended gap: after a `/sprint` batch merges the blocker
REQ-A, the orchestrator automatically rebases any REQ held with `blockedBy == A`
onto the refreshed integration branch and resumes it — **composing existing
machinery** (workflow `resumeFromRunId`, the trial-merge gate, the
`pipeline-state.blockers` schema, `currentPhase`), not inventing new mechanism.
The only net-new piece is the **automatic trigger**: blocker-merged →
rebase-held-REQ → resume, replacing "park it for a human."

## Decisions (ADRs)

### ADR-1: The auto-rebase/resume trigger lives in the `/sprint` orchestrator only (BR-1)

The trigger is added to `/sprint`'s merge-sequencing path — the one place that
*knows* a blocker just merged within the run. Solo `/proceed` (and the
`pipeline-runner` agent it drives) keep today's manual-resume behavior: a
pipeline-runner that hits rc=1 still returns `blocked` and exits; it does NOT
self-resume (BR-8 — "the held pipeline-runner does NOT self-resume"). The
orchestrator owns the trigger because:

- Only the orchestrator sees the *cross-REQ* "REQ-A merged" event (a single
  pipeline-runner sees only its own REQ).
- BR-9 scopes v1 to *within-run* blockers: the orchestrator merged REQ-A itself,
  so the merge is a known local event, not something to poll for.
- Mutating a held REQ's branch is a write the held (already-exited) runner can no
  longer perform; the live orchestrator must.

**Rationale**: keeps the manual `/proceed` path unchanged (the human is present),
and concentrates the new control flow in the orchestrator that has the necessary
visibility and lifecycle.

### ADR-2: Two-engine implementation, workflow-engine-first per OQ-1 default

`/sprint` is a two-engine dispatcher (legacy background-runner + workflow
`adlc-sprint.workflow.js`). The auto-rebase/resume trigger is specified for both,
but with the OQ-1 default applied:

- **Workflow engine (primary)**: the engine has a first-class resume-from-phase
  mechanism (`resumeFromRunId` + `args.answers[<REQ-id>]`). REQ-485 extends the
  resume contract with an **orchestrator-generated `blocker-cleared` signal**
  (BR-8) so a merge-blocked REQ can be resumed by the orchestrator (not a user
  answer). After the cross-REQ merge barrier merges REQ-A, the script runs an
  **unblock pass** that rebases held REQs and relaunches via `resumeFromRunId`
  with the cleared signal.
- **Legacy engine (degrade-safe per BR-7)**: the legacy engine re-dispatches a
  fresh `pipeline-runner` for the held REQ after a clean rebase. Where the legacy
  engine cannot re-dispatch-from-phase cleanly (OQ-1 — no `resumeFromRunId`
  equivalent), it **degrades to today's surface-to-human** (BR-7) rather than
  erroring. A fresh pipeline-runner re-runs the now-passing trial-merge gate at
  Phase 8 and proceeds to merge — this IS a legacy "resume from currentPhase"
  for the common pre-merge-gate halt, so the common case is auto-resumable; only
  exotic mid-phase halts degrade.

**Rationale**: OQ-1 default explicitly says "workflow-engine first; legacy
degrades." This avoids inventing a legacy resume-from-arbitrary-phase engine
(out of scope) while still auto-resolving the dominant case (a Phase-8
trial-merge halt) on both engines.

### ADR-3: Clean rebase auto-resumes; conflicting rebase aborts non-mutatingly and re-halts (BR-3, BR-4)

The unblock attempt for a held REQ:

1. `git -C <held-worktree> fetch origin <integrationBranch>` (refresh the tip —
   a stale ref is a false result, LESSON-036).
2. `git -C <held-worktree> rebase origin/<integrationBranch>`.
3. **Clean (exit 0)** → auto-resume from `resumePhase` (the recorded
   `currentPhase`): workflow → `resumeFromRunId` with `blocker-cleared`; legacy →
   re-dispatch pipeline-runner. The resumed run re-runs the now-passing
   trial-merge gate and proceeds to merge.
4. **Conflict (non-zero)** → `git -C <held-worktree> rebase --abort` (worktree
   restored, non-mutating), re-halt `blocked` carrying the NOW-materialized
   conflict files, surface for human resolution. **Never** auto-resolve, `-X`
   force, or "merge anyway" (ethos #6).

This mirrors the trial-merge philosophy exactly (REQ-483): a real conflict is
always human-resolved; the machinery only *detects* and *restores*, never
resolves.

### ADR-4: Auto-rebase mutates ONLY the held REQ's own worktree (BR-5)

The unblock pass operates exclusively inside `repos[<held-id>].worktree` on the
held REQ's own `feat/REQ-x-...` branch. It MUST NOT touch the blocker's branch/PR
(already merged, immutable) or any third REQ's worktree. Ordering is *derived*
from merge events, never *asserted* by mutating another REQ's tree — the same
permission boundary REQ-483 established. The `git -C <worktree>` form makes the
target worktree explicit on every command (no cwd inference, per pipeline-runner
worktree-isolation rules).

### ADR-5: Deterministic, idempotent, serialized unblock pass anchored on `blockers` presence (BR-6, BR-11)

The unblock pass:

- **Deterministic + idempotent**: with nothing newly merged it is a no-op. When
  multiple REQs are blocked on the same blocker they unblock in REQ-483's
  deterministic order (earliest-published PR, lower REQ tiebreak) and are
  processed **one at a time** (serialized), because the held REQs may themselves
  overlap — resuming two overlapping REQs concurrently would re-introduce the
  merge race REQ-483 eliminated.
- **Idempotency anchor (BR-11)**: the unblock pass considers ONLY REQs whose
  `pipeline-state.json.blockers` entry is *still present*. On a successful resume
  that reaches merge, the orchestrator transitions the BlockHold to `resumed` and
  **clears the REQ's `blockers` entry**. Today the merge path sets
  `repos[<id>].merged = true` but never clears `blockers`; REQ-485 adds the
  clear. Without the clear, a later blocker-merged event could re-process an
  already-merged REQ.

### ADR-6: Retry bound prevents an auto-rebase loop (BR-10, OQ-3/OQ-6 defaults)

If a held REQ's rebase conflicts, BR-4 re-halts it. To prevent an infinite
auto-rebase loop when the conflict persists, a retry bound (OQ-3 default: **1**,
overridable via `.adlc/config.yml`) caps conflicting-rebase attempts. After the
bound is hit, the REQ is marked **`needs-manual-rebase`** (OQ-6 default) — a
state semantically distinct from "waiting for a blocker to merge." A
`needs-manual-rebase` REQ is **not auto-re-triggered** by future blocker-merged
events; it waits for a human. BR-10 counts attempts **per blocker-merged event**
(OQ-6 default), recorded in the `blockers` entry.

### ADR-7: `blockedBy` semantics after a materialized conflict (OQ-6 default)

When a rebase conflicts *after* the blocker has already merged (the BR-4
re-halt), the REQ needs **manual conflict resolution**, not "wait for a blocker."
Its `blockers` entry transitions to a `manual`/`self` sentinel (state
`needs-manual-rebase`) so the BR-2 unblock scan (which keys on a live
`blockedBy == <just-merged-REQ>`) does not re-pick it up. The now-merged blocker
id is preserved in a `resolvedBlocker` field for human context, but `blockedBy`
no longer points at a live merge dependency.

### ADR-8: OQ-5 — release a held REQ when its sole blocker ends `failed`/abandoned

If a blocker REQ ends `failed`/abandoned *within the run* (its PR will never
merge), no blocker-merged event will ever fire BR-2, so a REQ held *solely* on it
would sit `blocked` to batch-end. Its ordering constraint has dissolved, so per
OQ-5 default the orchestrator **releases + re-attempts** the solely-dependent
held REQ (treats the dead blocker as cleared, runs the same rebase+resume path).
A REQ with *other* live blockers stays held. This is the in-run analogue of
REQ-483's stale-PR safety.

## System Model realization

| Spec entity/field | Realization in `pipeline-state.json.blockers[*]` |
|---|---|
| BlockHold.req | the REQ's own spec dir (state file owner) |
| BlockHold.blockedBy | `blockers[*].blockedBy` (live merge dep) or `manual`/`self` sentinel post-conflict (ADR-7) |
| BlockHold.resumePhase | top-level `currentPhase` (already recorded) |
| BlockHold.conflictFiles | `blockers[*].conflictFiles` (from trial-merge/rebase) |
| BlockHold.state | `blockers[*].holdState` ∈ `held` / `rebasing` / `resumed` / `re-halted` / `needs-manual-rebase` |
| (retry bound) | `blockers[*].rebaseAttempts` (int, capped at config `auto_rebase_max_attempts`, default 1) |
| (OQ-6 context) | `blockers[*].resolvedBlocker` (the now-merged blocker id, post-conflict) |

`resumed` clears the entry entirely (BR-11), so it is a transient terminal
observed only during the clearing write.

## Events realization (sprint orchestrator)

| Event | Where | Effect |
|---|---|---|
| blocker-merged | legacy Step 5 / workflow cross-REQ merge barrier, immediately after `gh pr merge` of REQ-A lands and `repos[A].merged=true` is written | run the unblock pass for every held BlockHold with `blockedBy == A` (BR-2) |
| blocker-failed | legacy Step 4.6 / workflow runReq terminal, when REQ-A returns `failed`/abandoned | release every BlockHold held SOLELY on A (ADR-8 / OQ-5) |
| rebase-clean | `git rebase` exit 0 in held worktree | auto-resume from `resumePhase` (BR-3) |
| rebase-conflict | `git rebase` non-zero | `rebase --abort`; increment `rebaseAttempts`; if < bound re-halt `held`; if ≥ bound mark `needs-manual-rebase` and surface (BR-4, BR-10) |

## Affected files

| File | Change |
|---|---|
| `sprint/SKILL.md` | Legacy Step 5: add the post-merge **unblock pass** (BR-2/3/4/5/6/10) + OQ-5 blocker-failed release (ADR-8). Workflow Step 0: extend the resume contract with the orchestrator `blocker-cleared` signal (BR-8). Add a "Self-healing serialization" subsection documenting the trigger, ordering, retry bound, and degrade-safe behavior (BR-1/7/9). |
| `agents/pipeline-runner.md` | Phase 8 / Blocker Handling: add BR-11 — on a successful resume that reaches merge, clear the REQ's `pipeline-state.json.blockers` entry (today only `merged=true` is set). Note the held runner does NOT self-resume (BR-8). |
| `proceed/phases-6-8-ship.md` | Phase 8 pre-merge trial-merge gate: document the `blockers` entry schema additions (`holdState`, `rebaseAttempts`, `resolvedBlocker`) and the BR-11 clear-on-resolve at the merge step. |
| `.adlc/context/architecture.md` | Add a one-line "Self-healing serialization (REQ-485)" bullet to the cross-cutting dependencies / ordering-enforcement section. |

## Out of scope (per spec)

- Auto-RESOLVING rebase conflicts (always human-resolved).
- Cross-session auto-resume (a different session merges the blocker) — v1 is
  within-`/sprint`-run only (BR-9).
- Solo `/proceed` auto-resume (stays manual, BR-1).
- A new legacy resume-from-arbitrary-phase engine (OQ-1 — legacy degrades).
- Cross-repo footprint publishing (REQ-484, sibling follow-up).

## Risk / verification notes

- **LESSON-330**: this REQ has 11 BRs. Before Phase 5, every BR is mapped to its
  implementing edit (see Phase-5 BR-coverage cross-check). The highest risk is a
  BR implemented-as-zero (e.g., BR-11 clear, BR-10 retry bound) — each is called
  out explicitly in Affected files.
- **LESSON-329**: any bash added to `sprint/SKILL.md` (rebase loop) must be
  split-free and dogfood-able under zsh — iterate held REQs over newlines, quote
  every path, wrap any `git -C` loop in a `while read -r` over `printf '%s\n'`.
- **Markdown-only convention**: this is a skills-doc REQ (sprint/SKILL.md,
  pipeline-runner.md, phases-6-8-ship.md are markdown). "Tests" are dogfooding +
  the BR→diff cross-check, not a unit-test runner (conventions.md "Code is
  markdown, not code"). The workflow `.js` resume-contract change, if any, is
  documentation of the `args` channel; the actual JS edit is scoped minimally and
  covered by the existing `workflows/tests/` node:test suite if touched.
