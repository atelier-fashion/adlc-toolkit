---
name: analyze
description: Codebase health audit — identify technical debt, quality issues, and improvement opportunities
argument-hint: Optional scope (e.g., "api", "app", specific directory, or focus area like "security")
---

# /analyze — Codebase Health Audit

You are performing a comprehensive codebase health audit for the Atelier Fashion project.

## Context

- Architecture: !`cat .sdlc/context/architecture.md 2>/dev/null || echo "No architecture context found"`
- Conventions: !`cat .sdlc/context/conventions.md 2>/dev/null || echo "No conventions found"`

## Input

Scope: $ARGUMENTS

## Instructions

### Step 1: Determine Scope
1. If given a specific directory or area, focus the audit there
2. If given a focus area (e.g., "security", "testing", "performance"), prioritize that dimension
3. If no argument, audit the entire project

### Step 2: Launch Audit Agents
Launch 4 specialized agents in parallel:

**Agent 1 — Code Quality & Technical Debt**
- Dead code (unused exports, unreachable branches)
- Code duplication across files
- Overly complex functions (high cyclomatic complexity)
- Inconsistent patterns (doing the same thing different ways)
- TODOs, FIXMEs, and HACKs in the codebase
- Files that are too large or have too many responsibilities

**Agent 2 — Convention Compliance**
- Naming violations (files, variables, routes, constants)
- Logging violations (console.log instead of logger)
- Hardcoded values that should be in config
- API response format inconsistencies
- Error handling pattern violations
- Import/export style consistency (ESM)

**Agent 3 — Security & Reliability**
- Input validation gaps (missing or insufficient)
- Authentication/authorization bypass risks
- Sensitive data exposure (PII in logs, unencrypted fields)
- Rate limiting coverage (unprotected expensive endpoints)
- Error messages leaking internal details
- Dependency vulnerabilities (`npm audit`)

**Agent 4 — Testing & Coverage**
- Test coverage gaps (run `npm test -- --coverage` if in API)
- Missing test cases for error paths
- Mock completeness (all module exports included)
- Test quality (testing behavior vs implementation details)
- Integration test coverage for API routes

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
3. Suggest which items could become SDLC requirements (candidates for `/spec`)
