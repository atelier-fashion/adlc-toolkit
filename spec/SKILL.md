---
name: spec
description: Write requirement specs from feature requests
argument-hint: Feature description or request
---

# /spec — Requirement Specification

You are writing a requirement spec for the Atelier Fashion project following the spec-driven SDLC process.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- SDLC context: !`cat .sdlc/context/project-overview.md 2>/dev/null || echo "No project overview found"`
- Requirement template: !`cat .sdlc/templates/requirement-template.md 2>/dev/null || cat ~/.claude/skills/templates/requirement-template.md 2>/dev/null || echo "No requirement template found"`
- Active specs: !`grep -rl 'status: draft\|status: approved\|status: in-progress' .sdlc/specs/*/requirement.md 2>/dev/null | head -20 || echo "No active specs"`

## Input

Feature request: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.sdlc/context/project-overview.md` exists. If it doesn't, stop and tell the user: "The `.sdlc/` structure hasn't been initialized. Run `/init` first to set up the project context."

## Instructions

### Step 1: Understand the Request
1. Read `.sdlc/context/project-overview.md` for grounding context (skip if already in conversation)
2. Read `.sdlc/context/architecture.md` for existing patterns (skip if already in conversation)
3. **Lessons — grep first, then read only matches**: use the Grep tool on `.sdlc/knowledge/lessons/` with patterns like `component:.*<affected-area>` or `domain:.*<domain>` matching the feature area (e.g., for an API auth feature, grep `component:.*API/auth` or `domain:.*API`). Then Read ONLY the matched files. Do NOT read all lessons. Use them to inform assumptions, surface known risks in the spec, and avoid specifying approaches that failed previously.
4. If the feature request is vague or ambiguous, ask clarifying questions before proceeding. Wait for answers.

### Step 2: Determine the Next REQ ID
1. Use the **global** atomic counter file `~/.claude/.global-next-req` (shared across all repos for unique IDs)
2. Read the number, use it as the REQ ID, and **immediately** write the incremented value back — using `flock` to prevent concurrent collisions:
   ```bash
   REQ_NUM=$(flock ~/.claude/.global-next-req.lock bash -c '
     NUM=$(cat ~/.claude/.global-next-req)
     echo $((NUM + 1)) > ~/.claude/.global-next-req
     echo $NUM
   ')
   ```
3. If `~/.claude/.global-next-req` does not exist, create it by scanning all `.sdlc/specs/` directories under `~/Documents/GitHub/` for the highest `REQ-xxx` number, use the next one, and write the number after that:
   ```bash
   HIGHEST=$(find ~/Documents/GitHub -path '*/.sdlc/specs/REQ-*' -type d 2>/dev/null | grep -oP 'REQ-\K\d+' | sort -n | tail -1)
   REQ_NUM=$((HIGHEST + 1))
   echo $((REQ_NUM + 1)) > ~/.claude/.global-next-req
   ```
4. The `flock` ensures that concurrent `/sprint` sessions don't read the same counter value

### Step 3: Create the Requirement Spec
1. Create directory: `.sdlc/specs/REQ-xxx-feature-slug/`
2. Create `requirement.md` using the template from `.sdlc/templates/requirement-template.md`
3. Fill in all sections:
   - **Frontmatter**: id, title, status (`draft`), created date, updated date
   - **Description**: What the feature does and why — be specific and grounded in the project context
   - **Acceptance Criteria**: Concrete, testable criteria as checkboxes
   - **External Dependencies**: Any new APIs, services, or libraries needed
   - **Assumptions**: Things assumed to be true that could affect the design
   - **Questions**: Open questions that need answers before implementation
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
