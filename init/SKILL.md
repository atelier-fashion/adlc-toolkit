---
name: init
description: Bootstrap .adlc/ structure in a new repo or subdirectory
argument-hint: Optional target directory (defaults to current directory)
---

# /init — Bootstrap ADLC Structure

You are setting up the `.adlc/` directory structure for spec-driven development.

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Input

Target: $ARGUMENTS

## Instructions

### Step 1: Determine Target Directory
1. If given a path, use that as the target
2. If no argument, use the current working directory
3. Check if `.adlc/` already exists — if so, report what's already there and ask if the user wants to reinitialize or fill gaps

### Step 2: Gather Project Context
Ask the user for the following (skip any that are already known from existing files):
1. **Project name** — What is this project called?
2. **What it does** — One paragraph description
3. **Tech stack** — Languages, frameworks, databases, cloud providers
4. **Project scope** — What's in scope vs out of scope
5. **Key architectural patterns** — Layered? Microservices? Monolith?

If a `CLAUDE.md`, `README.md`, or `package.json` exists, extract this info automatically and confirm with the user instead of asking.

### Step 3: Create Directory Structure
```
.adlc/
  ETHOS.md               # Copy of ~/.claude/skills/ETHOS.md — ensures skills work inside git worktrees
  context/
    project-overview.md    # What the project does, tech stack, scope
    architecture.md        # System diagram, layers, key patterns, ADRs
    conventions.md         # File organization, naming, testing, git conventions
    taxonomy.md            # Retrieval tag vocabulary (component/domain/stack/concerns)
  specs/
    .gitkeep
  bugs/
    .gitkeep
  knowledge/
    assumptions/
      .gitkeep
    lessons/
      .gitkeep
  templates/             # Copies of ~/.claude/skills/templates/*.md — ensures skills work inside git worktrees
    assumption-template.md
    bug-template.md
    lesson-template.md
    requirement-template.md
    task-template.md
```

**Why the local copies of ETHOS.md and templates?** Claude Code's sandbox blocks the `Read` tool from accessing paths outside the current working directory. When a skill runs inside a git worktree (e.g., `.claude/worktrees/<name>/`), `~/.claude/skills/ETHOS.md` and `~/.claude/skills/templates/*.md` become unreadable by subagents and any tool that uses `Read` mid-skill. Keeping copies under `.adlc/` makes the toolkit work identically in main checkouts and worktrees.

### Step 4: Populate Context Files

**project-overview.md** — Based on user input or existing docs:
```markdown
# {Project Name} — Project Overview

## What It Does
{description}

## Tech Stack
{tech stack table or list}

## Project Scope
{in scope / out of scope}
```

**architecture.md** — Initial structure:
```markdown
# {Project Name} — Architecture

## System Diagram
{ASCII diagram of major components}

## Layers
{description of architectural layers}

## Key Patterns
{important patterns used in the codebase}

## ADRs
(Add architectural decision records here as decisions are made)
```

**conventions.md** — Based on project analysis:
```markdown
# {Project Name} — Conventions

## File Organization
{directory structure}

## Naming
{naming conventions per language}

## Testing
{test framework, conventions, coverage requirements}

## Error Handling
{error handling patterns}

## Git Conventions
{branch naming, commit messages, PR process}
```

### Step 5: Update .gitignore
Add the following entries to the project's `.gitignore` (create it if it doesn't exist):
```
# ADLC worktrees (used by /proceed for parallel session isolation)
.worktrees/

# Claude Code per-user permission overrides (team settings live in .claude/settings.json)
.claude/settings.local.json

# ADLC global REQ counter is at ~/.claude/.global-next-req (not per-project)
# ADLC local BUG counter (per-project state, not shared)
.adlc/.next-bug
```

### Step 6: Copy ETHOS.md and Templates Into the Project

Copy the canonical ETHOS.md and all templates from the toolkit into the project so skills keep working inside git worktrees (where Read is sandboxed to the worktree root).

```bash
# Verify source exists
if [ ! -f ~/.claude/skills/ETHOS.md ] || [ ! -d ~/.claude/skills/templates ]; then
  echo "ERROR: Toolkit not found at ~/.claude/skills/. Ensure ~/.claude/skills is symlinked to the adlc-toolkit repo."
  exit 1
fi

# Copy ETHOS.md (overwrite — canonical is source of truth)
cp ~/.claude/skills/ETHOS.md .adlc/ETHOS.md

# Copy templates (overwrite — canonical is source of truth)
mkdir -p .adlc/templates
cp ~/.claude/skills/templates/*.md .adlc/templates/

# Clean up Finder-style duplicates if present. Matches:
#   - .md files: "requirement-template 2.md"
#   - non-.md files: "pipeline-state 2.json", ".next-bug 2"
#   - directories: "knowledge 2", "specs 2"
# The `-depth` flag processes directory contents before the directory itself,
# so `rm -rf` on a "* 2" dir doesn't fail due to prior deletions.
find .adlc -depth \( -name "* 2" -o -name "* 2.*" \) -exec rm -rf {} + 2>/dev/null
```

If the user has previously made intentional customizations to their local `.adlc/ETHOS.md` or `.adlc/templates/*.md`, confirm before overwriting. Use `/template-drift` to surface what differs. Typical drift (stale copies) should be overwritten silently.

### Step 7: Scaffold Retrieval Taxonomy

Copy the canonical taxonomy template to `.adlc/context/taxonomy.md` so authors of new REQs, bugs, and lessons have a reference vocabulary for retrieval tags.

**This step is idempotent — skip if the file already exists** (preserve any project-local customizations).

```bash
# Verify source exists
if [ ! -f ~/.claude/skills/templates/taxonomy-template.md ]; then
  echo "ERROR: Taxonomy template not found at ~/.claude/skills/templates/taxonomy-template.md. Ensure ~/.claude/skills is symlinked to the adlc-toolkit repo."
  exit 1
fi

# Ensure destination directory exists (safe if Step 3 already created it)
mkdir -p .adlc/context

# Idempotent copy: only copy if destination does not already exist
if [ ! -f .adlc/context/taxonomy.md ]; then
  cp ~/.claude/skills/templates/taxonomy-template.md .adlc/context/taxonomy.md
  echo "Created .adlc/context/taxonomy.md from canonical template."
else
  echo "Preserved existing .adlc/context/taxonomy.md (idempotent — not overwritten)."
fi
```

Advise the user: "Open `.adlc/context/taxonomy.md` and customize the example values for this codebase. Authors of new REQs, bugs, and lessons will reference this file when choosing tag values (`component`, `domain`, `stack`, `concerns`). The `tags` dimension stays free-form."

### Step 8: Scaffold Claude Code Permissions Allowlist

Copy the canonical Claude Code settings template to `.claude/settings.json` so `/proceed` (and every other skill in this toolkit) can run end-to-end without prompting for permission on every routine `git`, `gh`, test, and agent-dispatch operation. This is the single biggest mitigation against per-phase gating in long-running pipelines.

**This step is idempotent — skip if the file already exists** (preserve any project-local customizations).

```bash
# Verify source exists
if [ ! -f ~/.claude/skills/templates/claude-settings-template.json ]; then
  echo "ERROR: Settings template not found at ~/.claude/skills/templates/claude-settings-template.json. Ensure ~/.claude/skills is symlinked to the adlc-toolkit repo."
  exit 1
fi

# Ensure destination directory exists
mkdir -p .claude

# Idempotent copy: only copy if destination does not already exist
if [ ! -f .claude/settings.json ]; then
  cp ~/.claude/skills/templates/claude-settings-template.json .claude/settings.json
  echo "Created .claude/settings.json from canonical template."
else
  echo "Preserved existing .claude/settings.json (idempotent — not overwritten)."
fi
```

The template pre-approves the routine `git`, `gh`, `npm`, Read/Write/Edit, and agent-dispatch operations the ADLC pipeline fires. Destructive operations (`rm -rf`, `git reset --hard`, `gh pr merge`, `./deploy.sh`, `terraform apply/destroy`, force-push to `main`) remain on the **ask** list so a human still confirms the one-way moves. Customize for project-specific commands (e.g., add `Bash(cd app && ./deploy.sh:*)` for iOS deploys) by editing `.claude/settings.json` directly.

Advise the user: "`.claude/settings.json` was scaffolded with a default allowlist. Commit this file — it is team-shared. Use `.claude/settings.local.json` (gitignored by Claude Code) for personal overrides."

### Step 9: Summary
1. Display the created directory structure
2. Explain the ADLC workflow: `/spec` → `/validate` → `/architect` → `/validate` → implement → `/reflect` → `/review` → `/wrapup` (or use `/proceed` to run the full pipeline automatically)
3. Suggest adding ADLC skill references to the project's `CLAUDE.md` if one exists
