---
name: review
description: Multi-agent code review covering correctness, quality, architecture, test coverage, and security
argument-hint: Optional file paths, branch name, or REQ/TASK ID to scope the review
---

# /review — Multi-Agent Code Review

You are performing a thorough code review of recent changes in the Atelier Fashion project using multiple specialized review agents.

This skill is the **pre-push ADLC review gate**. It runs 5 specialized review agents in parallel, covering the same dimensions the CI `llm-review` workflow would cover if it ran (correctness, conventions, test coverage, security) plus an architecture dimension the CI workflow doesn't have. Running this before pushing means the ADLC gate catches issues regardless of whether the CI layer is available — CI-layer LLM reviews can be blocked (billing, infra, outages) and must not become the sole safety net.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- Recent changes: !`git diff main --stat 2>/dev/null || echo "No diff available"`

**Context files loaded on demand**: `.adlc/context/conventions.md` and recent lessons are loaded by Step 1 below — **skip the Reads if they are already in the current conversation** (e.g., when invoked from `/proceed`, which preloads `conventions.md` at Phase 0).

## Input

Scope: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.adlc/context/conventions.md` exists. If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` first to set up conventions."

## Instructions

### Step 1: Determine Review Scope and Load Context
1. If given specific file paths, review those files
2. If given a branch name, review all changes on that branch vs `main`
3. If given a REQ/TASK ID, find the associated branch and review its changes
4. If no argument, review all uncommitted changes + commits on the current branch vs `main`
5. Get the full diff: `git diff main...HEAD` (or `git diff` for uncommitted changes)
6. **Conventions**: if `.adlc/context/conventions.md` is NOT already in your conversation context, Read it now. Otherwise skip — it's already loaded.
7. **Relevant lessons** (mirrors the spirit of `llm-review.yml`, but relevance-ranked instead of time-ranked):
   a. Derive the set of touched **components** from the diff. Components are inferred from file paths — e.g. `api/auth/*` → `API/auth`, `app/Sources/Views/*.swift` → `iOS/SwiftUI`, `admin-api/src/users/*` → `API/admin/users`, `infrastructure/terraform/*` → `infra/terraform`. Produce a short list of plausible `component` values and a broader list of `domain` values (e.g. `API`, `iOS`, `infra`).
   b. Glob `.adlc/knowledge/lessons/*.md` and read each file's frontmatter (`domain`, `component`, `tags`). Keep lessons where `component` matches any touched component exactly, OR where `domain` matches any touched domain AND `component` is a prefix of a touched component, OR where any tag matches a touched component/domain. This is the **relevance set**.
   c. If the relevance set has fewer than 5 entries, top it up with the most recently modified lessons from `.adlc/knowledge/lessons/` (the previous time-based heuristic) until the set has up to 10 entries. This keeps small or cross-cutting diffs from losing context entirely.
   d. Cap the final list at 15 lessons. Read their bodies in full.
   e. Pass the content of every selected lesson as context to every review agent in Step 3. When a finding later matches one of these lessons, cite its `id` explicitly (Step 4 uses this to elevate severity).
   **Fallback**: if any lesson has no `component` / `domain` / `tags` frontmatter (legacy file), fall back to reading its title + first paragraph and include it only if the title contains any touched domain or component substring. Do not skip it silently — it may be load-bearing.

### Step 2: Read All Changed Files
Read the complete current version of every changed file (not just the diff) to understand full context.

### Step 3: Launch Review Agents
Launch **5 formal review agents in parallel** using the Agent tool. Each agent is defined in `~/.claude/agents/` with its full checklist, model selection, and tool restrictions. Running in parallel minimizes wall-clock time.

1. **correctness-reviewer** agent — provide it the list of changed files, the full diff, `conventions.md` content, and recent lessons. Focus: logic errors, null risks, race conditions, edge cases, concurrency bugs. Tell it: "Report findings only. Do not apply fixes."
2. **quality-reviewer** agent — same inputs. Focus: naming, convention compliance, code duplication, complexity, maintainability. Tell it: "Report findings only. Do not apply fixes."
3. **architecture-reviewer** agent — same inputs plus `architecture.md` content. Focus: layering, separation of concerns, API contracts, module boundaries, scope discipline. Tell it: "Report findings only. Do not apply fixes."
4. **test-auditor** agent — same inputs. Focus: test coverage gaps for the changed code, mock completeness, edge case coverage, test isolation, determinism. Tell it: "Audit test coverage only for the diff under review. Report findings only. Do not apply fixes."
5. **security-auditor** agent — same inputs. Focus: input validation, authentication/authorization gaps, data exposure (PII, secrets), injection risks, dependency issues, rate limiting. Tell it: "Audit security posture only for the diff under review. Report findings only. Do not apply fixes."

Each agent returns structured findings with severity (Critical/Major/Minor/Nit), file path, line number, and suggested fix.

**Gate rule** (mirrors `llm-review.yml`): if ANY agent reports a `Critical` finding, the review gate FAILS and the changes are not ready to merge. Fix critical findings before proceeding to push. Major findings should typically be fixed before merge but can be escalated to the user for judgment calls.

### Step 4: Consolidate Findings
1. Collect results from all 5 agents
2. Deduplicate overlapping findings
3. Categorize by severity:
   - **Critical**: Must fix before merge (bugs, security, data loss, test gaps that hide regressions)
   - **Major**: Should fix before merge (convention violations, missing tests, architectural smells)
   - **Minor**: Nice to fix (style, naming, minor improvements)
   - **Nit**: Optional suggestions
4. Cross-reference findings against the loaded recent lessons — if a finding matches a known pitfall, escalate its severity by one level (e.g., a Minor finding that matches a prior LESSON becomes a Major). Flag this explicitly in the report.

### Step 5: Present Review
Display findings organized by file, then by severity within each file. Include a dimension summary at the top so the user can see which of the 5 dimensions have issues at a glance:

```
## Dimension Summary

| Dimension | Critical | Major | Minor | Nit | Gate |
|---|---|---|---|---|---|
| Correctness | 0 | 1 | 2 | 0 | PASS |
| Quality | 0 | 0 | 3 | 1 | PASS |
| Architecture | 0 | 2 | 0 | 0 | PASS |
| Test Coverage | 0 | 0 | 1 | 0 | PASS |
| Security | 0 | 0 | 0 | 0 | PASS |

**Overall gate: PASS / FAIL**

## file/path.js

### Critical
- Line XX: description of issue

### Major
- Line XX: description of issue
```

### Step 6: Summary
1. Overall gate: PASS (ready to merge) / FAIL (fix criticals first) / RESHAPE (significant rework needed)
2. Count of issues by severity and by dimension
3. Top 3 most important things to address
4. Any findings that matched recent lessons (elevated-severity items)
5. If changes look good, say so clearly — an empty review is a valid result for small, well-scoped changes
