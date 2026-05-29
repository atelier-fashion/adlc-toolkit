---
id: REQ-474
title: "Re-platform /sprint orchestration onto Claude Code Dynamic Workflows"
status: draft
deployable: true
created: 2026-05-29
updated: 2026-05-29
component: "adlc/sprint"
domain: "adlc"
stack: ["claude-code", "dynamic-workflows", "javascript", "markdown", "bash"]
concerns: ["orchestration", "concurrency", "resumability", "delegation", "security"]
tags: ["dynamic-workflows", "sprint", "pipeline-runner", "kimi-pre-pass", "opus-4-8", "worktree", "halt-resume", "review-panel", "schemas", "two-engine"]
---

## Description

Opus 4.8 ships **Dynamic Workflows** — a native Claude Code capability to "plan the work and then run hundreds of parallel subagents in a single session," with output verification. This directly overlaps the toolkit's hand-rolled `/sprint` + `pipeline-runner` orchestration, which exists specifically to work around the constraint that **a subagent cannot dispatch sub-agents** (`pipeline-runner.md` opens with "You CANNOT dispatch sub-agents"). That constraint forces today's trade-off: `/proceed` gets rich per-REQ parallelism (explore trio, task tiers, 6-agent review panel) but runs one REQ at a time, while `/sprint` runs N REQs at once but collapses each into a **sequential** pipeline with a single inline review checklist instead of the parallel specialist panel.

This REQ re-platforms `/sprint` onto a deterministic **Workflow script** (the `adlc-sprint` workflow) in which orchestration lives in the script and agents are leaves it dispatches. That lifts the nesting constraint and yields the cross-product: **N REQs concurrently, each with its full internal fan-out restored** — most importantly the parallel Phase-5 review panel that `/sprint` currently sacrifices.

The change is additive and gated. `/sprint` stays the single user-facing command and becomes a **two-engine dispatcher**: it uses the workflow engine when Dynamic Workflows is available (behind a `--workflow` flag during the experimental phase), and otherwise falls back to today's background-`pipeline-runner` engine, which remains unchanged. The workflow naturally handles N=1, so a future `/proceed` unification is possible but is **not** in scope here.

This spec was developed through an extended design dialogue; it captures the agreed design end-to-end so implementation has a single source of truth rather than scrollback.

_Altitude note (validated 2026-05-29): by design this requirement carries architecture-level detail — the structured-output schemas (System Model) and the pipeline shape (Business Rules). This is a conscious choice to preserve the agreed design in one place; `/architect` should formalize these into ADRs and tasks rather than re-derive them, and a future `/validate` should not re-flag the altitude as a defect._

## System Model

_This is a process/orchestration feature; the "data model" is the set of structured-output schemas the workflow uses to replace prose-parsing, plus the engine-selection inputs._

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| EngineSelection | dynamicWorkflowsAvailable | boolean | true iff the session can invoke the Workflow tool (plan + Claude Code ≥ v2.1.154) |
| EngineSelection | workflowFlag | boolean | from `--workflow`; during experimental phase, workflow engine requires this true |
| EngineSelection | engine | enum | `workflow` \| `legacy` — `workflow` only if available AND (flag OR graduated default) |
| WorkflowArgs | reqs | string[] | REQ ids to sprint (max 5 enforced after eligibility) |
| WorkflowArgs | integrationBranch | string | resolved per repo (`staging` two-branch, else `main`); never hardcoded `main` |
| WorkflowArgs | answers | map<reqId,string> | `{}` on first run; carries user replies to halts on resume |
| CANDIDATES (per repo) | repo | string | repo id the pre-pass ran for |
| CANDIDATES | invoked | boolean | true iff `ask-kimi` actually executed (drives ghost-skip check) |
| CANDIDATES | exit | integer | ask-kimi exit code; 0 = ok |
| CANDIDATES | gateReason | enum | `ok` \| `no-binary` \| `disabled-via-env` |
| CANDIDATES | changedFiles | string[] | `git diff <base>...HEAD --name-only` — TRUSTED; script validates candidate paths against it |
| CANDIDATES | candidates[] | object[] | `{dimension∈5, path, lineRange?, description}` — UNTRUSTED (from Kimi stdout) |
| FINDINGS (per reviewer) | dimension | enum | `reflector` \| `correctness` \| `quality` \| `architecture` \| `test-coverage` \| `security` |
| FINDINGS | findings[] | object[] | `{severity∈[Critical,Major,Minor,Nit], file, line?, title, detail?, suggestedFix?, mustFix, userFacing, lessonId?, fromCandidate}` |
| TERMINAL (per REQ) | state | enum | `merged` \| `pr-ready` \| `blocked` \| `failed` |
| TERMINAL | prs[] / reason / detail | mixed | PR urls on success; `reason`+`question` on blocked |
| REQ pipeline (runReq) | worktree | string (abs path) | persistent per-REQ worktree, created+recorded in Phase 0; reused across all phases |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| halt:validation | spec/arch validation fails 3× at a gate | `{terminal:'blocked', reason:'spec\|arch-validation'}` |
| halt:reflector-question | reflector returns a `userFacing` finding | `{terminal:'blocked', reason:'reflector-questions', detail:{questions}}` |
| halt:merge-conflict | Phase 8 rebase/merge conflict | `{terminal:'blocked', reason:'merge-conflict'}` |
| req:merged | single-repo REQ self-merges in Phase 8 | `{terminal:'merged', prs}` |
| req:pr-ready | cross-repo REQ stops at Phase 7 | `{terminal:'pr-ready', prs}` |
| resume | user answers a blocked REQ | relaunch with `resumeFromRunId` + `args.answers[reqId]` |

### Permissions

| Action | Allowed when |
|--------|--------------|
| Run workflow engine | Dynamic Workflows available AND (`--workflow` OR graduated-to-default) |
| Run legacy engine | always (fallback) |

## Business Rules

- [ ] BR-1: `/sprint` is a single command with two engines. It selects the **workflow** engine only when Dynamic Workflows is available AND (`--workflow` is passed OR the engine has been graduated to default); otherwise it runs the **legacy** background-`pipeline-runner` engine. The legacy engine's behavior is unchanged by this REQ. (informed by REQ-263)
- [ ] BR-2: The per-REQ worktree is **explicit and persistent** — created and recorded by the Phase-0 agent and reused across Phases 0–8. The Workflow tool's per-agent `isolation:'worktree'` is NOT used for the REQ container (wrong lifecycle: per-agent, ephemeral). Worktree paths obey the REQ-263 dispatch-line / absolute-path contract and base on `origin/<integrationBranch>`, never a hardcoded `main`. (informed by REQ-263, LESSON-003, BUG-060)
- [ ] BR-3: Read-only / report phases fan out in parallel — Phase 2 (explore trio) and Phase 5 (review panel). Phase 4 (implement) runs **serially** within the single REQ worktree (one writer, no git-index contention). Per-task worktrees and Phase-4 parallelism are out of scope for v1. (informed by LESSON-003)
- [ ] BR-4: A pipeline halt MUST be expressed as a **returned** `{terminal:'blocked', …}` value, never a thrown error (a throw would drop the item to `null` and lose the question). The three halts are: validation fails 3× (Phase 1/3), a reflector `userFacing` question (Phase 5), and a merge conflict (Phase 8). (informed by LESSON-004)
- [ ] BR-5: Resume is via `resumeFromRunId` with the user's reply threaded through `args.answers[reqId]`. The previously-blocked REQ re-runs **from its halt point** (its halt-prone agent prompts reference `args.answers`, so only they diverge from cache); untouched REQs and already-`merged` REQs replay from cache and MUST NOT re-execute side effects (no double-merge).
- [ ] BR-6: Terminal-state is schema-validated (`TERMINAL`) rather than parsed from prose. A `merged`/`pr-ready` claim is still **verified** against `gh pr view --json state,mergedAt` before acceptance — a claim is not truth. (Verify, Don't Trust)
- [ ] BR-7: Phase-5 review findings are returned as `FINDINGS` objects. Consolidation, dedupe, cross-repo flagging, severity ranking, and the Critical-blocks gate are performed in **deterministic script code**, not by an agent.
- [ ] BR-8: In the workflow engine, the Kimi Phase-5 pre-pass is **skipped for v1** (matching current `/sprint`, which already skips it — `pipeline-runner` runs no pre-pass). The pre-pass is advisory (recall, not safety), so skipping loses no correctness guarantee. (informed by REQ-417)
- [ ] BR-9: The **target** pre-pass design uses one `kimi-pre-pass` leaf agent **per touched repo** (the citation-scoping boundary): the agent performs gate-check, diff capture, credential redaction, and the `ask-kimi` call, returning `CANDIDATES`. The workflow **script** performs the LESSON-008 citation validation in deterministic JS — reject any path containing `..`, require `candidate.path ∈ changedFiles`, sanitize the description column — and slices candidates per dimension into the 5 reviewers. The **reflector receives no candidates**. (informed by LESSON-008, LESSON-010, REQ-417)
- [ ] BR-10: Delegation integrity in the workflow is enforced **structurally**: the script asserts `candidates ⇒ invoked` (a claimed-but-not-invoked pre-pass is a ghost-skip the script rejects), and the pre-pass agent still emits unified telemetry via `emit-telemetry.sh` (which independently unmasks any mislabeled gate-pass fallback as `ghost-skip`) so `check-delegation.sh` stays whole across skills. Kimi stdout is never executed as instructions. (informed by LESSON-012, REQ-424, REQ-416, LESSON-008)
- [ ] BR-11: `pipeline-state.json` remains the durable artifact (it powers `/status` and the legacy engine); the workflow journal / `resumeFromRunId` handles in-run recovery. Both are retained; neither is removed by this REQ.
- [ ] BR-12: REQ-level concurrency keeps the existing max-5 bound (applied after eligibility). Beyond that, the workflow relies on the built-in `min(16, cores−2)` agent cap and `budget.total` as the cost ceiling — no custom semaphore. Silent truncation of coverage (top-N drops) MUST be logged via `log()`.

## Acceptance Criteria

- [ ] AC-1: On a Dynamic-Workflows-capable session, `/sprint --workflow REQ-a REQ-b` runs both REQs concurrently through Phases 0–8, each with a **parallel** Phase-5 specialist panel (reflector + 5 reviewers). _Oracle:_ the run produces the same set of merged PRs (same touched repos, same squash result) as a legacy-engine run of the same REQs, compared via final `pipeline-state.json.repos[*].merged` and `gh pr view --json state`.
- [ ] AC-2: On a session without Dynamic Workflows (or without `--workflow`), `/sprint` runs the legacy engine. _Oracle:_ no diff to the legacy `sprint` dispatch path, `proceed/SKILL.md`, or `pipeline-runner.md` behavior; a smoke run of one known REQ yields the same phase sequence, agent set, and PR outcome as before REQ-474.
- [ ] AC-3: A REQ that hits any of the three halts returns `blocked` with its question; the workflow run completes (other REQs unaffected); the orchestrator surfaces the question; a `resumeFromRunId` relaunch carrying the answer advances **only** that REQ past the halt and does **not** re-merge any already-merged REQ.
- [ ] AC-4: Phase-5 consolidation (dedupe, cross-repo flag, severity rank, Critical-blocks gate) is performed by deterministic code; a `Critical` finding blocks merge; a reflector `userFacing` finding triggers the halt.
- [ ] AC-5: `TERMINAL` claims of `merged`/`pr-ready` are re-verified with `gh pr view --json state,mergedAt` before the dashboard accepts them; a false `merged` claim is caught and corrected. (covers BR-6)
- [ ] AC-6: **Worktree persistence (BR-2):** a multi-phase REQ run uses one worktree across Phases 0–8 — the path recorded in `pipeline-state.json.repos[*].worktree` is created in Phase 0 and unchanged through Phase 8; no per-agent ephemeral (`isolation:'worktree'`) worktree is created for the REQ container.
- [ ] AC-7: **State + resume (BR-11):** after a run, `pipeline-state.json` reflects final per-REQ state (consumable by `/status`); an interrupted run resumed via `resumeFromRunId` recreates no existing worktree and re-merges no already-merged PR.
- [ ] AC-8: **Concurrency (BR-12):** a sprint of >5 eligible REQs runs at most 5 concurrently; agent fan-out respects the built-in `min(16, cores−2)` cap; any coverage truncation (top-N drop) is emitted via `log()`.
- [ ] AC-9: _(target / post-OQ-1)_ The `kimi-pre-pass` agent returns `CANDIDATES`; the script drops a candidate citing a `..` path or a path absent from `changedFiles`; the reflector receives no advisory block; telemetry records `delegated`/`fallback`/`ghost-skip` correctly and `check-delegation.sh` counts it.
- [ ] AC-10: The `adlc-sprint` workflow script and the `kimi-pre-pass` agent definition pass `lint-skills` / template-drift checks where applicable.

## External Dependencies

- **Claude Code Dynamic Workflows** — research preview, available on Max/Team/Enterprise plans, requires Claude Code ≥ v2.1.154 (Opus 4.8). This gating is why the legacy engine must remain a first-class fallback (BR-1). The capability may be absent in headless/cron runs.
- **`ask-kimi`** (existing toolkit tooling) — only for the target pre-pass (BR-9); not required for v1 (BR-8).

## Assumptions

- The Opus-4.8 agent model/effort tuning (effort `xhigh` on the doer agents; `opus` on correctness/security/reflector) is already in place — shipped in commit `8758132` — so the agents the workflow dispatches via `agentType` already carry the intended tiers. (out of scope here; see Out of Scope)
- Tasks within a Phase-4 dependency tier touch **disjoint files** (enforced by `/architect`), which is what makes serial-in-shared-worktree safe and is a prerequisite if per-task worktrees are added later.
- Dynamic Workflows behaves as documented: one-level agent nesting, cache keyed by `(prompt, opts)` for resume, and **the script is responsible for its own git/worktree management** (the workflow primitive has no shell/filesystem access — every git/gh/file op runs inside an `agent()` call).
- Existing agent definitions (`correctness-reviewer`, `task-implementer`, explorers, etc.) are reusable as-is via `agentType`; only `kimi-pre-pass` is new.

## Open Questions

- [ ] OQ-1: Does a workflow **leaf agent's** Bash inherit the launchctl-exported environment so `ask-kimi` (and `MOONSHOT_API_KEY`) are reachable? This determines whether the target pre-pass (BR-9) is buildable. The `pipeline-runner` prose asserts subagents can't reach it, but a live env check this session found `ask-kimi` on PATH and the key set even in a non-interactive shell — so that assumption may be stale. **Must be tested against a real leaf agent before BR-9 is implemented.** (informed by LESSON-011)
- [ ] OQ-2: Single source of truth for state — keep both `pipeline-state.json` and the workflow journal (BR-11 default), or collapse to one once the workflow engine is proven?
- [ ] OQ-3: When concurrent REQs have interdependent cross-repo `mergeOrder`, does the script need a cross-REQ merge barrier, or is per-REQ self-merge + per-REQ rebase-onto-main sufficient (as the legacy engine assumes)?
- [ ] OQ-4: Is the built-in `min(16, cores−2)` cap + `budget.total` sufficient, or is an explicit REQ-level concurrency control needed beyond max-5 under heavy cross-repo fan-out?
- [ ] OQ-5: Should `/proceed` (single REQ) eventually share the `adlc-sprint` engine as an N=1 run? If yes, restoring Phase-4 parallelism (per-task worktrees) rises in priority.

## Out of Scope

- The Opus-4.8 agent model/effort tuning — **already shipped** in commit `8758132` (effort `xhigh` on `task-implementer`/`pipeline-runner`; `opus` on `correctness-reviewer`/`security-auditor`/`reflector`). Recorded here as completed prior work, not a deliverable.
- Removing or rewriting the legacy `/sprint` / `pipeline-runner` engine — it remains the fallback (BR-1).
- Phase-4 parallelism / per-task worktrees (deferred — see OQ-5).
- `/proceed` unification onto the workflow engine (future REQ).
- Porting the full shell-flag ghost-skip apparatus into the workflow — BR-10 replaces it with a schema contract; the legacy skill keeps its existing apparatus untouched.

## Retrieved Context

> Retrieval note: Step 1.6's delegated body-read ran (`mode=delegated`, exit 0, 148s) but returned a **truncated** summary (only a partial REQ-263 block) — a live recurrence of LESSON-010 (delegated-model silent truncation). Per the Step-1.6 coverage-reconciliation fallback, citations below were reconciled from document frontmatter and in-session reading of the load-bearing docs. Worth a follow-up: confirm whether the truncation was an `ask-kimi` output issue or a background-capture artifact.

- REQ-263 (spec, ~7): Sprint worktree isolation — the dispatch-line contract + absolute-path-from-state rule this design preserves (BR-2)
- LESSON-003 (lesson, ~7): Sprint worktree collision — the concurrency/race motivation for explicit per-REQ worktrees (BR-2, BR-3)
- BUG-060 (bug, ~5): Sprint spec-preflight base-ref — eligibility preflight + integration-branch (not hardcoded `main`) (BR-2)
- LESSON-008 (lesson, ~4): Skill-delegation untrusted data & citation sanitization — the security model the script-side validation enforces (BR-9, BR-10)
- REQ-416 (spec, ~4): Toolkit refactor / `kimi-gate` ADR-2 — the shared gate predicate the pre-pass reuses (BR-10)
- LESSON-012 (lesson, ~3): Structural telemetry beats prose enforcement — re-expressed as the `candidates ⇒ invoked` schema contract (BR-10)
- LESSON-010 (lesson, ~3): Delegated-model silent truncation & advisory anchoring — why candidates are advisory + coverage must be reconciled (BR-9; and observed in this very retrieval)
- REQ-417 (spec, ~3): Kimi skill-delegation wave 2 — origin of the Phase-5 reviewer pre-pass being re-homed (BR-8, BR-9)
- REQ-424 (spec, ~3): Skill-delegation telemetry — the ghost-skip telemetry this design preserves via `emit-telemetry.sh` (BR-10)
- REQ-380 (spec, ~2): Drop proceed Phase 7.5/8a — precedent for phase-structure changes + halt-contract (BR-4)
- LESSON-004 (lesson, ~2): Drop proceed canary/snapshot phases — halt-contract precedent (BR-4)
- LESSON-014 (lesson, ~2): Lock symlink TOCTOU — informs the Step-2 global-counter allocation used to mint this REQ
- LESSON-015 (lesson, ~2): Subshell exit does not propagate — same allocation-block hardening
- REQ-258 (spec, ~2): Unified retrieval pilot — the `/spec` retrieval mechanism that produced this section
