# ADLC Toolkit

Shared skills and templates for spec-driven development with Claude Code.

## What's Included

### Skills

| Skill | Description |
|-------|-------------|
| `/init` | Bootstrap `.adlc/` structure in a new repo |
| `/spec` | Write requirement specs from feature requests |
| `/architect` | Design architecture and break requirements into tasks |
| `/validate` | Validate any ADLC phase output before advancing |
| `/proceed` | End-to-end pipeline: validate → architect → implement → reflect → review → PR → wrapup |
| `/sprint` | Parallel pipeline orchestrator — launch multiple `/proceed` sessions across REQs |
| `/reflect` | Post-implementation self-review before formal review |
| `/review` | Multi-agent code review (correctness, quality, architecture, tests, security) |
| `/canary` | Canary deployment with smoke tests — deploy zero-traffic revision and promote on success |
| `/wrapup` | Close out a feature — commit, merge, deploy, update artifacts |
| `/bugfix` | Streamlined bug fix workflow |
| `/status` | Show current state of all ADLC work |
| `/analyze` | Codebase health audit |
| `/optimize` | API cost & performance scanner |
| `/template-drift` | Detect drift between a project's local `.adlc/templates/` and the canonical toolkit templates |

### Templates

- `requirement-template.md` — Requirement spec template
- `task-template.md` — Technical task template
- `bug-template.md` — Bug report template
- `assumption-template.md` — Validated-assumption knowledge entry
- `lesson-template.md` — Lesson-learned knowledge entry

## Setup

This toolkit uses a **symlink-based live install**: one canonical git clone on disk, exposed to Claude Code at `~/.claude/skills/` via an absolute-path symlink. There is no separate "installed" copy and no sync step — edits you commit to the clone are instantly visible to every Claude Code session on the machine.

### 1. Clone this repo

```bash
cd ~/Documents/GitHub  # or wherever you keep repos
git clone https://github.com/atelier-fashion/adlc-toolkit.git
```

### 2. Symlink to Claude Code's skills and agents directories

```bash
# Back up any existing directories (rename is safe and reversible)
[ -e ~/.claude/skills ] && mv ~/.claude/skills ~/.claude/skills.bak
[ -e ~/.claude/agents ] && mv ~/.claude/agents ~/.claude/agents.bak

# Create symlinks — use ABSOLUTE paths so they resolve from any cwd
ln -s "$HOME/Documents/GitHub/adlc-toolkit" "$HOME/.claude/skills"
ln -s "$HOME/Documents/GitHub/adlc-toolkit/agents" "$HOME/.claude/agents"
```

Verify:

```bash
readlink ~/.claude/skills   # → /Users/<you>/Documents/GitHub/adlc-toolkit
readlink ~/.claude/agents   # → /Users/<you>/Documents/GitHub/adlc-toolkit/agents
ls ~/.claude/skills/review/SKILL.md  # should resolve through the symlink
```

Git commands run from inside `~/.claude/skills/` transparently operate on the clone's `.git` directory, so you can use either path interchangeably.

### 3. Initialize a project

In any code repo:

```bash
claude
> /init
```

This bootstraps the `.adlc/` directory with project-specific context, specs, and copies of the templates.

## Workflow

```
/spec → /validate → /architect → /validate → implement → /reflect → /review → merge → /wrapup
```

For bugs: `/bugfix` (report → analyze → fix → verify)

## Project Structure

After `/init`, each code repo will have:

```
.adlc/
  config.yml         # (Optional) Cross-repo configuration — see below
  context/           # Project-specific architecture, conventions, overview
  specs/             # Requirement docs, architecture docs, tasks
  knowledge/         # Assumptions validated, lessons learned
  templates/         # Copies of templates (from this toolkit)
```

The toolkit repo contains the **process** (skills + templates). Each code repo contains the **artifacts** (specs, architecture, knowledge).

## Cross-Repo REQs

Some features span multiple repos (e.g., an admin control plane that touches a backend API, a mobile app, and a web app). The toolkit supports these via an optional `.adlc/config.yml` in each participating repo.

### Key concept: "primary" is per-REQ

There is no fixed "primary repo." Whichever repo you invoke `/proceed` (or `/bugfix`) from becomes the primary for that REQ — it holds the spec, tasks, and `pipeline-state.json` for that work. A different REQ that originates in a sibling repo makes that sibling the primary. Every repo that may originate REQs gets its own `.adlc/` structure and its own `config.yml`; the configs are **mirror images** of each other (each repo marks itself `primary: true` and lists the others as siblings).

### config.yml shape

```yaml
repos:
  admin-api:
    primary: true       # only in this repo's config
  infrastructure:
    path: ../infrastructure
  atelier-fashion:
    path: ../atelier-fashion
  atelier-web:
    path: ../atelier-web

merge_order:            # default Phase 8 merge sequence
  - infrastructure
  - admin-api
  - atelier-fashion
  - atelier-web

services:               # consumed by /canary, keyed by repo id
  admin-api:
    cloud_run_service: admin-api
    region: us-central1
    image_path: us-central1-docker.pkg.dev/<gcp-project>/admin-api/admin-api
  # (infrastructure has no service entry — it deploys via Terraform)
```

See [`templates/config-template.yml`](templates/config-template.yml) for the full annotated template.

### What changes when cross-repo is configured

- `/proceed` creates a worktree in every touched sibling, routes tasks by `repo:` frontmatter, opens one PR per repo, and merges in `merge_order`
- `/architect` requires a `repo:` field on every task it generates
- `/validate` checks that `repo:` values resolve to configured repo ids and that task files stay in their declared repo
- `/wrapup` walks `mergeOrder` to land PRs in order and cleans up worktrees across every touched repo
- `/canary` resolves service metadata from `services:` instead of a hardcoded table
- `/status` reports cross-repo activity (REQs originating elsewhere that touch this repo)
- `/sprint` delegates cross-repo mechanics to each `/proceed`; one sprint still originates all REQs from the invoking repo
- `/bugfix` supports cross-repo bugs via `repo:` or `touched_repos:` on the bug frontmatter

### Single-repo mode (default)

If no `config.yml` exists or it has only a single `repos:` entry, every skill falls back to legacy single-repo behavior. Existing projects are unaffected until they opt in by creating `config.yml`.

## Updating

Pull the latest toolkit to update all skills across all projects:

```bash
cd ~/Documents/GitHub/adlc-toolkit
git pull
```

Since `~/.claude/skills` is a symlink, changes are picked up immediately.
