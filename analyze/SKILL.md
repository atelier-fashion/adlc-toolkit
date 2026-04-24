---
name: analyze
description: Codebase health audit — identify technical debt, quality issues, and improvement opportunities
argument-hint: Optional scope (e.g., "api", "app", specific directory, or focus area like "security")
---

# /analyze — Codebase Health Audit

You are performing a comprehensive codebase health audit for the current project.

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Architecture: !`cat .adlc/context/architecture.md 2>/dev/null || echo "No architecture context found"`
- Conventions: !`cat .adlc/context/conventions.md 2>/dev/null || echo "No conventions found"`

## Input

Scope: $ARGUMENTS

## Instructions

### Step 1: Determine Scope
1. If given a specific directory or area, focus the audit there
2. If given a focus area (e.g., "security", "testing", "performance"), prioritize that dimension
3. If no argument, audit the entire project

### Step 2: Launch Audit Agents + Repo Hygiene Scan (parallel)
In a single message, launch the 4 audit agents AND run the repo hygiene bash checks below in parallel. The agents live in `~/.claude/agents/` with their full audit checklists, model selection (sonnet for deep analysis, haiku for pattern matching), and tool restrictions.

1. **code-quality-auditor** agent — provide the audit scope determined in Step 1
2. **convention-auditor** agent — provide the audit scope and conventions.md content
3. **security-auditor** agent — provide the audit scope
4. **test-auditor** agent — provide the audit scope
5. **Repo Hygiene** (inline bash, not an agent) — see Step 2a below

Each agent returns structured findings with severity, file paths, and descriptions.

### Step 2a: Repo Hygiene Checks
Run these bash checks directly (do not spawn an agent). Adapt the commands to the repo — skip remote checks if no `origin`, pick the correct default branch (`main` or `master`), etc.

**Stale branches (local and remote, no commits in 90+ days):**
```bash
# Portable cutoff date (GNU vs BSD date)
CUTOFF=$(date -d '90 days ago' +%Y-%m-%d 2>/dev/null || date -v-90d +%Y-%m-%d)

# Local stale branches
git for-each-ref --sort=committerdate refs/heads/ \
  --format='%(committerdate:short) %(refname:short) %(authorname)' \
  | awk -v c="$CUTOFF" '$1 < c'

# Remote stale branches (origin)
git for-each-ref --sort=committerdate refs/remotes/origin/ \
  --format='%(committerdate:short) %(refname:short) %(authorname)' \
  | awk -v c="$CUTOFF" '$1 < c && $2 !~ /HEAD/'

# Branches already merged into the default branch (safe to delete)
DEFAULT=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@' || echo main)
git branch --merged "$DEFAULT" | grep -vE "^\*|^  ($DEFAULT|master)$"
git branch -r --merged "origin/$DEFAULT" | grep -vE "origin/(HEAD|$DEFAULT|master)"
```

**Duplicate files (identical content):**
```bash
# Hash every tracked file and group by identical content
git ls-files -z | xargs -0 shasum 2>/dev/null \
  | sort | awk '{h=$1; $1=""; sub(/^ /,""); map[h]=map[h] ORS $0; count[h]++} END {for (h in count) if (count[h]>1) print "== "h" =="map[h]}'
```

**Unreferenced files (candidates — require judgment before acting):**
For each source file, check whether its basename appears in any other file. Flag files whose basename (sans extension) has zero references outside itself. Entrypoints (`main`, `index`, config files, test fixtures, docs) are expected to be unreferenced — filter those out before reporting. Use Grep tool with the filename-without-extension as the pattern.

Treat results as **candidates**, not verdicts. Module systems with dynamic imports, string-based config loads, or framework conventions (e.g., Next.js page routing) will produce false positives.

### Step 3: Consolidate Results
Organize findings into a health report:

#### Health Scorecard
| Dimension | Score | Summary |
|-----------|-------|---------|
| Code Quality | A-F | Key findings |
| Convention Compliance | A-F | Key findings |
| Security | A-F | Key findings |
| Testing | A-F | Key findings |
| Repo Hygiene | A-F | Stale branches, duplicate/unused files |
| **Overall** | **A-F** | |

#### Critical Issues (fix now)
Issues that pose immediate risk — security vulnerabilities, data loss potential, broken functionality.

#### Technical Debt (fix soon)
Issues that slow development or increase risk over time — duplicated code, missing tests, convention drift.

#### Improvement Opportunities (fix later)
Nice-to-have improvements — refactoring opportunities, performance optimizations, developer experience.

### Step 4: Recommendations
1. Rank the top 5 most impactful improvements
2. For each, estimate effort (small/medium/large) and impact (low/medium/high)
3. Suggest which items could become ADLC requirements (candidates for `/spec`)
