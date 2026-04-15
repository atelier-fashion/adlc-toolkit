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
| `/review` | Multi-agent code review |
| `/reflect` | Post-implementation self-review before formal review |
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
  context/           # Project-specific architecture, conventions, overview
  specs/             # Requirement docs, architecture docs, tasks
  knowledge/         # Assumptions validated, lessons learned
  templates/         # Copies of templates (from this toolkit)
```

The toolkit repo contains the **process** (skills + templates). Each code repo contains the **artifacts** (specs, architecture, knowledge).

## Updating

Pull the latest toolkit to update all skills across all projects:

```bash
cd ~/Documents/GitHub/adlc-toolkit
git pull
```

Since `~/.claude/skills` is a symlink, changes are picked up immediately.
