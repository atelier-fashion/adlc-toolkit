---
name: spec
description: Write requirement specs from feature requests (SDLC Phase 1)
argument-hint: Feature description or request
---

# /spec — Requirement Specification

You are writing a requirement spec for the Atelier Fashion project following the spec-driven SDLC process.

## Context

- SDLC context: !`cat .sdlc/context/project-overview.md 2>/dev/null || echo "No project overview found"`
- Requirement template: !`cat .sdlc/templates/requirement-template.md 2>/dev/null || echo "No requirement template found"`
- Existing specs: !`ls .sdlc/specs/ 2>/dev/null || echo "No specs directory found"`

## Input

Feature request: $ARGUMENTS

## Instructions

### Step 1: Understand the Request
1. Read `.sdlc/context/project-overview.md` for grounding context
2. Read `.sdlc/context/architecture.md` for existing patterns
3. Scan `.sdlc/knowledge/lessons/` — read any lessons relevant to the feature area. Use them to inform assumptions, surface known risks in the spec, and avoid specifying approaches that failed previously.
4. If the feature request is vague or ambiguous, ask clarifying questions before proceeding. Wait for answers.

### Step 2: Determine the Next REQ ID
1. Check for the atomic counter file `.sdlc/.next-req`
2. If it exists, read the number, use it as the REQ ID, and **immediately** write the incremented value back:
   ```bash
   REQ_NUM=$(cat .sdlc/.next-req)
   echo $((REQ_NUM + 1)) > .sdlc/.next-req
   ```
3. If `.sdlc/.next-req` does not exist, fall back to scanning `.sdlc/specs/` for the highest `REQ-xxx` number, use the next one, and create `.sdlc/.next-req` with the number after that:
   ```bash
   # e.g., if highest existing is REQ-024, use REQ-025 and write 26 to .next-req
   echo 26 > .sdlc/.next-req
   ```
4. This avoids collisions when multiple sessions run `/spec` concurrently

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
