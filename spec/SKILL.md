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
3. **Lessons — grep first, then read only matches**: use the Grep tool on `.adlc/knowledge/lessons/` with patterns like `component:.*<affected-area>` or `domain:.*<domain>` matching the feature area (e.g., for an API auth feature, grep `component:.*API/auth` or `domain:.*API`). Then Read ONLY the matched files. Do NOT read all lessons. Use them to inform assumptions, surface known risks in the spec, and avoid specifying approaches that failed previously.
4. If the feature request is vague or ambiguous, ask clarifying questions before proceeding. Wait for answers.

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
   - **Frontmatter**: id, title, status (`draft`), created date, updated date
   - **Description**: What the feature does and why — be specific and grounded in the project context
   - **System Model**: Structured data model — Entities (fields, types, constraints), Events (triggers, payloads), Permissions (actions, roles). Remove sub-sections that don't apply to this feature.
   - **Business Rules**: Explicit, testable constraints governing behavior (e.g., "Only item owner can delete"). Numbered BR-1, BR-2, etc.
   - **Acceptance Criteria**: Concrete, testable criteria as checkboxes
   - **External Dependencies**: Any new APIs, services, or libraries needed
   - **Assumptions**: Things assumed to be true that could affect the design
   - **Open Questions**: Questions that need answers before implementation
   - **Out of Scope**: Items explicitly excluded to prevent scope creep

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
