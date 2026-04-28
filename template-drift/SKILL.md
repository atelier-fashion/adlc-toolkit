---
name: template-drift
description: Detect drift between this project's `.adlc/templates/` copies and the canonical templates in `~/.claude/skills/templates/`. Use when the user says "check template drift", "template drift", "are my templates out of date", or wants to know whether toolkit template updates have landed in this project yet. Reports a per-file diff summary and flags intentional customizations from accidental staleness.
argument-hint: Optional template name (e.g., "requirement-template") to scope the check to a single file
---

# /template-drift — Template Drift Detector

You are checking whether the project's local `.adlc/templates/` copies still match the canonical templates in the adlc-toolkit. Templates are copied per-repo (not symlinked like skills/agents), so they drift over time. Some drift is **intentional** (project-specific customization); some is **accidental** (toolkit updated and the project never pulled the change). This skill surfaces both and helps you decide what to reconcile.

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Project templates dir: !`ls .adlc/templates/ 2>/dev/null || echo "No .adlc/templates/ directory — run /init first"`
- Toolkit templates dir: !`ls ~/.claude/skills/templates/ 2>/dev/null || echo "Toolkit templates not found at ~/.claude/skills/templates/"`
- Current directory: !`pwd`

## Input

Scope: $ARGUMENTS (optional — single template name to check; otherwise all templates)

## Prerequisites

1. `.adlc/templates/` must exist in the current project. If it does not, stop and tell the user: "This project has no local templates — it uses toolkit templates directly. No drift to check." (New projects per the `/init` Step 6 policy don't copy templates locally.)
2. `~/.claude/skills/templates/` must resolve through the symlink. If it does not, stop and tell the user: "The adlc-toolkit symlink is broken. Verify `readlink ~/.claude/skills` points to the toolkit repo."

## Instructions

### Step 1: Enumerate Templates to Compare

1. If the user passed a scope argument (e.g. `requirement-template`), only check `.adlc/templates/<scope>.md` vs `~/.claude/skills/templates/<scope>.md`.
2. Otherwise list every `*.md` file in `.adlc/templates/` AND every `*.md` file in `~/.claude/skills/templates/`. Compare the union of both sets — this catches templates that exist in the toolkit but not in the project (new templates added upstream) and templates in the project but not in the toolkit (legacy or custom-to-project files).

### Step 2: Diff Each Template

For each template in the comparison set, run `diff -u ~/.claude/skills/templates/<name>.md .adlc/templates/<name>.md`. Capture:
- **Missing upstream**: template exists locally but not in toolkit (legacy or custom)
- **Missing locally**: template exists in toolkit but not in project (upstream added, not yet copied)
- **Identical**: no diff (drift = 0)
- **Drifted**: diff output — count added/removed lines

Also compute a rough drift size: total lines added + total lines removed (excluding context lines). This gives a "how much has changed" number for the summary table.

### Step 3: Classify Drift as Intentional vs Accidental

For each drifted template, **read both full versions** (not just the diff) and make a judgment call. The goal is to separate:

**Intentional customization signals** (do NOT reconcile without explicit user consent):
- Added sections that are domain-specific to this project (e.g. `## System Model`, `## Entities`, `## Permissions`, `## Business Rules` added to a project's local `.adlc/templates/requirement-template.md`)
- Added field names in frontmatter that reference project-specific concepts
- Rewritten wording that reflects a deliberate editorial choice
- Any change that appears in `git log` with a commit message indicating project-specific intent

**Accidental staleness signals** (SHOULD reconcile):
- Toolkit added a new section or field and the project's copy is structurally older
- Cosmetic-only differences (whitespace, placeholder text like `YYYY-MM-DD` vs `[date]`)
- Toolkit renamed/removed a section that the project still has dangling
- Toolkit tightened a rule (e.g. locking a naming convention) and the project's copy still shows the old rule

When in doubt, classify as "needs human review" — do not silently reconcile.

### Step 4: Produce the Drift Report

Emit a summary table, then per-file detail:

```
## Template Drift Report — [date]

Project: <repo name>
Toolkit ref: <`git -C "$(readlink ~/.claude/skills)" rev-parse --short HEAD`>

| Template | Status | Drift | Classification |
|---|---|---|---|
| requirement-template.md | Drifted | +42 / -8 | Intentional (System Model, Entities) |
| task-template.md | Drifted | +3 / -1 | Accidental (cosmetic) |
| bug-template.md | Identical | — | — |
| assumption-template.md | Missing locally | — | Upstream added — needs copy |
| lesson-template.md | Drifted | +6 / -0 | Accidental (upstream added filename lock comment) |

Overall: 3 drifted, 1 missing locally, 1 identical.
Intentional: 1. Accidental: 2. Missing: 1.
```

Then, for each non-identical template, write a short per-file section:

```
### requirement-template.md — Intentional

Project has these sections that the toolkit does not:
- `## System Model` (lines 34–52)
- `## Entities` (lines 54–71)
- `## Permissions` (lines 73–80)
- `## Business Rules` (lines 82–95)

These are project-specific. Do NOT overwrite. No action needed.

Toolkit changes the project is missing (if any):
- <list any upstream changes not yet in the project's copy>
```

```
### task-template.md — Accidental (cosmetic)

Diff is 3 added / 1 removed lines, all whitespace and one field rename:
- `status: [status]` → `status: pending`
- Extra blank line after frontmatter

Action: safe to sync from toolkit. Propose a one-line change: copy `~/.claude/skills/templates/task-template.md` over `.adlc/templates/task-template.md`.
```

### Step 5: Offer Reconciliation Actions

For each **accidental** drift and each **missing locally** template, offer the user a specific action they can take. Format as a numbered list so the user can approve selectively:

```
## Proposed Actions

1. **task-template.md**: Copy from toolkit to project (accidental cosmetic drift).
   Command: `cp ~/.claude/skills/templates/task-template.md .adlc/templates/task-template.md`

2. **lesson-template.md**: Copy from toolkit to project (toolkit added filename-lock comment).
   Command: `cp ~/.claude/skills/templates/lesson-template.md .adlc/templates/lesson-template.md`

3. **assumption-template.md**: Copy from toolkit to project (upstream added, not yet in project).
   Command: `cp ~/.claude/skills/templates/assumption-template.md .adlc/templates/assumption-template.md`

Reply with action numbers to apply (e.g. "1 2 3" or "all"), or "skip" to take no action.
```

**Do not apply any changes without explicit user approval.** Writing to `.adlc/templates/` affects how future `/spec`, `/architect`, and `/bugfix` runs behave, so it's a deliberate choice. If the user approves, apply only the numbered actions they listed and re-run Step 2 for those files to confirm drift is now zero.

For **intentional** drift, do not propose reconciliation — just note it in the report so the user is aware.

### Step 6: Recommend Follow-Up

At the end of the report:
- If all drift is intentional and reconciled: "All templates are in sync or intentionally customized. No action needed."
- If drift remains after user-approved actions: list what's still drifted and suggest running `/template-drift` again after a toolkit update.
- If intentional customizations were found: remind the user to update their project CLAUDE.md or a project-local NOTES file so future toolkit-template updates don't accidentally overwrite them during a merge.

## What This Skill Does NOT Do

- It does not modify toolkit templates — changes to the canonical version go through the adlc-toolkit repo via PR.
- It does not rename or delete project template files — only copies or reports.
- It does not touch `.adlc/templates/` in other projects — it's scoped to the current working directory.
- It does not check drift of skills or agents — those are symlinked, so drift is structurally impossible.

## Implementation Notes

- Use `diff -u` for readable unified diffs. Fall back to `git diff --no-index` if preferred.
- `wc -l` on the diff output is a decent proxy for drift size, but prefer counting `^+` and `^-` lines excluding the `+++`/`---` headers.
- When running under `/status`, this skill should produce a one-line summary only (e.g. "Templates: 2 drifted, 1 missing") rather than the full report. Detect that case by checking whether `$ARGUMENTS` contains `--brief`.
