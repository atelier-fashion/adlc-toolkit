---
name: status
description: Show current state of all ADLC work across the project
argument-hint: Optional filter (e.g., REQ-xxx, "in-progress", "bugs")
---

# /status — ADLC Status Dashboard

You are generating a status report of all ADLC work in the current project.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

> **See also `/manifest`** — `/status` reads this **local** checkout; `/manifest` derives in-flight work across **all sessions** from the remote (open PRs + pushed `feat/REQ-*` branches), with an advisory overlap report. Use `/manifest` to see what other people are working on before you start.

## Context

- Specs directory: !`ls .adlc/specs/ 2>/dev/null || echo "No specs found"`
- Bugs directory: !`ls .adlc/bugs/ 2>/dev/null || echo "No bugs found"`
- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`

## Input

Filter: $ARGUMENTS

## Prerequisites

Before proceeding, verify that the `.adlc/specs/` directory exists (this skill reads requirement and task frontmatter from there). `.adlc/bugs/` and live `pipeline-state.json` files are read when present but are not required. If `.adlc/specs/` does not exist, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` first to set up the project context."

## Instructions

### Step 1: Scan All ADLC Artifacts

**Detect repository mode** — read `.adlc/config.yml`. If it declares more than one entry under `repos:`, this is **cross-repo mode**; otherwise **single-repo mode**.

1. Read all `requirement.md` files under `.adlc/specs/REQ-*/` (this repo)
2. Read all task files under `.adlc/specs/REQ-*/tasks/`
3. Read all bug reports under `.adlc/bugs/` — including the optional `introduced_by` /
   `attribution` frontmatter, which supplies the Incident Attribution section below
4. Read all `pipeline-state.json` files under `.adlc/specs/REQ-*/` for live pipeline progress
5. Also check for nested `.adlc/` directories (e.g., `api/.adlc/`)
6. Extract frontmatter (id, title, status, updated) from each artifact

**Cross-repo scan** (only in cross-repo mode): for every sibling declared in `.adlc/config.yml`:
- Resolve the sibling's absolute path from `repos[<id>].path`
- Read `<sibling-path>/.adlc/specs/REQ-*/pipeline-state.json` to find REQs where the sibling was primary. Any of those that have a `repos` block listing the current repo as `touched: true` represents cross-repo work that affects us but originates elsewhere.
- Capture REQ id, primary repo id, state file path, and current phase for the cross-repo report section (Step 2).

Cross-repo scan is read-only — `/status` never modifies sibling repos.

### Step 2: Build Status Report
Organize the report as follows:

#### Requirements Summary Table
| ID | Title | Status | Tasks | Progress |
|----|-------|--------|-------|----------|

For each requirement:
- Count total tasks and completed tasks
- Calculate progress percentage
- Show status from frontmatter

#### Active Pipelines
If any `pipeline-state.json` files exist with `"completed": false`, show:
| REQ | Primary | Branch | Current Phase | Started | Last Phase Completed | Touched Repos |
|-----|---------|--------|---------------|---------|----------------------|---------------|

- **Primary** column: which repo the REQ originates from (the repo holding the state file). In single-repo mode this is always the current repo; omit the column if no cross-repo config exists.
- **Touched Repos** column: only populated in cross-repo mode — list every repo id from the state file's `repos` block where `touched: true`, with a ✓ for merged and a clock for in-progress.

Phase names: 0=Worktree, 1=Validate Spec, 2=Architect, 3=Validate Tasks, 4=Implement, 5=Verify, 6=Create PR, 7=PR Cleanup, 7.5=Canary, 8=Wrapup

**Separate the genuinely-active from the never-closed (BUG-193).** A
`completed:false` state file is not proof of an active pipeline — a run that
merged its PR but skipped the Phase 8 close-out leaves the same signature, and
those files never self-correct. Before listing a REQ as active, test these
offline invariants and report any that trip under a **Stale Pipeline State**
heading instead, with the reconciliation as the recommended action:

| Signature | Reading |
|---|---|
| `completed:false` but every touched repo has `merged:true` | merged; close-out skipped |
| `completed:false`, `currentPhase:8`, `7 ∈ completedPhases` | reached the final phase and stopped — verify the PR, then close |
| `completed:true` but `8 ∉ completedPhases`, or `currentPhase ≠ 8`, or a touched repo still `merged:false` | closed with a partial record |
| the requirement's frontmatter says `status: complete` | the REQ is done; a `completed:false` state file contradicts it |

Confirm against the forge before reconciling — `gh pr view <prNumber> --json
state,mergedAt` — and write the real merge commit and timestamp into the
phase-8 `phaseHistory` entry rather than a synthesized one. Never infer a merge
from the requirement's status alone.

#### Cross-Repo Activity (cross-repo mode only)
If the cross-repo scan found REQs originating elsewhere that touch this repo, surface them separately so the user sees inbound cross-repo work without losing context on local REQs:

| REQ | Primary (origin) | Current Phase | This Repo's Role | Branch Here |
|-----|------------------|---------------|------------------|-------------|
| REQ-091 | api       | 4/8 Implement | sibling (touched) | feat/REQ-091-... |

"Branch Here" is detected by checking `git -C <this-repo> branch --list feat/REQ-xxx-*`. If absent, the REQ hasn't reached Phase 4 yet or this repo isn't touched after all.

#### In-Progress Work
List any artifacts with status `in-review`, `approved`, or in-progress tasks:
- Which requirement they belong to
- What phase they're in (spec, architecture, tasks, implementation)
- What's blocking progress (if any)

#### Open Bugs
| ID | Title | Severity | Status | Updated |
|----|-------|----------|--------|---------|

#### Incident Attribution
Which shipped REQs have produced incidents (REQ-593). Derived at read time by scanning
`.adlc/bugs/` frontmatter — the reverse edge is never stored in a REQ spec, because a
stored backlink rots silently when an artifact is moved or renumbered (BR-4, LESSON-019).

Source the partial and call it **in the same fenced block** (the cross-fence-fn rule):

```bash
if [ -f .adlc/partials/attribution.sh ]; then . .adlc/partials/attribution.sh; else . ~/.claude/skills/partials/attribution.sh; fi
# Emits one "BUG-id<TAB>REQ-id" line per attributed edge; add a REQ id as a second
# argument to filter to that REQ's incidents. Strictly read-only.
adlc_attr_bugs_with_attribution "$PWD"
```

| REQ | Incidents | Bugs |
|-----|-----------|------|

One row per REQ that has at least one attributed bug, with the count and the BUG ids.
A bug carrying no `introduced_by` is simply absent — it is not an error. When nothing is
attributed, print `No attributed incidents yet.` rather than an empty table or a warning.

This section reads `.adlc/bugs/` only. It **modifies no file**, and in particular opens
nothing under `.adlc/specs/**`.

#### Conflict Resolutions
Which pipeline runs resolved a merge or rebase conflict mid-run, and whether the
resolution was verified (BUG-212). Read from each spec's `pipeline-state.json`
`conflictsResolved` array — the record written at the moment of resolution, not the
runner's narrative. Strictly read-only; a state file without the key is simply a run
that resolved nothing.

```bash
# One row per recorded resolution. `conflictsResolved` is optional and additive:
# a state file without it parses unchanged (absent == none resolved).
for f in .adlc/specs/REQ-*/pipeline-state.json; do
  [ -f "$f" ] || continue
  python3 - "$f" <<'PYEOF'
import json, sys, os
p = sys.argv[1]; req = os.path.basename(os.path.dirname(p)).split("-", 2)[:2]
try:
    s = json.load(open(p))
except (OSError, ValueError):
    sys.exit(0)  # unreadable state is /status Step 1's concern, not this section's
for e in s.get("conflictsResolved") or []:
    print("\t".join(["-".join(req), str(e.get("phase", "?")), ",".join(e.get("files") or []),
                     str(e.get("resolvedBy", "?")), str(e.get("strategy", "?")),
                     "yes" if e.get("verified") else "no", str(e.get("resolvedAt", "?"))]))
PYEOF
done
```

| REQ | Phase | Files | Resolved by | Strategy | Verified | When |
|-----|-------|-------|-------------|----------|----------|------|

When no run has a recorded resolution, print `No recorded conflict resolutions.` rather
than an empty table. An entry with `verified: no` is not an error — it is the honest
value the record exists to surface.

#### Recently Completed
List artifacts completed in the last 7 days (by `updated` date).

### Step 3: Apply Filters (if provided)
- If a REQ ID is given, show detailed status for just that requirement and its tasks
- If "in-progress" is given, show only non-complete work
- If "bugs" is given, show only bug reports
- If no filter, show the full dashboard

### Step 4: Highlight Action Items
At the bottom, list recommended next actions:
- Specs that are `draft` and need validation
- Approved specs that need architecture/tasks
- Tasks that are ready to implement (dependencies met)
- Bugs that are `open` and unassigned
