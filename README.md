# SDLC Toolkit

Shared skills and templates for spec-driven development with Claude Code.

## What's Included

### Skills

| Skill | Description |
|-------|-------------|
| `/init` | Bootstrap `.sdlc/` structure in a new repo |
| `/spec` | Write requirement specs from feature requests |
| `/architect` | Design architecture and break requirements into tasks |
| `/validate` | Validate any SDLC phase output before advancing |
| `/review` | Multi-agent code review |
| `/reflect` | Post-implementation self-review before formal review |
| `/wrapup` | Close out a feature — commit, merge, deploy, update artifacts |
| `/bugfix` | Streamlined bug fix workflow |
| `/status` | Show current state of all SDLC work |
| `/analyze` | Codebase health audit |
| `/optimize` | API cost & performance scanner |

### Templates

- `requirement-template.md` — Requirement spec template
- `task-template.md` — Technical task template
- `bug-template.md` — Bug report template

## Setup

### 1. Clone this repo

```bash
cd ~/Documents/GitHub  # or wherever you keep repos
git clone https://github.com/atelier-fashion/sdlc-toolkit.git
```

### 2. Symlink to Claude Code skills directory

```bash
# Back up existing skills if any
mv ~/.claude/skills ~/.claude/skills.bak

# Create symlink
ln -s ~/Documents/GitHub/sdlc-toolkit ~/.claude/skills
```

### 3. Initialize a project

In any code repo:

```bash
claude
> /init
```

This bootstraps the `.sdlc/` directory with project-specific context, specs, and copies of the templates.

## Workflow

```
/spec → /validate → /architect → /validate → implement → /reflect → /review → merge → /wrapup
```

For bugs: `/bugfix` (report → analyze → fix → verify)

## Project Structure

After `/init`, each code repo will have:

```
.sdlc/
  context/           # Project-specific architecture, conventions, overview
  specs/             # Requirement docs, architecture docs, tasks
  knowledge/         # Assumptions validated, lessons learned
  templates/         # Copies of templates (from this toolkit)
```

The toolkit repo contains the **process** (skills + templates). Each code repo contains the **artifacts** (specs, architecture, knowledge).

## Updating

Pull the latest toolkit to update all skills across all projects:

```bash
cd ~/Documents/GitHub/sdlc-toolkit
git pull
```

Since `~/.claude/skills` is a symlink, changes are picked up immediately.
