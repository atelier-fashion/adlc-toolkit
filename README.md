# ADLC Toolkit

Skills, agents, and templates for spec-driven development with [Claude Code](https://claude.com/claude-code). Stack-agnostic at the core, with optional preset configs for common stacks (iOS+Firebase+Cloud Run, etc.).

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

### Presets

Stack-shaped starter configs that seed `.adlc/config.yml` for common stacks. See [`presets/`](presets/) for the current list.

## How it works

The toolkit is split into two layers:

1. **The toolkit repo** (this repo) — generic skills, agents, and templates that work for any stack. Symlinked into `~/.claude/skills/` so every Claude Code session sees them.
2. **Per-project `.adlc/` directory** — lives in each code repo. Holds the project's specs, architecture, conventions, and a `config.yml` that declares the project's stack, deploy targets, and repo layout. **All project-specific values live here**, never in the toolkit.

Skills read `.adlc/config.yml` at runtime to resolve project-specific things (GCP project IDs, iOS device names, Cloud Run service names, etc.) — nothing is hardcoded in the skills themselves.

## Setup

The toolkit uses a **symlink-based live install**: one canonical git clone on disk, exposed to Claude Code at `~/.claude/skills/` via an absolute-path symlink. There is no separate "installed" copy and no sync step — edits you commit to the clone are instantly visible to every Claude Code session on the machine.

### 1. Clone this repo

Pick any directory you keep code in. The toolkit doesn't care where it lives, as long as the symlink in step 2 uses an absolute path.

```bash
cd ~/code  # or wherever you keep repos — anywhere works
# Replace <owner> with the canonical upstream's GitHub owner (or your fork's)
git clone https://github.com/<owner>/adlc-toolkit.git
```

### 2. Symlink to Claude Code's skills and agents directories

```bash
# Back up any existing directories (rename is safe and reversible)
[ -e ~/.claude/skills ] && mv ~/.claude/skills ~/.claude/skills.bak
[ -e ~/.claude/agents ] && mv ~/.claude/agents ~/.claude/agents.bak

# Create symlinks — use ABSOLUTE paths so they resolve from any cwd.
# Replace the source path with wherever you cloned the toolkit.
TOOLKIT="$PWD/adlc-toolkit"
ln -s "$TOOLKIT" "$HOME/.claude/skills"
ln -s "$TOOLKIT/agents" "$HOME/.claude/agents"
```

Verify:

```bash
readlink ~/.claude/skills   # → absolute path to your adlc-toolkit clone
readlink ~/.claude/agents   # → absolute path to .../adlc-toolkit/agents
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

### 4. Configure for your stack

Pick a preset that matches your stack and copy it to `.adlc/config.yml`:

```bash
ls ~/.claude/skills/presets/
cp ~/.claude/skills/presets/ios-firebase-cloudrun.yml .adlc/config.yml
$EDITOR .adlc/config.yml  # replace every <placeholder> with a real value
```

If no preset matches, copy the bare template instead and fill it out from scratch:

```bash
cp ~/.claude/skills/templates/config-template.yml .adlc/config.yml
```

Single-repo projects without a backend can leave the file absent — every skill falls back to legacy single-repo behavior in that case.

## Workflow

```
/spec → /validate → /architect → /validate → implement → /reflect → /review → merge → /wrapup
```

For bugs: `/bugfix` (report → analyze → fix → verify → ship)

For multi-REQ batches: `/sprint` (parallel `/proceed` runners)

## Project Structure

After `/init`, each code repo will have:

```
.adlc/
  config.yml         # Project's stack, deploy config, and (optional) sibling repo layout
  context/           # Project-specific architecture, conventions, overview
  specs/             # Requirement docs, architecture docs, tasks
  knowledge/         # Assumptions validated, lessons learned
  templates/         # Copies of templates (from this toolkit)
```

The toolkit repo contains the **process** (skills + templates). Each code repo contains the **artifacts** (specs, architecture, knowledge).

## Cross-Repo REQs

Some features span multiple repos (e.g., a feature that touches a backend API, a web frontend, and a mobile app at the same time). The toolkit supports these via the optional `repos:` block in `.adlc/config.yml`.

### Key concept: "primary" is per-REQ

There is no fixed "primary repo." Whichever repo you invoke `/proceed` (or `/bugfix`) from becomes the primary for that REQ — it holds the spec, tasks, and `pipeline-state.json` for that work. A different REQ that originates in a sibling repo makes that sibling the primary. Every repo that may originate REQs gets its own `.adlc/` structure and its own `config.yml`; the configs are **mirror images** of each other (each repo marks itself `primary: true` and lists the others as siblings).

### config.yml shape

```yaml
repos:
  api:
    primary: true       # only in this repo's config
  infrastructure:
    path: ../infrastructure
  app:
    path: ../app
  web:
    path: ../web

merge_order:            # default Phase 8 merge sequence
  - infrastructure
  - api
  - app
  - web

services:               # consumed by /canary, keyed by repo id
  api:
    cloud_run_service: api
    region: us-central1
    image_path: us-central1-docker.pkg.dev/<gcp-project>/api/api
  # (infrastructure has no service entry — it deploys via Terraform)
```

See [`templates/config-template.yml`](templates/config-template.yml) for the full annotated template (including `project:`, `stack:`, `gcp:`, and `ios:` sections).

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

## Stack support

The toolkit's workflow is stack-agnostic. Skills that need to do stack-specific things (deploy a Cloud Run service, push a build to an iOS device, etc.) read `.adlc/config.yml` to learn what your stack is and what concrete values to use.

| Capability | Where the skill checks | What you fill in |
|---|---|---|
| Deploy confirmation (`/bugfix`, `/wrapup`) | `stack.backends` includes `cloud-run` | `gcp.staging_project`, `gcp.production_project` |
| Canary deploys (`/canary`) | `services:` block | service name, region, image path per repo |
| iOS device deploys (`/bugfix`, `/wrapup`) | `stack.frontends` includes `ios` | `ios.deploy_targets`, `ios.deploy_command` |
| Convention checking (`/review`, `/reflect`) | `.adlc/context/conventions.md` | declare your project's naming, logging, and API conventions |

If you want to add support for a new stack (e.g., AWS Lambda backends, Android device deploys), edit the relevant skill to handle the new `stack.*` value and document it in [`templates/config-template.yml`](templates/config-template.yml). PRs welcome.

## Updating

Pull the latest toolkit to update all skills across all projects:

```bash
cd "$(readlink ~/.claude/skills)"
git pull
```

Since `~/.claude/skills` is a symlink, changes are picked up immediately.

## Contributing

This is published as a generic toolkit you can fork or contribute back to. Patches that add presets, support new stacks, or sharpen workflows for stacks already supported are all welcome.
