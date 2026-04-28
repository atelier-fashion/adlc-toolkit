---
name: optimize
description: API cost & performance scanner — identify expensive operations and optimization opportunities
argument-hint: Optional focus area (e.g., "ai", "caching", "queries", "latency")
---

# /optimize — API Cost & Performance Scanner

You are scanning this project's API and infrastructure for cost and performance optimization opportunities.

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Architecture: !`cat .adlc/context/architecture.md 2>/dev/null || echo "No architecture context found"`
- Project overview: !`cat .adlc/context/project-overview.md 2>/dev/null || echo "No project overview found"`

## Input

Focus: $ARGUMENTS

## Instructions

### Step 1: Determine Focus
1. If given a focus area, prioritize that dimension
2. If no argument, scan all dimensions
3. Read `.adlc/context/architecture.md` for current caching and optimization patterns

### Step 2: Launch Scanner Agents
Launch 3 formal scanner agents in parallel using the Agent tool. Each agent is defined in `~/.claude/agents/` with its full scanning checklist and model selection (sonnet for deep analysis).

1. **api-cost-scanner** agent — provide the focus scope and architecture.md for caching context
2. **db-perf-scanner** agent — provide the focus scope
3. **latency-scanner** agent — provide the focus scope

Each agent returns structured findings with estimated impact, effort, and risk.

### Step 3: Build Optimization Report

#### Cost Summary
| Service | Est. Monthly Usage | Est. Monthly Cost | Top Optimization |
|---------|-------------------|-------------------|------------------|
| Claude Sonnet | X calls | $X | ... |
| Claude Haiku | X calls | $X | ... |
| Gemini Flash | X calls | $X | ... |
| SerpAPI | X calls | $X | ... |
| Firestore | X reads/writes | $X | ... |
| GCS | X operations | $X | ... |

#### Performance Hotspots
Rank endpoints by estimated latency, highlighting:
- Sequential operations that could be parallel
- Missing caches
- N+1 query patterns
- Unnecessary data fetching

#### Optimization Opportunities
For each opportunity:
- **What**: Description of the optimization
- **Impact**: Cost savings or latency reduction estimate
- **Effort**: Small / Medium / Large
- **Risk**: Low / Medium / High (chance of breaking something)

### Step 4: Prioritized Recommendations
1. Rank optimizations by impact/effort ratio
2. Group into quick wins (small effort, high impact) and strategic improvements
3. Suggest which items warrant a full ADLC requirement (candidates for `/spec`)
