---
name: init
description: Bootstrap .adlc/ structure in a new repo or subdirectory
argument-hint: Optional target directory (defaults to current directory)
---

# /init — Bootstrap ADLC Structure

You are setting up the `.adlc/` directory structure for spec-driven development.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

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
  context/
    project-overview.md    # What the project does, tech stack, scope
    architecture.md        # System diagram, layers, key patterns, ADRs
    conventions.md         # File organization, naming, testing, git conventions
  specs/
    .gitkeep
  bugs/
    .gitkeep
  knowledge/
    assumptions/
      .gitkeep
    lessons/
      .gitkeep
```

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

# ADLC global REQ counter is at ~/.claude/.global-next-req (not per-project)
# ADLC local BUG counter (per-project state, not shared)
.adlc/.next-bug
```

### Step 6: Verify Toolkit Templates Are Accessible
Verify that templates are accessible at `~/.claude/skills/templates/` (the toolkit symlink). Do NOT copy templates into per-project `.adlc/templates/` — all skills reference the toolkit templates directly at runtime.

If `~/.claude/skills/templates/` doesn't exist, warn: "Toolkit templates not found at `~/.claude/skills/templates/`. Ensure `~/.claude/skills` is symlinked to the adlc-toolkit repo."

**Note**: The `.adlc/templates/` directory is no longer created. Existing projects with local templates will continue to work — skills check the local path first, then fall back to the toolkit path.

### Step 7: Summary
1. Display the created directory structure
2. Explain the ADLC workflow: `/spec` → `/validate` → `/architect` → `/validate` → implement → `/reflect` → `/review` → `/wrapup` (or use `/proceed` to run the full pipeline automatically)
3. Suggest adding ADLC skill references to the project's `CLAUDE.md` if one exists
