# Project Overview — ADLC Toolkit

## What this project is

The ADLC Toolkit is a library of **skills, agents, and templates** that enable spec-driven development with Claude Code. It is the source of `/spec`, `/architect`, `/proceed`, `/review`, `/bugfix`, and other skills that consumer projects use to run their own Agentic Development Life Cycle (ADLC) pipelines.

This repo dogfoods the toolkit on its own feature work: REQs in `.adlc/specs/`, lessons in `.adlc/knowledge/lessons/`, and bugs in `.adlc/bugs/`. It does not carry the full consumer scaffold — there is no `.adlc/templates/` directory inside this repo, because the canonical `templates/` directory at the repo *root* is the source `/init` copies into consumer projects (a vendored `.adlc/templates/` copy here would just shadow it). Knowledge and bug tracking, by contrast, ARE present and active.

## Who uses it

- **Consumer projects** (e.g., `~/Documents/GitHub/atelier-fashion`) get the toolkit by one of the two install routes below. Plugin users run a pinned release and move to a new one when it is tagged and they update. A machine on the symlink route (this repo linked at `~/.claude/skills/` and `~/.claude/agents/`) sees any improvement committed here in every Claude Code session immediately, with no publish step.
- **Toolkit maintainers** (Brett) evolve the skills, add new ones, and fix bugs in the skill definitions themselves. REQs tracked here describe changes to the toolkit's own surface area: skill behavior, template schemas, agent prompts, documentation.

## Install model

Two routes (REQ-669). One skill text serves both, and a machine should use one of them, not both.

- **Plugin route (users).** This repo is both a Claude Code marketplace (`adlc-toolkit`) and the plugin (`adlc`). `claude plugin marketplace add atelier-fashion/adlc-toolkit`, then `claude plugin install adlc@adlc-toolkit`, copies a release into `~/.claude/plugins/cache/adlc-toolkit/adlc/<version>/`. The plugin's `version` is pinned to `VERSION`, so the install layer is versioned on this route. Users move only when a release is tagged and they run `claude plugin update` (`RELEASING.md` is the release sequence). Skills are `/adlc:<skill>` and agents `adlc:<name>`. A SessionStart hook records the plugin root in `~/.claude/adlc/plugin-root`, scaffolds a delegation-off `~/.claude/adlc/config.yml` when none exists, and puts `scripts/adlc` on the session's PATH.
- **Symlink route (contributors and the maintainer).** One canonical git clone on disk, linked at `~/.claude/skills/` and `~/.claude/agents/` by `install.sh`. Edits to the clone are visible immediately, with no separate installed copy and no sync step. This matters because a skill change committed here takes effect for every project on such a machine the instant it lands, while plugin users get it at the next release.

Every toolkit-owned file a skill, partial, agent, workflow or tool reads resolves through **ToolkitRoot** (`$ADLC_TOOLKIT_ROOT`): the clone on the symlink route, the cache copy on the plugin route (see architecture.md "Install routes"). Machine state, meaning the id counters, their locks, `~/.claude/adlc/config.yml` and the telemetry log, stays where it is and is shared by both routes. Both routes active on one machine is a doubled install, which `adlc doctor` reports.

## Primary surface areas

| Surface | Files | Purpose |
|---|---|---|
| Skills | `<skill-name>/SKILL.md` | Markdown files invoked by Claude Code as slash commands |
| Agents | `agents/<agent-name>.md` | Specialized subagent definitions with tool restrictions and model selection |
| Templates | `templates/*.md` | Canonical templates for requirements, bugs, lessons, tasks, assumptions |
| Ethos | `ETHOS.md` | The ETHOS principles injected into every skill — the non-negotiable constitution |
| Docs | `README.md`, `RELEASING.md` | Install instructions for both routes (plugin first), the skill catalog, and the maintainer's release and directory-submission sequence |
| Plugin | `.claude-plugin/`, `hooks/`, `scripts/` | The plugin and marketplace manifests, the SessionStart hook, and the `scripts/adlc` CLI shim (REQ-669) |

## Relationship to consumer projects

`/init` is the bridge: when a consumer project runs `/init`, it creates `.adlc/context/`, `.adlc/specs/`, `.adlc/bugs/`, `.adlc/knowledge/`, and `.adlc/templates/` in that project, copying from the toolkit's `templates/` directory. After `/init`, the consumer project uses skills that read from **its** `.adlc/` structure — not the toolkit's.

The toolkit's own `.adlc/` is intentionally lean but no longer minimal: it tracks `specs/`, `context/`, `knowledge/lessons/`, and `bugs/` for the toolkit's own work. It deliberately omits a vendored `templates/` copy (the root `templates/` is authoritative). The toolkit dogfoods its own lesson- and bug-capture process the same way a consumer project does.

## Current scope

The toolkit dogfoods its own spec-driven process: feature work is tracked in `.adlc/specs/` (starting with REQ-258, unified tag-based retrieval for `/spec`), lessons in `.adlc/knowledge/lessons/`, and bugs in `.adlc/bugs/`. Toolkit changes before REQ-258 live only in git history and PR descriptions. The current epoch is **5.x ("Works anywhere")** — see `VERSION` and `CHANGELOG.md`, which are authoritative for what has shipped; this overview deliberately does not re-enumerate the changelog (enumerations rot — LESSON-019).

## REQ-numbering policy (remote-derived, collision-safe)

Numbering is **remote-derived** as of REQ-518: a new id is `max(local-cache, remote-high-water) + 1`, computed by the shared `partials/id-alloc.sh` (allocation) and rechecked at push/PR time by `partials/id-recheck.sh`. The remote is the source of truth; the per-machine `~/.claude/.global-next-req` counter is a fast-forwarded *cache*, not the authority. This makes ids collision-safe across multiple users and machines, not just across repos on one machine. The same pattern allocates BUG ids (`~/.claude/.global-next-bug`) and LESSON ids (`~/.claude/.global-next-lesson`).

Rationale: a single id should resolve to one work item across every repo and every contributor, so cross-repo references (links, lessons, branch names, PR titles) are unambiguous. Deriving the high-water from the remote rather than trusting a local counter is what makes that hold when several people allocate concurrently.

*Historical note:* the global counter began (REQ-380, 2026-05-04) as a per-machine file shared between adlc-toolkit and atelier-fashion, fast-forwarded past adlc-toolkit's then-local high-water of REQ-263 (leaving the intentional REQ-264..379 gap). REQ-518 generalized that machine-local counter into the remote-derived scheme above. Existing toolkit specs (REQ-258, REQ-262, REQ-263) keep their original numbers.
