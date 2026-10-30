---
name: init
description: Bootstrap .adlc/ structure in a new repo or subdirectory
argument-hint: Optional target directory, then --harness <name>[,<name>…] (defaults to claude)
---

# /init — Bootstrap ADLC Structure

You are setting up the `.adlc/` directory structure for spec-driven development.

## Ethos

!`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md || echo No ethos found — run /init, or /adlc:init on the plugin install, to vendor .adlc/ETHOS.md`

## Input

The target is the argument: whatever follows `/init` in the invocation (on Claude Code it can also arrive as an `ARGUMENTS:` line appended to this text), a directory to initialize. With none, the current working directory.

A `--harness <name>[,<name>…]` flag in the argument names the agent harnesses whose project layer Step 8 renders (REQ-657 BR-11). Strip it before reading the directory. Without it the harness list is `claude` alone. A non-Claude harness's project layer is written only when the flag names it, never because `adlc harness detect` found its binary, and only the adapters shipped under the toolkit's `harness/` directory can be named.

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
  ETHOS.md               # Copy of $ADLC_TOOLKIT_ROOT/ETHOS.md — ensures skills work inside git worktrees
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
  templates/             # Copies of $ADLC_TOOLKIT_ROOT/templates/*.md — ensures skills work inside git worktrees
    assumption-template.md
    bug-template.md
    lesson-template.md
    requirement-template.md
    task-template.md
  partials/              # Copies of $ADLC_TOOLKIT_ROOT/partials/*.sh — shared shell snippets sourced by SKILL.md files
    ethos-include.sh
  agents/                # Copies of $ADLC_TOOLKIT_ROOT/agents/*.md — the checklists a dispatch paragraph runs inline (no harness discovers agents here)
    reflector.md
  workflows/             # Copies of $ADLC_TOOLKIT_ROOT/workflows/ RUNTIME files only — Dynamic Workflow scripts used by the workflow engine
    adlc-sprint.workflow.js   # ONE self-contained file: meta first, schemas + pure helpers inlined behind // ==== BEGIN/END PURE ==== (runtime has no require)
    README.md            # NOTE: workflows/tests/ is intentionally NOT copied — those are toolkit-internal node:test files (CommonJS require) that break Jest in "type":"module" consumer repos (see Step 6)
```

**Why the local copies of ETHOS.md, templates, partials, agents, and workflows?** Claude Code's sandbox blocks the `Read` tool from accessing paths outside the current working directory. When a skill runs inside a git worktree (e.g., `.claude/worktrees/<name>/`), `$ADLC_TOOLKIT_ROOT/ETHOS.md`, `$ADLC_TOOLKIT_ROOT/templates/*.md`, `$ADLC_TOOLKIT_ROOT/partials/*.sh`, `$ADLC_TOOLKIT_ROOT/agents/*.md`, and `$ADLC_TOOLKIT_ROOT/workflows/*` become unreadable by subagents and any tool that uses `Read` mid-skill. That holds on both install routes: the clone behind the skills symlink is outside the project, and so is the plugin's cache copy, which is not an allowed working directory either (REQ-669 `verification.md` N2). Keeping copies under `.adlc/` makes the toolkit work identically in main checkouts and worktrees.

**ToolkitRoot.** `$ADLC_TOOLKIT_ROOT` is the running install's toolkit directory: the plugin's cache copy on the plugin route, or the clone behind the skills symlink on the symlink route. Every fence below that reads a toolkit file resolves it with the canonical root line as its first line (conventions.md "Bash in skills", REQ-669 ADR-1). Fenced blocks share no shell state, so each fence carries its own copy of that line, and `/init` copies from whichever install is running (REQ-669 ADR-8).

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

# ADLC session sidecars (per-session transcript pointers written by a hook, per-worktree)
.adlc/.session/

# ADLC ID counters are global (${ADLC_HOME:-$HOME/.claude}/.global-next-req, .global-next-bug and .global-next-lesson) — not per-project
# Legacy per-project counters (deprecated, no longer read/written — ignored if present)
.adlc/.next-bug
.adlc/.next-req
.adlc/.next-lesson
```

### Step 6: Copy ETHOS.md and Templates Into the Project

Copy the canonical ETHOS.md and all templates from the toolkit into the project so skills keep working inside git worktrees (where Read is sandboxed to the worktree root).

```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
# Verify source exists. ToolkitRoot is the plugin's cache copy on the plugin
# route, or the clone behind the skills symlink on the symlink route.
if [ ! -f "$ADLC_TOOLKIT_ROOT/ETHOS.md" ] || [ ! -d "$ADLC_TOOLKIT_ROOT/templates" ] || [ ! -d "$ADLC_TOOLKIT_ROOT/partials" ] || [ ! -d "$ADLC_TOOLKIT_ROOT/agents" ] || [ ! -d "$ADLC_TOOLKIT_ROOT/workflows" ]; then
  echo "ERROR: adlc toolkit not found at $ADLC_TOOLKIT_ROOT (ToolkitRoot). Install it by either route. Plugin route: claude plugin marketplace add atelier-fashion/adlc-toolkit, then claude plugin install adlc@adlc-toolkit. Symlink route: clone adlc-toolkit and run its ./install.sh."
  exit 1
fi

# Copy ETHOS.md (overwrite — canonical is source of truth)
cp "$ADLC_TOOLKIT_ROOT/ETHOS.md" .adlc/ETHOS.md

# Copy templates (overwrite — canonical is source of truth)
mkdir -p .adlc/templates
cp "$ADLC_TOOLKIT_ROOT/templates"/*.md .adlc/templates/

# Copy partials (overwrite — canonical is source of truth). These are POSIX
# shell snippets sourced by SKILL.md files (e.g., ethos-include.sh). As in the
# other copies, the glob sits outside the quoted directory. Here that also
# matters: partials/tests/source-guard.test.sh reads any fence line containing
# "$ADLC_TOOLKIT_ROOT/partials/" as a partial being sourced.
mkdir -p .adlc/partials
cp "$ADLC_TOOLKIT_ROOT/partials"/*.sh .adlc/partials/
chmod +x .adlc/partials/*.sh

# Copy agent checklists (overwrite — canonical is source of truth), every
# agents/*.md by glob. A dispatch paragraph's inline arm reads
# .adlc/agents/<name>.md when the harness cannot run subagents or the skill runs
# inside one (REQ-666 BR-8), because a worktree-sandboxed or session-jailed read
# cannot reach ToolkitRoot. A checklist store only: no harness is configured to
# discover agents here, so nothing is registered twice.
mkdir -p .adlc/agents
cp "$ADLC_TOOLKIT_ROOT/agents"/*.md .adlc/agents/

# Copy workflows (overwrite — canonical is source of truth). These are the
# Dynamic Workflow scripts the workflow engine runs (e.g.,
# adlc-sprint.workflow.js — ONE self-contained file with schemas + pure helpers
# inlined, since the runtime has no require). Resolved via the two-level fallback
# (.adlc/workflows/... -> $ADLC_TOOLKIT_ROOT/workflows/...) so the engine works
# inside git worktrees where Read is sandboxed to the worktree root.
#
# Copy ONLY the runtime files: the workflow script(s) and the top-level README.
# Do NOT copy workflows/tests/ — those are toolkit-internal `node:test` unit
# tests for the inlined PURE helpers (CommonJS `require('node:test')`). They have
# no purpose in a consumer repo, and shipping a `*.test.js` under .adlc/ is a
# trap: in any "type":"module" repo running Jest, the DEFAULT testMatch
# (**/?(*.)+(spec|test).[jt]s?(x)) discovers .adlc/workflows/tests/helpers.test.js,
# runs it as ESM, and fails it with "ReferenceError: require is not defined" —
# reddening `npm test` and any CI gate that runs it. The engine is ONE
# self-contained file (no require/import/fs), so globbing *.workflow.js captures
# everything the runtime ever resolves.
mkdir -p .adlc/workflows
cp "$ADLC_TOOLKIT_ROOT/workflows"/*.workflow.js .adlc/workflows/
cp "$ADLC_TOOLKIT_ROOT/workflows/README.md" .adlc/workflows/
# Idempotent cleanup: remove a stale tests/ dir left by an OLDER /init that did
# `cp -R` of the whole workflows tree. Heals already-initialized repos on re-run;
# safe no-op when absent. (Belt-and-suspenders to the explicit-file copy above.)
rm -rf .adlc/workflows/tests

# Clean up Finder-style duplicates if present. Matches:
#   - .md files: "requirement-template 2.md"
#   - non-.md files: "pipeline-state 2.json", ".next-bug 2"
#   - directories: "knowledge 2", "specs 2"
# The `-depth` flag processes directory contents before the directory itself,
# so `rm -rf` on a "* 2" dir doesn't fail due to prior deletions.
find .adlc -depth \( -name "* 2" -o -name "* 2.*" \) -exec rm -rf {} + 2>/dev/null

# Advisory (Jest repos): the copy above ships NO test files under .adlc/, so the
# default Jest testMatch stays green with no config change. Only a repo with a
# custom BROAD testMatch (e.g. "**/*.js") would pick up .adlc/ — those repos
# should add "<rootDir>/.adlc/" to testPathIgnorePatterns. Purely informational;
# this does not edit package.json or any jest config.
if grep -q '"jest"' package.json 2>/dev/null || find . -maxdepth 1 -name 'jest.config.*' 2>/dev/null | grep -q .; then
  echo "ADVISORY (Jest detected): .adlc/ contains no test files by design — default 'npm test' is unaffected. If you use a custom broad testMatch, add \"<rootDir>/.adlc/\" to testPathIgnorePatterns."
fi
```

If the user has previously made intentional customizations to their local `.adlc/ETHOS.md`, `.adlc/templates/*.md`, `.adlc/partials/*.sh`, `.adlc/agents/*.md`, or `.adlc/workflows/adlc-sprint.workflow.js`, confirm before overwriting. Use `/template-drift` to surface what differs (it also flags a stale `.adlc/workflows/tests/` left by an older `/init` — the Jest landmine fixed above). Typical drift (stale copies) should be overwritten silently.

#### Vendored sync surfaces (drift-detection contract with `/template-drift`)

The five surfaces this step copies, plus the harness project layer Step 8 renders
(`harness-config`), are the project's **vendored sync surfaces** — written once at init time, never
auto-updated afterward. `/template-drift` is the tool that detects when a toolkit update to any of
them has not yet landed in this project. The two lists MUST stay in agreement:
**every surface added here must get a matching check in `/template-drift`** (see its
`<!-- sync-surfaces: template-drift -->` list). The toolkit's `tools/lint-skills`
`sync-surface-parity` check fails the build if they diverge.

<!-- sync-surfaces: init -->
- `ethos` — `cp "$ADLC_TOOLKIT_ROOT/ETHOS.md" .adlc/ETHOS.md`
- `templates` — `cp "$ADLC_TOOLKIT_ROOT/templates"/*.md .adlc/templates/`
- `partials` — `cp "$ADLC_TOOLKIT_ROOT/partials"/*.sh .adlc/partials/`
- `agents` — `cp "$ADLC_TOOLKIT_ROOT/agents"/*.md .adlc/agents/`
- `workflow-runtime` — `cp "$ADLC_TOOLKIT_ROOT/workflows"/*.workflow.js` + `README.md` → `.adlc/workflows/`
- `harness-config` — `adlc harness render --harness <name>` → each named harness's project layer (Step 8; `claude`: `.claude/settings.json`; `copilot`: `.github/hooks/adlc.json`; `cursor`: `.cursor/cli.json`, `.cursor/permissions.json`)
<!-- /sync-surfaces -->

(Note: `/template-drift` checks one additional surface — `workflow-test-landmine`, a stale
`*.test.js` an *older* `/init` left under `.adlc/`. That is a drift *symptom* this step deliberately
does NOT copy, so it has no entry here; the parity check accounts for that asymmetry.)

### Step 7: Scaffold Retrieval Taxonomy

Copy the canonical taxonomy template to `.adlc/context/taxonomy.md` so authors of new REQs, bugs, and lessons have a reference vocabulary for retrieval tags.

**This step is idempotent — skip if the file already exists** (preserve any project-local customizations).

```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
# Verify source exists
if [ ! -f "$ADLC_TOOLKIT_ROOT/templates/taxonomy-template.md" ]; then
  echo "ERROR: Taxonomy template not found at $ADLC_TOOLKIT_ROOT/templates/taxonomy-template.md. Ensure the adlc toolkit is installed (plugin route or symlink route, see Step 6)."
  exit 1
fi

# Ensure destination directory exists (safe if Step 3 already created it)
mkdir -p .adlc/context

# Idempotent copy: only copy if destination does not already exist
if [ ! -f .adlc/context/taxonomy.md ]; then
  cp "$ADLC_TOOLKIT_ROOT/templates/taxonomy-template.md" .adlc/context/taxonomy.md
  echo "Created .adlc/context/taxonomy.md from canonical template."
else
  echo "Preserved existing .adlc/context/taxonomy.md (idempotent — not overwritten)."
fi
```

Advise the user: "Open `.adlc/context/taxonomy.md` and customize the example values for this codebase. Authors of new REQs, bugs, and lessons will reference this file when choosing tag values (`component`, `domain`, `stack`, `concerns`). The `tags` dimension stays free-form."

### Step 8: Render the Harness Project Layer (allowlist, hooks, instruction files)

Render each named harness's project layer through its adapter (REQ-657 BR-11), so `/proceed` (and every other skill in this toolkit) can run end-to-end without prompting on every routine `git`, `gh`, test and agent-dispatch operation. The project layer is **rendered, never copied**: `adlc harness render` turns the toolkit's `templates/permissions.yml` (the routine tier and the deny tier) and `templates/hooks.yml` (`ethos-inject`, `session-record`) into the file each harness reads. For `claude` that is `.claude/settings.json`, whose deny tier is Claude Code's **ask** list, so a person still confirms each one-way move (`rm -rf`, `git reset --hard`, `gh pr merge`, `./deploy.sh`, `terraform apply/destroy`, force-push to `main`). The same render writes `AGENTS.md`, the project instruction file every harness reads, and a `CLAUDE.md` that imports it.

**Before you run it, when `CLAUDE.md` already exists and someone is in the session**: show the user the `AGENTS.md` the render would write (`$ADLC_TOOLKIT_ROOT/templates/instructions/AGENTS.md`, with the skill list filled in) and the lines that would stay in `CLAUDE.md` if its harness-neutral lines moved to `AGENTS.md`, and wait for their answer. Move lines only on their approval, and by editing `CLAUDE.md` yourself afterwards: the render never deletes or moves a line. In a non-interactive run, render and leave `CLAUDE.md` as the render leaves it.

**This step is idempotent.** An existing `.claude/settings.json` and `AGENTS.md` are kept (pass `--force` to `adlc harness render` to overwrite one), and `CLAUDE.md` gains exactly one `@AGENTS.md` line when it has none, with every other line unchanged. A second run changes nothing. Replace `'<harnesses>'`, quotes included, with the `--harness` value as one single-quoted literal, or with `''` when the argument has none:

```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ ! -f "$ADLC_TOOLKIT_ROOT/tools/adlc/adlc.py" ]; then
  echo "ERROR: the adlc CLI was not found at $ADLC_TOOLKIT_ROOT/tools/adlc/adlc.py. Ensure the adlc toolkit is installed (plugin route or symlink route, see Step 6)."
  exit 1
fi
harnesses='<harnesses>'
[ -n "$harnesses" ] || harnesses=claude
printf '%s\n' "$harnesses" | tr ',' '\n' | while IFS= read -r harness; do
  case "$harness" in
    ''|*[!a-z]*) echo "Skipping '$harness': not a harness name." ; continue ;;
  esac
  python3 "$ADLC_TOOLKIT_ROOT/tools/adlc/adlc.py" harness render --harness "$harness"
done
```

The render prints one line per file (`written`, `unchanged` or `kept`), and on stderr every allowlist entry the harness cannot express, what will prompt because of it, and the user-level remedy where one exists. When `CLAUDE.md` kept its lines, tell the user the follow-up: harness-neutral lines belong in `AGENTS.md`, and `CLAUDE.md` keeps only the Claude-specific ones below its `@AGENTS.md` line.

**Copilot CLI and Cursor (REQ-656).** Each is rendered only when the flag names it. Neither writes a second instruction file: `AGENTS.md` is the one both read.

- `copilot` writes `.github/hooks/adlc.json` and **prints** one `copilot --allow-tool … --deny-tool …` line, because Copilot has no committed allowlist. Show that line to the user verbatim and tell them to paste it into a shell alias or profile, and say which commands will prompt: the report names them. A line labelled "WIDENING, not applied" is a separate remedy; never add it to the paste-ready line. The rendered agents are user-level, so this step does not write them: the render prints the command that does (`adlc harness install --harness copilot`).
- `cursor` writes `.cursor/cli.json` and `.cursor/permissions.json`. Cursor reads its agents and hooks from Claude Code's paths, so a project needs `.claude/settings.json` too: use `--harness claude,cursor`. `--harness cursor` alone leaves that surface unserved, and the session starts without the ETHOS hook. Tell the user `git` and `gh` will prompt, and that a denied one-way move (`rm`, `terraform`, `./deploy.sh`) is run from their own shell.

Customize for project-specific commands (e.g., add `Bash(cd app && ./deploy.sh:*)` for iOS deploys) by editing `.claude/settings.json` directly; `/template-drift` reports those additions as `customized`, never as drift to undo.

Advise the user: "`.claude/settings.json` was rendered with the default allowlist and hooks. Commit it and `AGENTS.md` — both are team-shared. Use `.claude/settings.local.json` (gitignored by Claude Code) for personal overrides. Claude Code applies the committed allowlist only once the workspace is trusted."

### Step 9: Scaffold Cross-Repo Config (Optional)

Ask the user: "Will this repo ever share features with other repos you also work on (e.g., an admin app + its API + an iOS app)? If yes, `/proceed` can coordinate REQs across them — this repo needs a `.adlc/config.yml` to list its siblings."

**Conceptual note** — explain if the user seems uncertain: "Primary" is per-REQ, not a fixed role. The current repo is primary for REQs that originate here (`/proceed` invoked from this repo). The siblings you list are other repos that might participate when a cross-repo REQ starts here. If you also originate REQs from one of those siblings, you'll run `/init` (`/adlc:init` on the plugin install) there too — each repo that hosts REQs gets its own `.adlc/` and its own `config.yml` listing the others as siblings (mirror images of each other).

If the user confirms cross-repo **and** `.adlc/config.yml` does not already exist, copy the template:

```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
# Verify source exists
if [ ! -f "$ADLC_TOOLKIT_ROOT/templates/config-template.yml" ]; then
  echo "ERROR: Config template not found at $ADLC_TOOLKIT_ROOT/templates/config-template.yml. Ensure the adlc toolkit is installed (plugin route or symlink route, see Step 6)."
  exit 1
fi

if [ ! -f .adlc/config.yml ]; then
  cp "$ADLC_TOOLKIT_ROOT/templates/config-template.yml" .adlc/config.yml
  echo "Created .adlc/config.yml from template — edit it to match your repo layout."
else
  echo "Preserved existing .adlc/config.yml."
fi
```

Advise the user:
- "Edit `.adlc/config.yml`. The entry for THIS repo should have `primary: true` and no `path` (path is implicit since it's this repo). Each sibling entry gets a `path:` (relative to this repo root, or absolute). Every sibling must already be cloned locally at that path."
- "If you also run REQs from one of the siblings, run `/init` (`/adlc:init` on the plugin install) there too. That repo's config will mark itself as primary and list the others as siblings — the structure is symmetric."
- "If this is a single-repo project (REQs only ever originate here and never touch other repos), skip this step. ADLC skills fall back to single-repo behavior when no config or no siblings are declared."
- "After editing, verify with `cat .adlc/config.yml` and make sure each sibling path resolves: `git -C <sibling-path> rev-parse --git-dir`."

If the project is single-repo, skip the copy (no config file needed).

### Step 10: Summary
1. Display the created directory structure
2. Explain the ADLC workflow: `/spec` → `/validate` → `/architect` → `/validate` → implement → `/reflect` → `/review` → `/wrapup` (or use `/proceed` to run the full pipeline automatically)
3. If cross-repo config was scaffolded, remind the user that `/proceed` will create worktrees in every touched sibling and open one PR per repo
4. Point to `AGENTS.md`, which Step 8 wrote with the workflow, the skill list and the project-context pointers, and to the `@AGENTS.md` line in `CLAUDE.md`
