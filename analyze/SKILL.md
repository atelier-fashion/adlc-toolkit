---
name: analyze
description: Codebase health audit — identify technical debt, quality issues, and improvement opportunities
argument-hint: Optional scope (e.g., "api", "app", specific directory, or focus area like "security")
---

# /analyze — Codebase Health Audit

You are performing a comprehensive codebase health audit for the Atelier Fashion project.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

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

### Step 2: Launch Audit Agents
Launch 4 formal audit agents in parallel using the Agent tool. Each agent is defined in `~/.claude/agents/` with its full audit checklist, model selection (sonnet for deep analysis, haiku for pattern matching), and tool restrictions.

1. **code-quality-auditor** agent — provide the audit scope determined in Step 1
2. **convention-auditor** agent — provide the audit scope and conventions.md content
3. **security-auditor** agent — provide the audit scope
4. **test-auditor** agent — provide the audit scope

Each agent returns structured findings with severity, file paths, and descriptions.

### Step 3: Consolidate Results
Organize findings into a health report:

#### Health Scorecard
| Dimension | Score | Summary |
|-----------|-------|---------|
| Code Quality | A-F | Key findings |
| Convention Compliance | A-F | Key findings |
| Security | A-F | Key findings |
| Testing | A-F | Key findings |
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
