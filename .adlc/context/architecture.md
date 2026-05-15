# Architecture — ADLC Toolkit

## Top-level layout

```
adlc-toolkit/
├── ETHOS.md                    # 5 principles — injected into every skill
├── README.md                   # Install + skill catalog
├── <skill>/SKILL.md            # One directory per skill (spec/, architect/, proceed/, etc.)
├── agents/<agent>.md           # Specialized subagent definitions
├── templates/*.md              # Canonical templates (copied into consumer projects by /init)
└── .adlc/                      # Minimal self-tracking for toolkit-internal REQs
    ├── context/                # This directory — project-overview, architecture, conventions
    └── specs/REQ-xxx-*/        # Requirement specs for toolkit changes
```

## Skill anatomy

Every skill is a single markdown file at `<skill-name>/SKILL.md` with this shape:

1. **Frontmatter**: `name`, `description`, optional `argument-hint`
2. **Title + one-line framing** — what the skill does
3. **Ethos injection**: `!`cat .adlc/ETHOS.md ...` bash macro that inlines the five principles at invocation time (consumer-project path preferred, toolkit-root path as fallback)
4. **Context loading**: explicit `!bash` commands to read project-overview, architecture, conventions, relevant knowledge
5. **Input**: how the skill reads `$ARGUMENTS`
6. **Prerequisites**: blocking checks (e.g., "verify `.adlc/context/project-overview.md` exists")
7. **Instructions**: numbered steps, often with sub-steps and explicit bash for deterministic operations
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

Templates are copied into consumer projects by `/init` (into `.adlc/templates/`). Consumer projects may customize their local copies; `/template-drift` detects divergence from the canonical set.

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

## Knowledge retrieval (current and evolving)

Skills retrieve relevant prior knowledge at context-loading time. The current implementation is a **3-tier grep** over `.adlc/knowledge/lessons/*.md` frontmatter (component > domain+prefix > tag), used by `/review` and `/spec`. REQ-258 upgrades this to a **weighted-score retriever** over three corpora (lessons + specs + bugs), pooled globally to top-15 rather than per-corpus capped.

## Key cross-cutting dependencies

- **Atomic REQ counter**: `~/.claude/.global-next-req` is a shared counter across all consumer repos to guarantee unique REQ IDs. Protected by a POSIX `mkdir`-based lock at `~/.claude/.global-next-req.lock.d` for concurrent-safe increments. The lock acquisition pre-checks `[ -L "$LOCK" ]` and refuses to run if the path is a symlink, defending against a TOCTOU symlink-swap that would otherwise let an attacker redirect `mkdir`/`rmdir` traffic (LESSON-013, REQ-416 ADR-4).
- **Atomic per-project counters**: `.adlc/.next-lesson` (LESSON ids) and `.adlc/.next-assume` (ASSUME ids) are per-project counters that prevent concurrent `/sprint` pipelines from double-allocating ids during wrapup. Both are protected by the same `mkdir`-lock + symlink pre-check pattern as the global REQ counter (lock dirs `.adlc/.next-lesson.lock.d` and `.adlc/.next-assume.lock.d`). `/wrapup` and `/bugfix` deliberately share the `.next-lesson.lock.d` path so they mutually exclude when both run concurrently against the same repo.
- **Worktree isolation**: `/proceed` creates a git worktree per REQ at `.worktrees/REQ-xxx` so multiple pipelines run without collision. `/sprint` orchestrates parallel worktrees.
- **Symlink install**: changes committed to this repo are live immediately for every Claude Code session on the machine. No build, no deploy.
