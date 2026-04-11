---
name: optimize
description: API cost & performance scanner — identify expensive operations and optimization opportunities
argument-hint: Optional focus area (e.g., "ai", "caching", "queries", "latency")
---

# /optimize — API Cost & Performance Scanner

You are scanning the Atelier Fashion API for cost and performance optimization opportunities.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Architecture: !`cat .sdlc/context/architecture.md 2>/dev/null || echo "No architecture context found"`
- Project overview: !`cat .sdlc/context/project-overview.md 2>/dev/null || echo "No project overview found"`

## Input

Focus: $ARGUMENTS

## Instructions

### Step 1: Determine Focus
1. If given a focus area, prioritize that dimension
2. If no argument, scan all dimensions
3. Read `.sdlc/context/architecture.md` for current caching and optimization patterns

### Step 2: Launch Scanner Agents
Launch 3 specialized agents in parallel:

**Agent 1 — AI/API Cost Analysis**
- Identify all AI API calls (Anthropic Claude, Google Gemini, SerpAPI)
- For each call: which model, estimated token usage, frequency, caching strategy
- Identify calls that could use a cheaper model (e.g., Sonnet → Haiku)
- Check for prompt caching opportunities (`cache_control: { type: 'ephemeral' }`)
- Identify redundant or duplicate AI calls
- Check if responses are being cached effectively (L1 in-memory + L2 Firestore)
- Look for missing cache keys or suboptimal TTLs
- Estimate monthly cost impact of each optimization

**Agent 2 — Database & Storage Performance**
- Firestore query patterns: missing indexes, unbounded queries, N+1 patterns
- GCS operations: unnecessary signed URL generation, missing thumbnail usage
- Pagination: verify all list endpoints use proper pagination (not fetching all docs)
- Atomic operations: verify counter updates use atomic increments
- Batch operations: identify sequential Firestore calls that could be batched
- Cache hit rates: identify frequently accessed data that isn't cached

**Agent 3 — Request Latency & Throughput**
- Identify slow endpoints (sequential async operations that could be parallelized)
- Check for `await` chains that could use `Promise.all`
- Middleware overhead: rate limiter efficiency, auth token verification
- Response payload sizes: over-fetching data, missing field selection
- Image processing: Sharp operations, resize strategies, format optimization
- Cold start impact: module initialization, lazy loading opportunities

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
3. Suggest which items warrant a full SDLC requirement (candidates for `/spec`)
