---
name: review
description: Multi-agent code review for quality, correctness, and convention compliance
argument-hint: Optional file paths, branch name, or REQ/TASK ID to scope the review
---

# /review — Multi-Agent Code Review

You are performing a thorough code review of recent changes in the Atelier Fashion project using multiple specialized review agents.

## Context

- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- Recent changes: !`git diff main --stat 2>/dev/null || echo "No diff available"`
- Conventions: !`cat .sdlc/context/conventions.md 2>/dev/null || echo "No conventions found"`

## Input

Scope: $ARGUMENTS

## Instructions

### Step 1: Determine Review Scope
1. If given specific file paths, review those files
2. If given a branch name, review all changes on that branch vs `main`
3. If given a REQ/TASK ID, find the associated branch and review its changes
4. If no argument, review all uncommitted changes + commits on the current branch vs `main`
5. Get the full diff: `git diff main...HEAD` (or `git diff` for uncommitted changes)

### Step 2: Read All Changed Files
Read the complete current version of every changed file (not just the diff) to understand full context.

### Step 3: Launch Review Agents
Launch 3 specialized review agents in parallel:

**Agent 1 — Correctness & Bugs**
- Logic errors, off-by-one, null/undefined handling
- Race conditions, async/await issues
- Error handling gaps (missing try/catch, unhandled promise rejections)
- Security issues (injection, auth bypass, data exposure)
- Edge cases not covered

**Agent 2 — Code Quality & Conventions**
- Adherence to `.sdlc/context/conventions.md`
- Naming conventions (camelCase JS, kebab-case URLs, snake_case JSON)
- Proper use of logger (no console.log)
- Config centralization (no hardcoded values)
- Code duplication, unnecessary complexity
- Missing or incorrect input validation

**Agent 3 — Architecture & Testing**
- Layered architecture compliance (routes → services → repositories)
- Proper separation of concerns
- Test coverage for new code
- Mock completeness (all exports mocked in test files)
- API response format compliance (`{ error, message }` for errors)
- Backward compatibility of API changes

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
