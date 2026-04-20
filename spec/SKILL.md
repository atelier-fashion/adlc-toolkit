---
name: spec
description: Write requirement specs from feature requests
argument-hint: Feature description or request
---

# /spec — Requirement Specification

You are writing a requirement spec for the Atelier Fashion project following the spec-driven ADLC process.

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- ADLC context: !`cat .adlc/context/project-overview.md 2>/dev/null || echo "No project overview found"`
- Requirement template: !`cat .adlc/templates/requirement-template.md 2>/dev/null || cat ~/.claude/skills/templates/requirement-template.md 2>/dev/null || echo "No requirement template found"`
- Active specs: !`grep -rl 'status: draft\|status: approved\|status: in-progress' .adlc/specs/*/requirement.md 2>/dev/null | head -20 || echo "No active specs"`

## Input

Feature request: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.adlc/context/project-overview.md` exists. If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` first to set up the project context."

## Instructions

### Step 1: Understand the Request
1. Read `.adlc/context/project-overview.md` for grounding context (skip if already in conversation)
2. Read `.adlc/context/architecture.md` for existing patterns (skip if already in conversation)
3. If the feature request is vague or ambiguous, ask clarifying questions before proceeding. Wait for answers.

### Step 1.5: Derive Query Tags for Retrieval

Before retrieval fires, derive a structured query from the feature request. This query drives both context loading (Step 1.6) and the self-tagging of the new REQ (Step 3).

1. Read the feature request in `$ARGUMENTS` alongside any grounding context already in conversation. Extract likely area signals:
   - **component** — which narrow area this touches (e.g., `API/auth`, `iOS/SwiftUI`, `adlc/spec`)
   - **domain** — broader problem domain (e.g., `auth`, `payments`, `ui`, `adlc`)
   - **stack** — tech layers implicated (e.g., `express`, `firestore`, `swiftui`, `markdown`)
   - **concerns** — cross-cutting dimensions (e.g., `security`, `perf`, `a11y`, `retrieval`)
   - **tags** — free-form keywords from the feature description (e.g., `password-reset`, `pagination`, `caching`)
2. Construct the query object:
   ```
   query = {
     component: "<proposed>",
     domain: "<proposed>",
     stack: [<proposed>],
     concerns: [<proposed>],
     tags: [<proposed>]
   }
   ```
3. **Interactive mode** (manual `/spec` invocation): surface the proposed query to the user and wait for confirmation or edits:
   ```
   Proposed retrieval query for this feature:
     component: <value>
     domain:    <value>
     stack:     [<values>]
     concerns:  [<values>]
     tags:      [<values>]
   Confirm or edit any field before retrieval fires.
   ```
4. **Pipeline mode** (invoked from `/proceed`): do NOT block for user input. Use the proposed tags directly. If `/proceed` passed inherited tags via invocation context, use those instead of the proposed ones.
5. Retain the confirmed `query` object. It is reused by Step 1.6 (retrieval) and Step 3 (self-tagging the new REQ's frontmatter).

### Step 1.6: Unified Retrieval Across Corpora

Run a weighted-score retrieval over three corpora using the query from Step 1.5. This is the only retrieval behavior — the prior 3-tier lesson grep is removed.

1. **Enumerate candidate files** with three Grep passes (paths relative to project root):
   - `.adlc/knowledge/lessons/*.md` — no status filter, all lessons are candidates
   - `.adlc/specs/*/requirement.md` — include only where frontmatter `status` is `approved`, `in-progress`, or `deployed`
   - `.adlc/bugs/*.md` — include only where frontmatter `status` is `resolved`

   If any directory is empty or missing, skip it and continue (cold-start path).

2. **Read the frontmatter of every candidate** using Read with `limit: 20` (enough to cover frontmatter block). Parse these fields: `component`, `domain`, `stack`, `concerns`, `tags`, `updated`, `created`, `status`. If the frontmatter is malformed (missing `---` delimiters, unparseable YAML), skip that doc and continue — do not crash.

3. **Compute a weighted score per candidate** using the following rule:
   - `+3` if `doc.component == query.component`
   - `+2` if `doc.domain == query.domain`
   - `+2 × |doc.concerns ∩ query.concerns|`
   - `+1 × |doc.stack ∩ query.stack|`
   - `+1 × |doc.tags ∩ query.tags|`
   - `+1` foundational floor **only for lesson documents** with none of the five tag fields populated. Specs and bugs with zero tag overlap score `0`.

4. **Filter** out every doc with final score `0`.

5. **Sort** descending by score. **Tiebreak**: newer `updated` wins; when `updated` is missing, fall back through `created` → file mtime → stable alphabetical by `id`. When two docs share the same date, corpus priority is `lesson > bug > spec`.

6. **Take the top 15 globally** across all corpora. There are no per-corpus quotas (no minimum-lesson floor, no maximum-bug cap). If fewer than 15 candidates survive filtering, take what is available.

7. **Read the full body** of each top-15 doc into context.

8. **Surface the retrieval summary** to the user before authoring continues. This is always shown — there is no verbose flag gate:
   ```
   Retrieved context for this REQ:
     LESSON-034 (lesson, score 5): Silent failure remediation
     BUG-012    (bug,    score 5): Auth rate-limit bypass
     REQ-019    (spec,   score 3): Prior login redesign
     ... (etc.)
   ```

9. **Cold-start path**: if every corpus is empty, or all candidates filter out to zero, skip retrieval and record this explicitly when Step 3 writes the `## Retrieved Context` section. Proceed to authoring without retrieved bodies.

### Step 2: Determine the Next REQ ID
1. Use the **global** atomic counter file `~/.claude/.global-next-req` (shared across all repos for unique IDs)
2. Read the number, use it as the REQ ID, and **immediately** write the incremented value back — using a POSIX `mkdir`-based lock to prevent concurrent collisions (works on macOS and Linux; `flock` is not available by default on macOS):
   ```bash
   REQ_NUM=$(
     LOCK=~/.claude/.global-next-req.lock.d
     for _ in $(seq 50); do mkdir "$LOCK" 2>/dev/null && break; sleep 0.1; done
     NUM=$(cat ~/.claude/.global-next-req)
     echo $((NUM + 1)) > ~/.claude/.global-next-req
     rmdir "$LOCK" 2>/dev/null
     echo $NUM
   )
   ```
3. If `~/.claude/.global-next-req` does not exist, create it by scanning all `.adlc/specs/` directories under `~/Documents/GitHub/` for the highest `REQ-xxx` number, use the next one, and write the number after that. Use `grep -oE` + `sed` (BSD-compatible) instead of `grep -oP` (GNU-only):
   ```bash
   HIGHEST=$(find ~/Documents/GitHub -path '*/.adlc/specs/REQ-*' -type d 2>/dev/null \
     | grep -oE 'REQ-[0-9]+' | sed 's/REQ-//' | sort -n | tail -1)
   REQ_NUM=$((HIGHEST + 1))
   echo $((REQ_NUM + 1)) > ~/.claude/.global-next-req
   ```
4. The `mkdir` lock ensures that concurrent `/sprint` sessions don't read the same counter value. `mkdir` is atomic on all POSIX filesystems — if another process holds the lock, the retry loop waits up to ~5 seconds.

### Step 3: Create the Requirement Spec
1. Create directory: `.adlc/specs/REQ-xxx-feature-slug/`
2. Create `requirement.md` using the template from `.adlc/templates/requirement-template.md`
3. Fill in all sections:
   - **Frontmatter**: id, title, status (`draft`), created date, updated date, AND the five query tags from Step 1.5 — `component`, `domain`, `stack`, `concerns`, `tags`. This self-tagging makes the new REQ retrievable for future `/spec` invocations (per REQ-258 BR-7).
   - **Description**: What the feature does and why — be specific and grounded in the project context
   - **System Model**: Structured data model — Entities (fields, types, constraints), Events (triggers, payloads), Permissions (actions, roles). Remove sub-sections that don't apply to this feature.
   - **Business Rules**: Explicit, testable constraints governing behavior (e.g., "Only item owner can delete"). Numbered BR-1, BR-2, etc.
   - **Acceptance Criteria**: Concrete, testable criteria as checkboxes
   - **External Dependencies**: Any new APIs, services, or libraries needed
   - **Assumptions**: Things assumed to be true that could affect the design
   - **Open Questions**: Questions that need answers before implementation
   - **Out of Scope**: Items explicitly excluded to prevent scope creep
   - **Retrieved Context** (NEW, always present): append a `## Retrieved Context` section at the end of the spec listing every retrieved source from Step 1.6.8 in the form `ID (corpus, score): title`. If no context was retrieved (cold-start path), write exactly: `No prior context retrieved — first REQ in this area.`
4. **Inline citations**: when a retrieved doc directly informed a Business Rule, Assumption, or Acceptance Criterion, add an inline citation in the form `(informed by BUG-012)` or `(informed by REQ-019, LESSON-034)` at the end of that line. Citations are required when the retrieved doc is load-bearing for the rule; optional when the doc was background reading only.

### Step 4: Present for Review
1. Display the full requirement spec to the user
2. Highlight any assumptions or open questions that need input
3. Remind the user to run `/validate` before advancing to `/architect`

## Quality Checklist
- [ ] Acceptance criteria are specific and testable (not vague)
- [ ] Description explains the "why" not just the "what"
- [ ] Assumptions are explicitly stated
- [ ] Out of scope items prevent scope creep
- [ ] No implementation details leaked into the requirement (that's for architecture phase)
- [ ] Retrieved Context section present
