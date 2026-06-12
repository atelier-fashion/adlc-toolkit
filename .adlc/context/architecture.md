# Architecture — ADLC Toolkit

## Top-level layout

```
adlc-toolkit/
├── ETHOS.md                    # the ETHOS principles — injected into every skill
├── README.md                   # Install + skill catalog
├── <skill>/SKILL.md            # One directory per skill (spec/, architect/, proceed/, etc.)
├── agents/<agent>.md           # Specialized subagent definitions
├── templates/*.md              # Canonical templates (copied into consumer projects by /init)
├── partials/                   # Shared snippets (ethos macro, delegate gate, trial-merge) sourced by SKILL.md files
├── workflows/                  # Deterministic Dynamic Workflow scripts + schemas (copied into consumer projects by /init)
└── .adlc/                      # Minimal self-tracking for toolkit-internal REQs
    ├── context/                # This directory — project-overview, architecture, conventions
    └── specs/REQ-xxx-*/        # Requirement specs for toolkit changes
```

## Skill anatomy

Every skill is a single markdown file at `<skill-name>/SKILL.md` with this shape:

1. **Frontmatter**: `name`, `description`, optional `argument-hint`
2. **Title + one-line framing** — what the skill does
3. **Ethos injection**: `!`cat .adlc/ETHOS.md ...` bash macro that inlines the ETHOS principles at invocation time (consumer-project path preferred, toolkit-root path as fallback)
4. **Context loading**: explicit `!bash` commands to read project-overview, architecture, conventions, relevant knowledge
5. **Input**: how the skill reads `$ARGUMENTS`
6. **Prerequisites**: blocking checks (e.g., "verify `.adlc/context/project-overview.md` exists")
7. **Instructions**: numbered steps, often with sub-steps and explicit bash for deterministic operations (each ```sh fenced block may be an independent shell — a shared shell function must be re-sourced from a partial in the same block that calls it; see "Partials")
8. **Quality checklist**: post-run self-check items

Skills are pure markdown — no code, no package dependencies. Claude Code loads them at invocation time and executes the instructions in-context.

## Agent anatomy

Agents live in `agents/<agent-name>.md` and have frontmatter declaring:
- `name` — identifier used when dispatching
- `description` — tells the parent agent when to use this one
- `tools` — explicit allowlist (or `*` for general-purpose agents)
- `model` — optional override (e.g., `sonnet`, `haiku`) for cost/speed tuning

Agent bodies contain specialized instructions: role, focus areas, reporting format. The `/review` and `/proceed` skills dispatch multiple review-style agents in parallel (correctness-reviewer, quality-reviewer, architecture-reviewer, test-auditor, security-auditor, reflector).

## Template anatomy

Templates at `templates/*.md` are the canonical shape for each artifact type:

- `requirement-template.md` — REQ specs (id, title, status, deployable, dates; Description, System Model, Business Rules, Acceptance Criteria, etc.)
- `task-template.md` — implementation tasks (id, title, req, status, dependencies)
- `bug-template.md` — bug reports (id, title, status, severity, dates; Description, Reproduction, Root Cause, Resolution)
- `lesson-template.md` — lessons learned (id, title, domain, component, tags, req, created)
- `assumption-template.md` — validated-assumption knowledge entries
- `taxonomy-template.md` — tag/taxonomy reference used by the retrieval tagging

The `templates/` directory is authoritative for the full set (it also carries the non-`.md` `config-template.yml` and `claude-settings-template.json`); the list above describes the per-artifact `*.md` templates and may lag the directory — prefer `ls templates/` when an exact roster matters.

Templates are copied into consumer projects by `/init` (into `.adlc/templates/`). Consumer projects may customize their local copies; `/template-drift` detects divergence from the canonical set.

## Partials

Partials at `partials/*.sh` are small POSIX shell snippets sourced by multiple SKILL.md files via Claude Code's `!`...`` macro syntax. Each partial emits a context block to stdout (e.g., `ethos-include.sh` emits the project ETHOS.md content with the consumer-project-first fallback). Skills invoke a partial with a two-level fallback — `!`sh .adlc/partials/<name>.sh 2>/dev/null || sh ~/.claude/skills/partials/<name>.sh`` — so the pattern works whether or not `/init` has copied the partials into the consumer repo. The `/init` skill copies `partials/` into `.adlc/partials/` alongside `templates/`. Keep partials trivially auditable: one snippet per file, no aggregator (`lib.sh`) until there are more than five.

A sourceable partial is also the **only** sanctioned mechanism for sharing a shell *function* across steps, because SKILL.md fenced blocks do not share shell state across steps — each may be an independent shell invocation, so a function defined in one fenced block is undefined in another (the silent telemetry-loss class — REQ-436, REQ-428). A shared function (e.g. `_adlc_emit_step_telemetry` in `partials/emit-step-telemetry.sh`, alongside the `delegate-gate.sh` precedent) must be re-sourced at *each* call site in the same fenced block as its invocation. This invariant is enforced structurally rather than by prose (LESSON-012): the `tools/lint-skills` `cross-fence-fn` check flags any function defined in one fence but called from a different fenced block. See conventions.md "Bash in skills" for the call-site rule.

## ADLC pipeline shape (consumer-project view)

When a consumer project runs `/proceed REQ-xxx`, the pipeline phases are:

```
/validate (spec)
   ↓
/architect  ← creates .adlc/specs/REQ-xxx/tasks/TASK-yyy.md
   ↓
/validate (architecture + tasks)
   ↓
Implement (parallel task-implementer agents)
   ↓
/verify (reflector + 5 reviewer agents in parallel)
   ↓
/review findings fixed in single pass
   ↓
Create PR
   ↓
PR cleanup + CI
   ↓
/wrapup (merge, artifact updates, knowledge capture, deploy)
```

Each phase has a validation gate. Failed validation loops up to 3 times before pausing for human input.

`proceed/SKILL.md` keeps Step 0, the Pipeline State Tracking gate protocol, and Phase 5 (Verify, with the delegate pre-pass gate) inline, but extracts the thinner phases to companion files referenced via `<!-- companion: <path> -->` markers in SKILL.md:

- `proceed/phases-1-3-validation.md` — Phases 1–3 (spec validation, architect, architecture/tasks validation)
- `proceed/phase-4-implementation.md` — Phase 4 (implement)
- `proceed/phases-6-8-ship.md` — Phases 6–8 (PR creation, cleanup/CI, wrapup/merge)

The companion marker is documentation-only — Claude Code does not auto-load referenced files. SKILL.md's inline summary is sufficient to execute each extracted phase; the companion holds the full step list for maintainers and for in-depth reference. Phase 5 is intentionally not extracted (ADR-3 of REQ-416) because the delegate pre-pass gate-handoff is load-bearing.

## Workflow engine

Some orchestration is too dispatch-heavy for a single subagent (a subagent cannot nest further subagents). For those cases the toolkit ships **deterministic Dynamic Workflow scripts** under `workflows/` — a JS orchestration script plus the JSON-Schema literals it validates agent output against. Scripts are reached via the skills symlink (`~/.claude/skills/workflows/<name>.workflow.js`) and `/init` vendors them into a consumer's `.adlc/workflows/` alongside `templates/` and `partials/`. A skill resolves a script with the same **two-level fallback** used everywhere else — consumer copy first (`.adlc/workflows/<name>.workflow.js`), toolkit-symlink copy as fallback (`~/.claude/skills/workflows/<name>.workflow.js`) — so it works whether or not `/init` has run.

**Agents are leaves; the script is the orchestrator.** The Workflow primitive has no shell or filesystem of its own, so every git/gh/file/state operation runs *inside* an `agent()` call; the script owns only control flow (sequence, fan-out, loops, merge ordering). This is the model that dissolves the "a subagent can't dispatch subagents" constraint: the script dispatches the leaves and parallelizes the read/report phases that pay for fan-out while serializing the single writer.

**`/sprint` is a two-engine dispatcher.** It selects the **workflow** engine only when the `Workflow` tool is actually invocable in the session **and** the run opts in (`--workflow`, or once the engine graduates to default); otherwise it uses the **legacy** background-runner engine with no behavior change. Dynamic Workflows is a research-preview, plan-gated capability that can be absent (headless/cron runs, non-qualifying plans), so the legacy engine is an always-available, unchanged fallback — the dispatcher degrades to it (with an explicit notice) rather than failing when the workflow engine is requested but unavailable.

**State has two layers.** The durable `pipeline-state.json` remains the cross-tool artifact that `/status` and the legacy engine read and that survives across sessions; the workflow **journal** is the in-run cache that powers `resumeFromRunId` (answer-a-halt-and-relaunch) within a single workflow run. They serve different layers and neither replaces the other — keeping `pipeline-state.json` is what lets `/status` and the legacy path keep working unchanged.

## Knowledge retrieval (current and evolving)

Skills retrieve relevant prior knowledge at context-loading time. The current implementation is a **3-tier grep** over `.adlc/knowledge/lessons/*.md` frontmatter (component > domain+prefix > tag), used by `/review` and `/spec`. REQ-258 upgrades this to a **weighted-score retriever** over three corpora (lessons + specs + bugs), pooled globally to top-15 rather than per-corpus capped.

## Key cross-cutting dependencies

- **Atomic REQ counter**: `~/.claude/.global-next-req` is a shared counter across all consumer repos to guarantee unique REQ IDs. Protected by a POSIX `mkdir`-based lock at `~/.claude/.global-next-req.lock.d` for concurrent-safe increments. The lock acquisition pre-checks `[ -L "$LOCK" ]` and refuses to run if the path is a symlink, defending against a TOCTOU symlink-swap that would otherwise let an attacker redirect `mkdir`/`rmdir` traffic (LESSON-014, REQ-416 ADR-4).
- **Atomic BUG counter**: `~/.claude/.global-next-bug` is the cross-repo machine-global counter for BUG IDs (REQ-441), allocated by `/bugfix` Phase 1 with the *same* `mkdir`-lock + `[ -L "$LOCK" ]` symlink pre-check + fail-loud guards as the global REQ counter — a faithful mirror of the `/spec` Step 2 pattern (the per-repo `.adlc/.next-bug` is deprecated, ignored if present). BUG ids therefore resolve to one work item across every repo, like REQ ids.
- **Atomic LESSON counter**: `~/.claude/.global-next-lesson` is the cross-repo machine-global counter for LESSON IDs (REQ-473), allocated by BOTH `/wrapup` (Step 4) and `/bugfix` (lesson capture) with the *same* `mkdir`-lock + `[ -L "$LOCK" ]` symlink pre-check + fail-loud guards as the global REQ/BUG counters — a faithful mirror of the `/spec` Step 2 pattern. The two skills deliberately share the single global lock `~/.claude/.global-next-lesson.lock.d` so concurrent `/wrapup` and `/bugfix` runs mutually exclude and cannot double-allocate a LESSON id. LESSON ids therefore resolve to one work item across every repo, like REQ and BUG ids (the per-repo `.adlc/.next-lesson` is deprecated, ignored if present).
- **Atomic per-project counter**: `.adlc/.next-assume` (ASSUME ids) is a per-project counter that prevents concurrent `/sprint` pipelines from double-allocating ids during wrapup. It is protected by the same `mkdir`-lock + symlink pre-check pattern as the global counters (lock dir `.adlc/.next-assume.lock.d`). ASSUME ids stay per-project because they are minted only by `/wrapup` within a single repo and have no cross-repo reference surface.
- **Worktree isolation**: `/proceed` creates a git worktree per REQ at `.worktrees/REQ-xxx` so multiple pipelines run without collision. `/sprint` orchestrates parallel worktrees.
- **Symlink install**: changes committed to this repo are live immediately for every Claude Code session on the machine. No build, no deploy.
- **Cross-session visibility (REQ-482)**: `/manifest` derives a read-only view of all in-flight ADLC work from the **remote** (open PRs + pushed `feat/REQ-*` branches), complementing `/status` (which sees only the local checkout). It is wired advisorily into `/proceed` Step 0 and `/sprint` pre-flight and never blocks — the visibility half of multi-human coordination; the enforcement half landed in REQ-483 (next).
- **Ordering enforcement (REQ-483)**: `/proceed` opens a **draft PR at Step 0**; `/architect` publishes the file footprint into the PR body (a fenced `adlc-footprint` block); `/manifest` reads footprints back and derives a **deterministic, lock-free merge order** (earliest-published PR wins, lower REQ tiebreak). Footprint overlap is advisory; the **hard gate** is a non-mutating trial-merge (`partials/trial-merge.sh`) that blocks `/proceed` / holds a `/sprint` merge only on a real git conflict — so different edits to the same file merge cleanly. Resolution is rebase, never merge-anyway.
- **Self-healing serialization (REQ-485)**: when a `/sprint` run merges blocker REQ-A, the orchestrator auto-rebases each REQ held with `blockedBy == A` onto the refreshed integration branch and resumes it from `currentPhase` (clean rebase → resume; conflicting rebase → `--abort` + re-halt with materialized conflict files, never auto-resolved), so an unattended batch self-heals REQ-483's `blocked` holds. Deterministic, serialized one-at-a-time, retry-bounded (`auto_rebase_max_attempts`, default 1), and anchored on the still-present `blockers` entry (cleared on resume-to-merge, BR-11). Scope is within-run only — cross-session blockers and solo `/proceed` stay manual.
- **Forge adapter (REQ-520)**: `partials/forge.sh` is the single home of `gh`/`az` PR-lifecycle commands — a sourceable partial exposing `adlc_forge_pr_{create,ready,edit,view,list,merge,comment}` with GitHub (`gh`) and Azure DevOps (`az repos`) backends and an `ADLC_FORGE_MOCK=1` offline fixture backend. Provider resolution (per-project `.adlc/config.yml` `forge.provider` > machine config > `auto` origin-URL detection, fail-loud on unrecognized host) and the key-shaped-`auth` refusal live in `tools/adlc/forge_config.py` (a thin flat-YAML reader mirroring `parse_delegate_config` — no shell YAML parsing, REQ-515 ADR-3). Every PR-lifecycle call site in `/proceed`, `/architect`, `/manifest`, `/bugfix`, `/wrapup`, `/sprint`, and the sprint workflow routes through the adapter; `tools/lint-skills`'s `forge-direct-gh` check rejects new direct `gh pr <op>` in skill fences. The GitHub backend is byte-compatible with the prior direct calls (zero change for GitHub installs). `adlc doctor`'s `forge` check (in `tools/adlc/checks.py`) **supersedes** the former standalone `gh-auth` check — it resolves the provider and probes the right backend's CLI + auth + a read-only API probe, SKIP-with-reason on a remote-less repo. `gh pr diff`/`gh pr checks` (CI polling is out of scope) and the REQ-518 `id-alloc`/`id-recheck` `gh api` tree reads (BR-8 pure-git merged-artifact scan, not a PR op) stay direct.
