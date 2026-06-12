---
name: architect
description: Design architecture and break requirement into tasks
argument-hint: REQ-xxx ID or requirement description
---

# /architect — Architecture & Task Breakdown

You are designing architecture and breaking a requirement into implementable tasks.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Task template: !`cat .adlc/templates/task-template.md 2>/dev/null || cat ~/.claude/skills/templates/task-template.md 2>/dev/null || echo "No task template found"`
- Active specs: !`grep -rl 'status: draft\|status: approved\|status: in-progress' .adlc/specs/*/requirement.md 2>/dev/null | head -20 || echo "No active specs"`

**Context files loaded on demand**: `.adlc/context/architecture.md` and `.adlc/context/conventions.md` are loaded by Step 1 below — **skip the Read if they are already in the current conversation** (e.g., when invoked from `/proceed`, which preloads them at Phase 0).

## Input

Requirement: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.adlc/context/architecture.md` and `.adlc/context/conventions.md` exist. If either is missing, stop and tell the user: "The `.adlc/` structure hasn't been fully initialized. Run `/init` first to set up the project context."

## Instructions

### Step 1: Locate and Read the Requirement
1. If given a REQ ID, read `.adlc/specs/REQ-xxx-*/requirement.md`
2. If given a description, search `.adlc/specs/` for the matching requirement
3. Verify the requirement status is `draft` or `approved` (not already `complete`)
4. **Context files**: if `.adlc/context/architecture.md` and `.adlc/context/conventions.md` are NOT already in your conversation context (e.g., this skill is being run standalone, not from `/proceed`), Read them now. Otherwise skip — they're already loaded.
5. Check `.adlc/knowledge/assumptions/` for prior decisions that may affect design
6. **Lessons — grep first, then read only matches**: use the Grep tool on `.adlc/knowledge/lessons/` with patterns like `component:.*<affected-area>` or `domain:.*<domain>` to identify matching files. Then Read ONLY those matched files. Do NOT read all lessons. Note applicable lessons in your architecture rationale so past mistakes aren't repeated and proven patterns are reused.

### Step 2: Explore the Codebase
1. Launch 3 formal exploration agents in parallel using the Agent tool. Each agent is defined in `~/.claude/agents/` with model selection (haiku for fast exploration) and read-only tool restrictions.

   - **feature-tracer** agent — provide the requirement description and key terms to search for similar existing implementations
   - **architecture-mapper** agent — provide the requirement and current architecture.md to map all files and layers that will be affected
   - **integration-explorer** agent — provide the affected areas to identify extension points, tests, and integration surfaces

2. Read the key files identified by agents
3. **Retain the `architecture-mapper` affected-file list** (the first column of its "Files to
   Modify" + "Files to Create" tables, bare paths) as `$MAPPER_PATHS` — one path per line. This
   is NOT the footprint source anymore (tasks are, per REQ-484); it is kept only as the BR-4
   graceful-degradation fallback consumed by Step 5 when a task carries no file list.

> **Note (REQ-484):** footprint publishing has moved to **Step 5**, which runs AFTER task
> creation. Per-repo attribution is derived from the task files' `repo:` frontmatter, so the
> publish step MUST run once those files exist — not here during codebase exploration. The
> mapper output is retained (item 3) only as the BR-4 fallback.

### Step 3: Design Architecture (if needed)
1. If the requirement involves new architectural decisions, create `.adlc/specs/REQ-xxx-*/architecture.md`
2. Document:
   - **Approach**: High-level design and rationale
   - **Data model changes**: New Firestore collections/fields, GCS metadata
   - **API changes**: New or modified endpoints
   - **Service layer**: New or modified services
   - **Key decisions**: ADRs with rationale (follow the style in `.adlc/context/architecture.md`)
3. Propose any additions to `.adlc/context/architecture.md` with rationale

### Step 4: Break Into Tasks
1. Create `.adlc/specs/REQ-xxx-*/tasks/` directory
2. Determine the next TASK ID by checking existing tasks across ALL specs (not just this one)
3. **Detect repository mode**: check whether `.adlc/config.yml` exists in the primary repo and declares a `repos:` block with more than one entry.
   - **Single-repo mode** (no config or single entry): set `repo:` on each task to the primary repo id (or omit — `/proceed` will backfill). Files listed under "Files to Create/Modify" all live in the primary repo.
   - **Cross-repo mode** (config has siblings): **every task MUST declare a `repo:` field** naming one of the ids under `repos:`. Group files by repo — a single task should not modify files in multiple repos. If a piece of work spans repos (e.g., an API contract change requires matching backend and frontend edits), split it into at least two tasks with an explicit dependency between them.
4. Create `TASK-xxx-description.md` for each task using the template from `.adlc/templates/task-template.md`
5. Each task must specify:
   - **Frontmatter**: id, title, status (`draft`), parent REQ, created/updated dates, dependencies, `repo:` (required in cross-repo mode)
   - **Description**: What this task accomplishes
   - **Files to Create/Modify**: Specific file paths with descriptions of changes — all paths must live in the task's target repo
   - **Acceptance Criteria**: Concrete, testable criteria
   - **Technical Notes**: Implementation details, patterns to follow, edge cases. In cross-repo mode, call out any cross-repo contracts this task establishes or consumes.
   - **Dependencies**: Other tasks that must complete first — dependencies may cross repos (a frontend task can depend on a backend task)
6. Tasks must form a valid dependency graph (no cycles), even when spanning repos
7. Order tasks so foundational work comes first (data layer → service → routes → UI). In cross-repo mode, backend/API tasks typically precede their frontend consumers.

### Step 5: Publish the File Footprint to the Draft PR(s) (REQ-483 BR-4 / REQ-484)

**Runs AFTER task creation** so per-repo `repo:` attribution from the task files is available
(REQ-484 ADR-2 / OQ-1). Under `/proceed`, a draft PR already exists per touched repo (Step 0),
each recorded in `pipeline-state.json` `repos[<id>].prNumber`. Publish **each repo's own**
footprint into **that repo's** draft PR — one fenced `adlc-footprint` block per PR, each line
repo-qualified `<repo-id>:<path-or-glob>` (the schema `/manifest` parses; see
`.adlc/specs/REQ-483-*/architecture.md` and `.adlc/specs/REQ-484-*/architecture.md`). Idempotent
(replace any prior block). Skip with a one-line note if there is no draft PR (standalone
`/architect`, no `/proceed`).

**Attribution (BR-1, BR-6, ADR-1).** A repo's footprint is the union of
`## Files to Create/Modify` paths across tasks whose `repo:` frontmatter equals that repo id. A
task with **no** `repo:` field attributes to the **primary** repo (single-repo projects omit
`repo:`), so single-repo REQs derive from tasks via this same path — NOT via the BR-4
mapper-fallback. A path is attributed to a repo solely by its task's `repo:` tag — never
broadcast to all PRs, never inferred from the path string.

**Iterate every PR (BR-2, BR-3).** Loop over every touched repo's `prNumber` from
`pipeline-state.json` — do NOT use `head -1`. Each PR receives only its own repo's lines. In
single-repo mode the loop degenerates to one repo / one PR / one block, with no separate code
path and no "coarse" flag.

**Sanitize on write (BR-5, LESSON-008).** Every emitted line MUST pass the same validation the
read side applies — reject any line containing `..`, then charset-validate
`^[A-Za-z0-9_.-]*:?[A-Za-z0-9_./*-]+$` — BEFORE it is written to any PR body.

**Graceful degradation, never error (BR-4).** A task with no file list, or a touched repo with
no tasks attributing files, falls back to the architecture-mapper paths attributed to the
**primary** repo, emitting a one-line `source: mapper-fallback` notice. A repo with genuinely
zero attributable files is skipped with a note — never publish an empty block silently.

```sh
# Forge adapter (REQ-520 BR-1): footprint publish reads/writes the PR body via
# pr_view/pr_edit, never direct gh. Sourced in THIS fence (shell state does not
# cross fences). GitHub backend forwards args verbatim, so the body read/write is
# byte-identical (BR-3).
. .adlc/partials/forge.sh 2>/dev/null || . ~/.claude/skills/partials/forge.sh

# Scope to THIS REQ's spec dir. $REQ is the REQ id (e.g. REQ-484) the skill is operating on;
# fall back to the lone pipeline-state.json if $REQ is unset (resolve to its spec dir either way).
# find, not ls globs: zsh errors on unmatched globs ("no matches found") instead of
# passing the pattern through, so a glob here breaks sh/bash/zsh parity.
state=""
if [ -n "$REQ" ]; then
  state=$(find .adlc/specs -type f -path "*/${REQ}-*/pipeline-state.json" 2>/dev/null | sort | head -1)
fi
[ -n "$state" ] || state=$(find .adlc/specs -type f -path "*/REQ-*/pipeline-state.json" 2>/dev/null | sort | head -1)
[ -n "$state" ] || { echo "architect: no pipeline-state.json — standalone run, skipping footprint publish"; exit 0; }
specdir=$(dirname "$state")   # THIS REQ's spec dir — task glob is scoped here, not all specs.
tick=$(printf '\140\140\140')
tab=$(printf '\t')
# Primary repo id (tasks with no repo: attribute here). The parse targets the pretty-printed
# pipeline-state.json that /proceed writes (one JSON field per line; each repo object spans
# multiple lines). It also tolerates one-repo-object-per-line layouts. A repo-id opening
# (`"<id>": {`) sets the current repo; "primary"/"prNumber" bind to it (matched on the same line
# too, so a repo whose object opens and closes on its own line still resolves). POSIX awk only —
# no 3-arg match(), no perl dependency.
primary=$(awk '
  /"repos"[[:space:]]*:/ { inrepos=1 }
  inrepos && /"[A-Za-z0-9_.-]+"[[:space:]]*:[[:space:]]*\{/ {
    # take the key immediately before `: {` (the LAST quoted token before the brace), so a
    # compact line like `{ "req":"R", "repos": { "solo": {` still yields `solo`, not `req`.
    s=$(0); sub(/[[:space:]]*:[[:space:]]*\{.*/,"",s); sub(/"$/,"",s); sub(/.*"/,"",s)
    if (s!="repos" && s!="") cur=s
  }
  inrepos && cur!="" && /"primary"[[:space:]]*:[[:space:]]*true/ { print cur; exit }
' "$state" 2>/dev/null)
# Touched repo ids that have a prNumber, one TSV line per repo: "<repo-id><TAB><prNumber>".
# Each prNumber stays bound to its owning repo id (NOT head -1). Same dual-format awk.
repos_prs=$(awk -v TAB="$tab" '
  /"repos"[[:space:]]*:/ { inrepos=1 }
  inrepos && /"[A-Za-z0-9_.-]+"[[:space:]]*:[[:space:]]*\{/ {
    # take the key immediately before `: {` (the LAST quoted token before the brace), so a
    # compact line like `{ "req":"R", "repos": { "solo": {` still yields `solo`, not `req`.
    s=$(0); sub(/[[:space:]]*:[[:space:]]*\{.*/,"",s); sub(/"$/,"",s); sub(/.*"/,"",s)
    if (s!="repos" && s!="") cur=s
  }
  inrepos && cur!="" && /"prNumber"[[:space:]]*:[[:space:]]*[0-9]+/ {
    n=$(0); sub(/.*"prNumber"[[:space:]]*:[[:space:]]*/,"",n); sub(/[^0-9].*/,"",n);
    if (n!="") { print cur TAB n; cur="" }
  }
' "$state" 2>/dev/null)
[ -n "$repos_prs" ] || { echo "architect: no draft PR (no prNumber in state) — skipping footprint publish"; exit 0; }

printf '%s\n' "$repos_prs" | while IFS="$tab" read -r repo prnum; do
  [ -n "$repo" ] && [ -n "$prnum" ] || continue
  # Collect this repo's task-attributed file paths (first backtick token of each bullet under
  # "## Files to Create/Modify"); a task with no repo: attributes to $primary.
  lines=""
  # while-read over find, not a for-glob: zsh errors on unmatched globs ("no matches
  # found") instead of passing the pattern through. Heredoc (not a pipe) so $lines
  # accumulated in the loop survives it.
  while IFS= read -r tf; do
    [ -f "$tf" ] || continue
    trepo=$(sed -nE 's/^repo:[[:space:]]*([A-Za-z0-9_.-]+).*/\1/p' "$tf" | head -1)
    [ -n "$trepo" ] || trepo="$primary"
    [ "$trepo" = "$repo" ] || continue
    paths=$(awk '/^## Files to Create\/Modify/{f=1;next} /^## /{f=0} f && /^- /{print}' "$tf" \
      | sed -nE 's/^- *`([^`]+)`.*/\1/p')
    [ -n "$paths" ] && lines=$(printf '%s\n%s\n' "$lines" "$paths")
  done <<TASKS_EOF
$(find "$specdir"/tasks -name 'TASK-*.md' 2>/dev/null | sort)
TASKS_EOF
  # Repo-qualify, sanitize (reject .. then charset-validate), dedupe.
  safe=$(printf '%s\n' "$lines" | sed '/^$/d' \
    | while IFS= read -r p; do printf '%s:%s\n' "$repo" "$p"; done \
    | grep -vE '\.\.' | grep -E '^[A-Za-z0-9_.-]*:?[A-Za-z0-9_./*-]+$' | sort -u)
  if [ -z "$safe" ]; then
    # BR-4 fallback: architecture-mapper paths attributed to primary (only for the primary PR).
    if [ "$repo" = "$primary" ] && [ -n "$MAPPER_PATHS" ]; then
      safe=$(printf '%s\n' "$MAPPER_PATHS" | sed '/^$/d' \
        | while IFS= read -r p; do printf '%s:%s\n' "$primary" "$p"; done \
        | grep -vE '\.\.' | grep -E '^[A-Za-z0-9_.-]*:?[A-Za-z0-9_./*-]+$' | sort -u)
      [ -n "$safe" ] && echo "architect: repo=$repo source: mapper-fallback (no task file list)"
    fi
  fi
  if [ -z "$safe" ]; then
    echo "architect: repo=$repo has zero attributable files — skipping (no empty block)"
    continue
  fi
  tmp=$(mktemp "${TMPDIR:-/tmp}/footprint.XXXXXX") || continue
  if base=$(adlc_forge_pr_view "$prnum" --json body -q .body 2>/dev/null); then
    base=$(printf '%s\n' "$base" | sed "/^${tick}adlc-footprint/,/^${tick}/d")
    { printf '%s\n\n%sadlc-footprint\n' "$base" "$tick"; printf '%s\n' "$safe"; printf '%s\n' "$tick"; } > "$tmp"
    adlc_forge_pr_edit "$prnum" --body-file "$tmp" >/dev/null 2>&1 && echo "architect: published footprint for repo=$repo to PR #$prnum"
  fi
  rm -f "$tmp"
done
```

`$MAPPER_PATHS` holds the architecture-mapper affected-file list (bare paths, no repo column)
captured during Step 2 — used only for the BR-4 primary-repo fallback when a task carries no file
list. Other sessions read each block via `adlc_forge_pr_view --json body` (consumed by `/manifest`'s
ordering verdict). The block is split-free (newline iteration, no unquoted word-splitting) so it
behaves identically under `sh` and `zsh` (LESSON-329), and uses `mktemp` + cleanup per PR.

### Step 6: Update Requirement Status
1. Update the requirement's frontmatter status from `draft` to `approved`
2. Update the `updated` date

### Step 7: Present for Review
1. Display the architecture decisions (if any)
2. Display the task breakdown as a dependency graph
3. Summarize the implementation plan
4. Remind the user to run `/validate` before starting implementation

## Quality Checklist
- [ ] Architecture follows existing patterns (layered: routes → services → repositories)
- [ ] Tasks are small enough to implement in a single session
- [ ] Task dependencies form a valid DAG (no cycles), including cross-repo edges
- [ ] Every file to be modified is listed in at least one task
- [ ] Tests are included in task acceptance criteria
- [ ] No task has more than 3 dependencies
- [ ] In cross-repo mode: every task has a `repo:` field naming a valid repo id from `.adlc/config.yml`, and all files in that task live in that repo
