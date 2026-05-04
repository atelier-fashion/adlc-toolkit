# Project Overview — ADLC Toolkit

## What this project is

The ADLC Toolkit is a library of **skills, agents, and templates** that enable spec-driven development with Claude Code. It is the source of `/spec`, `/architect`, `/proceed`, `/review`, `/bugfix`, and other skills that consumer projects use to run their own Agentic Development Life Cycle (ADLC) pipelines.

This repo is itself a consumer of the toolkit only in the narrow sense that its own feature work is tracked in `.adlc/specs/` — but it does NOT have the full consumer scaffold. No `.adlc/knowledge/lessons/`, `.adlc/bugs/`, or `.adlc/templates/` directory inside this repo (those live in consumer projects after `/init`). The toolkit's canonical `templates/` directory at the repo root is what `/init` copies into consumer projects.

## Who uses it

- **Consumer projects** (e.g., `~/Documents/GitHub/atelier-fashion`) symlink this repo to `~/.claude/skills/` and `~/.claude/agents/`. Any improvement committed here is immediately visible to every Claude Code session on the machine — no publish step.
- **Toolkit maintainers** (Brett) evolve the skills, add new ones, and fix bugs in the skill definitions themselves. REQs tracked here describe changes to the toolkit's own surface area: skill behavior, template schemas, agent prompts, documentation.

## Install model

Symlink-based live install. One canonical git clone on disk, symlinked at `~/.claude/skills/`. Edits to the clone are visible immediately. No separate installed copy, no sync step, no versioning at the install layer. This matters because skill changes committed here take effect for every project on the machine the instant they land.

## Primary surface areas

| Surface | Files | Purpose |
|---|---|---|
| Skills | `<skill-name>/SKILL.md` | Markdown files invoked by Claude Code as slash commands |
| Agents | `agents/<agent-name>.md` | Specialized subagent definitions with tool restrictions and model selection |
| Templates | `templates/*.md` | Canonical templates for requirements, bugs, lessons, tasks, assumptions |
| Ethos | `ETHOS.md` | Five principles injected into every skill — the non-negotiable constitution |
| Docs | `README.md` | Install instructions and skill catalog |

## Relationship to consumer projects

`/init` is the bridge: when a consumer project runs `/init`, it creates `.adlc/context/`, `.adlc/specs/`, `.adlc/bugs/`, `.adlc/knowledge/`, and `.adlc/templates/` in that project, copying from the toolkit's `templates/` directory. After `/init`, the consumer project uses skills that read from **its** `.adlc/` structure — not the toolkit's.

The toolkit's own `.adlc/` (containing only `specs/` and `context/`) is minimal by design. The toolkit doesn't track lessons or bugs for itself yet; that may change if the toolkit's internal work grows.

## Current scope

As of 2026-04-19, the toolkit tracks its own feature work starting with REQ-258 (unified tag-based retrieval for `/spec`). Prior toolkit changes were tracked only in git history and PR descriptions. REQ-258 onward, the toolkit dogfoods its own spec-driven process at a minimal level.

## REQ-numbering policy (cross-project global counter)

As of REQ-380 (2026-05-04), this repo and atelier-fashion share a **global** REQ counter. Future REQ allocations from adlc-toolkit MUST take the next slot above the global high-water (currently anchored by atelier-fashion's REQ-380), not above adlc-toolkit's local high-water of REQ-263.

Rationale: a single REQ id should resolve to one work item across every repo on the machine, so cross-repo references (links, lessons, branch names, PR titles) are unambiguous. atelier-fashion's `~/.claude/.global-next-req` counter is the source of truth; adlc-toolkit reads from the same file.

Existing toolkit specs (REQ-258, REQ-262, REQ-263) keep their numbers — the policy applies to new allocations only. The intentional gap from REQ-264 through REQ-379 is the price of fast-forwarding to the global counter.

Paired doc on the consumer side: atelier-fashion's `CLAUDE.md` "Cross-Project Considerations" section (shipped in atelier-fashion REQ-379, PR #774, merged 2026-05-04).
