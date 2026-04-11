---
name: review
description: Multi-agent code review for quality, correctness, and convention compliance
argument-hint: Optional file paths, branch name, or REQ/TASK ID to scope the review
---

# /review — Multi-Agent Code Review

You are performing a thorough code review of recent changes in the Atelier Fashion project using multiple specialized review agents.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- Recent changes: !`git diff main --stat 2>/dev/null || echo "No diff available"`

**Context files loaded on demand**: `.sdlc/context/conventions.md` is loaded by Step 1 below — **skip the Read if it is already in the current conversation** (e.g., when invoked from `/proceed`, which preloads it at Phase 0).

## Input

Scope: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.sdlc/context/conventions.md` exists. If it doesn't, stop and tell the user: "The `.sdlc/` structure hasn't been initialized. Run `/init` first to set up conventions."

## Instructions

### Step 1: Determine Review Scope
1. If given specific file paths, review those files
2. If given a branch name, review all changes on that branch vs `main`
3. If given a REQ/TASK ID, find the associated branch and review its changes
4. If no argument, review all uncommitted changes + commits on the current branch vs `main`
5. Get the full diff: `git diff main...HEAD` (or `git diff` for uncommitted changes)
6. **Context files**: if `.sdlc/context/conventions.md` is NOT already in your conversation context, Read it now. Otherwise skip — it's already loaded.

### Step 2: Read All Changed Files
Read the complete current version of every changed file (not just the diff) to understand full context.

### Step 3: Launch Review Agents
Launch 3 formal review agents in parallel using the Agent tool. Each agent is defined in `~/.claude/agents/` with its full checklist, model selection, and tool restrictions.

1. **correctness-reviewer** agent — provide it the list of changed files, the full diff, and conventions.md content. Tell it: "Report findings only. Do not apply fixes."
2. **quality-reviewer** agent — provide it the list of changed files, the full diff, and conventions.md content. Tell it: "Report findings only. Do not apply fixes."
3. **architecture-reviewer** agent — provide it the list of changed files, the full diff, and architecture.md content. Tell it: "Report findings only. Do not apply fixes."

Each agent returns structured findings with severity (Critical/Major/Minor/Nit), file path, line number, and suggested fix.

### Step 4: Consolidate Findings
1. Collect results from all 3 agents
2. Deduplicate overlapping findings
3. Categorize by severity:
   - **Critical**: Must fix before merge (bugs, security, data loss)
   - **Major**: Should fix before merge (convention violations, missing tests)
   - **Minor**: Nice to fix (style, naming, minor improvements)
   - **Nit**: Optional suggestions

### Step 5: Present Review
Display findings organized by file, then by severity within each file:

```
## file/path.js

### Critical
- Line XX: description of issue

### Major
- Line XX: description of issue
```

### Step 6: Summary
1. Overall assessment: Ready to merge / Needs fixes / Needs significant rework
2. Count of issues by severity
3. Top 3 most important things to address
4. If changes look good, say so clearly
