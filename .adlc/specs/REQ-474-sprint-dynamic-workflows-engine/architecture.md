# Architecture — REQ-474: Re-platform `/sprint` onto Dynamic Workflows

## Approach

`/sprint` becomes a **two-engine dispatcher**. Orchestration moves out of the `pipeline-runner` agent (which cannot dispatch sub-agents) and into a deterministic **`adlc-sprint` Workflow script** where agents are leaves the script dispatches. This restores per-REQ internal fan-out (explore trio, Phase-5 review panel) *while* keeping cross-REQ concurrency — the cross-product the current engine can't reach. The legacy background-`pipeline-runner` engine stays as an unchanged, always-available fallback (Dynamic Workflows is research-preview + plan-gated).

The work is **staged**: v1 ships the engine + restored review panel with the Kimi pre-pass *skipped* (matching today's `/sprint`); the target per-repo `kimi-pre-pass` agent is gated on OQ-1 (env-reachability), built but only wired in once the spike passes.

This file records the ADRs; the spec (`requirement.md`) holds the BRs/ACs the ADRs satisfy.

## Affected files (from the Step-2 exploration)

**CREATE**
- `workflows/adlc-sprint.workflow.js` — the deterministic engine as ONE self-contained file: `meta` first, the JSON-Schema literals (`REPOS`, `VERDICT`, `TASKS`, `FINDINGS`, `CANDIDATES`, `PRS`, `TERMINAL`) + all pure helpers inlined behind the `// ==== BEGIN/END PURE ====` sentinels, then the Preflight + per-REQ Phase 0–8 orchestration. (Superseded the original multi-file `schemas.js`/`helpers.js` split — see ADR-2 amendment; the runtime has no `require`.)
- `agents/kimi-pre-pass.md` — the new per-repo pre-pass leaf agent (target; gated on OQ-1).
- `workflows/tests/` — the shared `vm` loader (`_load-pure.js`) + `node:test` unit tests for the inlined pure helpers.

**MODIFY**
- `sprint/SKILL.md` — add the engine-selection dispatcher (availability + `--workflow`); legacy path otherwise unchanged. Add `argument-hint` note + "What This Does NOT Do" entry.
- `init/SKILL.md` — copy `workflows/` into consumer `.adlc/workflows/` (alongside `templates/`, `partials/`).
- `README.md` — skill catalog: note `/sprint`'s two engines.
- `.adlc/context/architecture.md` — add the "Workflow engine" + `workflows/` layout subsection (proposed addition, per Step 3.3).

**LEAVE UNTOUCHED (load-bearing boundary)**
- `proceed/SKILL.md`, `agents/pipeline-runner.md`, all reviewer/explorer/implementer agents, every `partials/*.sh` and `tools/kimi/*` (reused, not modified), `ETHOS.md`, `tools/lint-skills/*` (the new `.js`/agent files are out of its `SKILL.md`-only scope).

## Architecture Decision Records

**ADR-1 — Two engines behind one `/sprint`, not a new command.**
`/sprint` detects Dynamic Workflows availability and reads a `--workflow` flag; it dispatches the workflow engine only when `available AND (flag OR graduated-default)`, else the legacy engine. *Rationale:* Dynamic Workflows is research-preview/plan-gated and may be absent (headless/cron, non-qualifying plans), so a single command with a hard fallback preserves portability. *Alternative rejected:* a separate `/sprint-wf` command — doubles the surface and forces users to know which to call. (BR-1)

**ADR-2 — Workflow scripts live in `workflows/`, reached via the skills symlink; `/init` vendors them. The engine is ONE self-contained file.**
`~/.claude/skills → repo`, so `~/.claude/skills/workflows/adlc-sprint.workflow.js` resolves with no install change (confirmed by integration-explorer). The dispatcher resolves the path with the standard two-level fallback (`.adlc/workflows/…` → `~/.claude/skills/workflows/…`). *Rationale:* mirrors the `templates/`/`partials/` distribution model; git-tracked and versioned with the toolkit. *Alternative rejected:* inlining the full script into `Workflow({script})` from the SKILL — bloats `sprint/SKILL.md` and defeats `scriptPath` resume/iteration.
*Amendment (dogfooding finding, Rung 1):* the Dynamic-Workflows runtime has **no `require` / `import` / `fs`**, and `export const meta` must be the **FIRST statement**. A multi-file engine (`adlc-sprint.workflow.js` requiring `./schemas.js` + `./helpers.js`) therefore cannot run (`require is not defined`). The engine MUST be a **single self-contained file**: `meta` first, then all schema literals + pure helpers **inlined** behind `// ==== BEGIN PURE ====` / `// ==== END PURE ====` sentinels, ending with a guarded `if (typeof module !== 'undefined') module.exports = {…}` (skipped at runtime where `module` is undefined; populated under the test loader). The toolkit forbids a build step, so the pure logic stays inline and is tested via a shared `vm` loader (`workflows/tests/_load-pure.js`) — **no `require` of a sibling module, no bundler**. `workflows/schemas.js` and `workflows/helpers.js` are deleted.

**ADR-3 — Orchestration is the script; agents are hands.**
The Workflow primitive has no shell/filesystem, so every git/gh/file/state op runs *inside* an `agent()` call; the script owns only control flow (sequence, fan-out, loops, mergeOrder). I/O-heavy phases (0, 6, 8) are one agent each returning structured data; fan-out is spent only where it pays (Phases 2, 5). *Rationale:* this is what dissolves the "subagent can't nest" constraint. `pipeline-runner.md` is **not** reused by this engine (it stays for the legacy engine). (BR-7)

**ADR-4 — Persistent per-REQ worktree, explicit — not `isolation:'worktree'`.**
The Phase-0 agent runs `git worktree add` from `origin/<integrationBranch>` and records the absolute path in `pipeline-state.json.repos[*].worktree`; every later agent is told that path. The Workflow tool's per-agent `isolation:'worktree'` is **not** used for the REQ container (wrong lifecycle: per-agent, ephemeral). *Rationale:* preserves the REQ-263 dispatch-line/absolute-path contract, LESSON-002 cross-repo primary handling, and BUG-060/LESSON-036 integration-branch hygiene; idempotent on resume (don't recreate existing worktrees). (BR-2)

**ADR-5 — Parallelize read/report phases; serialize the writer.**
Phase 2 (explore trio) and Phase 5 (reflector + 5 reviewers) fan out; Phase 4 (implement) runs serially in the single REQ worktree — one writer, no git-index contention, `task-implementer` unchanged. *Rationale:* the only write-contention source is Phase 4; the headline win (the review panel) is read-only and safe. Per-task worktrees / Phase-4 parallelism deferred (OQ-5). (BR-3, LESSON-003)

**ADR-6 — Halt = returned value; resume = `resumeFromRunId` + `args.answers`.**
A halt returns `{terminal:'blocked', reason, detail}` and **never throws** (a throw drops the item to `null` and loses the question). The workflow completes; the orchestrator surfaces blocked REQs; the user answers; a relaunch with `resumeFromRunId` threads the reply through `args.answers[reqId]`. Only the blocked REQ's halt-prone agent prompts reference `args.answers`, so on resume only they diverge from cache — untouched and already-`merged` REQs replay (no double-merge). *Rationale:* matches today's "blocked → surface → re-engage" semantics and exploits the journal cache. (BR-4, BR-5, LESSON-004 halt-contract precedent)

**ADR-7 — Schemas replace prose-parsing; consolidation is deterministic.**
Agents return validated `FINDINGS`/`CANDIDATES`/`TERMINAL`/`VERDICT` objects. Phase-5 dedupe, cross-repo flagging, severity ranking, and the Critical-blocks gate run as plain JS in the script (no agent in the loop for the mechanical part). `merged`/`pr-ready` claims are still re-verified with `gh pr view --json state,mergedAt` before acceptance. *Rationale:* "Verify, Don't Trust" — a schema makes the terminal-contract un-violable and the gh-check keeps claim≠truth. (BR-6, BR-7)

**ADR-8 — Kimi pre-pass: v1 skip; target per-repo agent; integrity via schema contract.**
v1 skips the pre-pass (parity with today's `/sprint`, which already does — it's advisory recall, not safety). The target adds `kimi-pre-pass` (one per touched repo — the citation-scoping boundary): the **agent** does gate + diff + redaction + `ask-kimi` (I/O); the **script** does the LESSON-008 validation in JS (reject `..`, require `path ∈ changedFiles`, sanitize description) and asserts `candidates ⇒ invoked` (the ghost-skip check, replacing the shell-flag dance — LESSON-012). The agent still calls `emit-telemetry.sh` so `check-delegation.sh` stays whole (it independently unmasks mislabeled fallbacks). Untrusted Kimi stdout is never executed; reflector gets no candidates. *Rationale:* the original failure mode (a *reviewing* model skipping delegation) is designed out — the pre-pass is a single-purpose isolated agent. (BR-8, BR-9, BR-10, LESSON-008, LESSON-010, REQ-417, REQ-424)

**ADR-9 — Keep both `pipeline-state.json` and the workflow journal.**
The state file remains the durable artifact (`/status`, the legacy engine, cross-tool resume); the journal handles in-run `resumeFromRunId`. They serve different layers; neither is removed. *Rationale:* `/status` and the legacy path must keep working unchanged. (BR-11)

**ADR-10 — Testing: pure helpers get unit tests; orchestration is dogfooded.**
The deterministic helpers (`validateCitations`, `dedupeAndRank`, eligibility scoring, `args.answers` cache-key behavior) are pure functions and get unit tests under `workflows/tests/`. Because the toolkit has no JS runner today, introduce a minimal harness (Node's built-in `node:test`, invoked from a pytest-style wrapper to match `tools/*/tests` conventions, or a standalone `node --test`). The orchestration itself is dogfooded via `/sprint --workflow` on a synthetic REQ; the `kimi-pre-pass` shell reuses already-tested partials. *Rationale:* honors "tests are dogfooding" for the agentic parts while giving the security-critical validation real unit coverage (LESSON-008 is load-bearing). *Alternative rejected:* no tests / pure dogfooding — citation validation is exactly the code that must not regress.
*Amendment (dogfooding finding, Rung 1):* because the Dynamic-Workflows runtime has **no `require` / `import` / `fs`** and `meta` must be first (see ADR-2), the pure helpers are **inlined** into `adlc-sprint.workflow.js` rather than living in an importable sibling module. They are unit-tested via a shared `vm` loader (`workflows/tests/_load-pure.js`) that reads the `// ==== BEGIN/END PURE ====` section and evaluates **only that section** with the runtime globals absent, returning its `module.exports` for `node:test` — **no build step**. The loader evaluates in the host realm (`vm.runInThisContext` of a wrapped function, not a fresh VM realm) so the helpers' returned objects keep host prototypes and pass `node:assert`'s prototype-sensitive `deepStrictEqual`. Run: `node --test 'workflows/tests/*.test.js'`.
*This whole class of breakage — `require is not defined`, `meta`-must-be-first — was caught only by **dogfooding the real runtime (Rung 1)**, NOT by `node --check`, the test harnesses, or the 6-agent review (all of which passed the multi-file structure). That gap is a **LESSON candidate**: static checks and reviewers validate against assumed runtime semantics, so a "does it actually run in the target runtime?" rung is required for any new execution substrate.*

**ADR-11 — Resolve OQ-1 with a spike before wiring the pre-pass. → RESOLVED: REACHABLE / GO.**
A standalone spike (TASK-056) dispatches a trivial workflow leaf agent that runs `command -v ask-kimi` + checks `MOONSHOT_API_KEY` and reports back. If reachable, the pre-pass integration (TASK-060) proceeds; if not, BR-9 stays deferred (v1 ships skip-only) while the agent def + JS validation still land (usable when the platform allows). *Rationale:* the `pipeline-runner` prose asserts subagents can't reach the env, but a live main-session check contradicts it (LESSON-011 launchctl inheritance) — so test, don't assume. (OQ-1) **Outcome (see `oq1-spike-result.md`): REACHABLE — `ask-kimi` on `PATH`, `MOONSHOT_API_KEY` present, gate `rc=0`. GO: BR-9 is in scope; the pre-pass is wired in TASK-060 behind the flag, with an explicit `[ -n "$MOONSHOT_API_KEY" ]` leaf-boundary check + graceful skip to harden against any future leaf-spawn env divergence.**

**ADR-12 — Cross-REQ merge ordering via a post-pipeline barrier keyed on shared repos.**
Single-repo REQs self-merge in Phase 8 (no coordination). Cross-repo REQs stop at `pr-ready`; the script then walks each REQ's `mergeOrder`. When concurrent REQs touch a shared sibling repo, a small merge barrier serializes those REQs' merges (others stay parallel). *Rationale:* mirrors the legacy orchestrator's per-`mergeOrder` sequencing without forcing a global barrier. (OQ-3 resolution; OQ-4 concurrency stays on the built-in cap + `budget.total` + max-5 per BR-12)

## Workflow script structure (reference)

`runReq(id)` per-REQ chain (each REQ flows independently via `pipeline(todo, r => runReq(r.id))`):
`Phase 0 (agent: worktree+state) → gate(P1 validate) → parallel(explore×3) → agent(P2 architect/tasks) → gate(P3 validate) → for tier: serial task-implementer (P4) → verify(P5: [pre-pass per repo] → parallel(panel) → JS consolidate → fix) → agent(P6 PR) → agent(P7 cleanup/CI) → agent(P8 wrapup/merge)`. Halts return `{terminal:'blocked'}`; success returns `TERMINAL`. Pure helpers: `scoreEligibility`, `validateCitations`, `dedupeAndRank`, `advisoryBlock`.

## Lessons applied
- LESSON-003 / REQ-263 — worktree race + dispatch contract → ADR-4
- LESSON-008 / LESSON-010 — untrusted delegation + truncation/anchoring → ADR-8 (script-side validation; advisory candidates; reflector excluded)
- LESSON-012 / REQ-424 — structural telemetry → ADR-8 (schema contract + emit-telemetry backstop)
- LESSON-011 — launchctl env inheritance → ADR-11 (OQ-1 spike rationale)
- LESSON-002 / BUG-060 — cross-repo primary + integration-branch base → ADR-4, ADR-12
- LESSON-004 / REQ-380 — halt-contract / phase-removal precedent → ADR-6
- LESSON-013/014/015/019/020 — POSIX/lock/shell-state/guard-rot → applied in TASK technical notes (the `kimi-pre-pass` shell + any `sprint/SKILL.md` fences)

## Open questions
- **OQ-1** (leaf-agent `ask-kimi` reachability) — **resolved REACHABLE / GO** by the TASK-056 spike (ADR-11, `oq1-spike-result.md`): the pre-pass is in scope and wired in TASK-060 (no longer skip-only).
- **OQ-2** (single state source) — deferred; ADR-9 keeps both for now.
- **OQ-3** (cross-REQ merge ordering) — resolved by ADR-12.
- **OQ-4** (concurrency ceiling) — resolved: built-in cap + `budget.total` + max-5 (BR-12).
- **OQ-5** (`/proceed` N=1 unification) — out of scope; revisit after v1 proves the engine.
