---
name: validate
description: Validate any ADLC phase output before advancing
argument-hint: REQ-xxx ID or phase name (spec, architecture, tasks, implementation)
---

# /validate — ADLC Phase Validation

You are validating ADLC artifacts to ensure quality before advancing to the next phase.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Active specs: !`grep -rl 'status: draft\|status: approved\|status: in-progress' .adlc/specs/*/requirement.md 2>/dev/null | head -20 || echo "No active specs"`

## Input

Target: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.adlc/specs/` exists. If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` first."

## Instructions

### Step 1: Identify What to Validate
1. If given a REQ ID, locate all artifacts under `.adlc/specs/REQ-xxx-*/`
2. If given a phase name, validate the most recently modified artifacts for that phase
3. Determine the current phase based on what artifacts exist:
   - **Spec phase**: Only `requirement.md` exists
   - **Architecture phase**: `architecture.md` exists alongside requirement
   - **Task phase**: `tasks/` directory with task files exists
   - **Implementation phase**: Tasks have status `complete` or code changes exist

### Step 2: Validate Based on Phase

#### Validating a Requirement Spec
- [ ] Frontmatter has valid id, title, status, created, updated fields
- [ ] Description clearly explains what AND why
- [ ] Acceptance criteria are specific, testable, and use checkbox format
- [ ] No implementation details in the requirement (belongs in architecture)
- [ ] Assumptions are explicitly stated
- [ ] Out of scope items are defined to prevent scope creep
- [ ] External dependencies are identified
- [ ] No duplicate or overlapping requirements with existing specs

#### Validating Architecture
- [ ] Architecture follows existing patterns from `.adlc/context/architecture.md`
- [ ] New ADRs include rationale (not just decisions)
- [ ] Data model changes are compatible with existing Firestore schema
- [ ] API endpoint design follows REST conventions from `.adlc/context/conventions.md`
- [ ] Service layer follows the layered pattern (routes → services → repositories)
- [ ] No architectural conflicts with other in-progress requirements

#### Validating Tasks
- [ ] Every task has valid frontmatter (id, title, status, parent, created, updated, dependencies)
- [ ] Tasks form a valid DAG — no circular dependencies (including cross-repo dependencies)
- [ ] Every acceptance criterion from the requirement is covered by at least one task
- [ ] Each task lists specific files to create/modify
- [ ] Tasks are appropriately scoped (not too large, not too granular)
- [ ] Test requirements are included in task acceptance criteria
- [ ] Dependencies reference valid task IDs

**Verification obligations (REQ-595)** — three checks over the task set's
`## Verification` blocks (shape defined in `.adlc/templates/task-template.md`).
Read the REQ's rules at run time; never carry a copy of them here, because an
enumeration in a skill rots the moment a spec changes.

A task file with **no** `## Verification` section is valid. Its absence is
reported by the coverage check below, not treated as a malformed task.

- [ ] **Obligation coverage** — every numbered **BR and AC** in the REQ is cited by
      at least one task's `## Verification` block. Report the unmapped ids by name.
      **Severity: Warning (advisory, non-blocking) in epoch 1.**
      - ACs are addressed by **1-based ordinal** within the REQ's
        `## Acceptance Criteria` list — the requirement template does not print AC
        numbers, so position is the addressing.
      - BR and AC coverage are gated **on the same footing**. Acceptance criteria do
        not reduce to business rules — a REQ can carry ACs with no one-to-one BR —
        so reporting BRs alone would leave half the omission class open.
      - A REQ with **zero numbered BRs** passes trivially: emit a notice and move
        on. Do not invent rules to check. An unnumbered legacy prose spec is not
        gate-able, and fabricating ids to gate it would report failures against
        rules nobody wrote.
- [ ] **Benign-path coverage** — every BR describing detection, refusal, or a halt
      carries at least one obligation with `benign_path: yes` (a case asserting the
      detector does *not* fire on the legitimate actor). A detector validated only
      against adversarial inputs ships broken and passes its own suite.
      **Severity: Warning (advisory, non-blocking) in epoch 1.**
      - Match the rule text on case-insensitive **stems** — `detect`, `refus`,
        `halt`, `reject`, `block`, `flag` — so `refusal`/`refuses` and
        `blocking`/`blocked` both hit. Do **not** use `\b` word anchors: BSD
        `grep -E` on macOS does not honor them, and the check would silently never
        fire on the dominant developer platform.
- [ ] **Vacuous verification run** — a verification run that exits 0 having done no
      work is a failure, not a pass. **Severity: Blocker.**
      - Work is defined **per kind**, because the kinds are not commensurable: a
        `test-case` obligation reports **executed cases**; a `structural-check`
        obligation reports **files scanned** by the lint invocation (many
        obligations legitimately share one invocation, so per-obligation case counts
        do not exist for that kind). `tools/lint-skills` reports its scanned count on
        stderr and exits `255` when that count is zero.
      - Either count reaching zero fails the gate.
      - This one blocks from epoch 1 while the two above do not, and the asymmetry is
        deliberate: the checks above are coverage *judgments* about obligation shape,
        whereas a zero-work run is evidence the verification **did not run at all**.
        A green suite that executed nothing proves nothing.

**Why two advisory and one blocking**: a coverage gate that blocked on day one
would fail every in-flight REQ written before obligations existed. The advisory
epoch lets the corpus accumulate obligations first; promotion to blocking is a
separate follow-up REQ. The two advisory checks share a posture on purpose — both
are obligation-shape judgments, and a mixed gate where one new shape check blocks
and the other does not is incoherent to anyone reading the output.

**Cross-repo tasks** — only applies if `.adlc/config.yml` in the primary repo declares more than one entry under `repos:`. Skip these checks in single-repo mode.
- [ ] Every task has a `repo:` field in its frontmatter
- [ ] Every `repo:` value matches an id declared in `.adlc/config.yml` under `repos:`
- [ ] No task modifies files outside its declared `repo:` — all paths under "Files to Create/Modify" live in that repo
- [ ] At least one task targets the primary repo (even if just spec/doc updates) OR a follow-up confirms the primary needs no code changes
- [ ] Cross-repo dependencies make sense (e.g., a frontend task depending on a backend task, not the reverse)

#### Validating Implementation
- [ ] All task acceptance criteria are met
- [ ] Tests pass (`npm test` or equivalent)
- [ ] Code follows conventions from `.adlc/context/conventions.md`
- [ ] No new lint warnings or errors
- [ ] All requirement acceptance criteria are satisfied
- [ ] ADLC artifacts are updated (task statuses set to `complete`)

### Step 3: Report Results
1. Display validation results as a checklist with pass/fail for each item
2. Categorize issues by severity:
   - **Blocker**: Must fix before advancing (e.g., missing acceptance criteria, circular deps, a vacuous verification run)
   - **Warning**: Should fix but won't block (e.g., vague wording, missing edge case, unmapped BR/AC obligations, a detector rule with no benign path)
   - **Info**: Suggestions for improvement

   **Advisory obligation findings (REQ-595)**: report unmapped BR/AC ids and
   missing benign paths as **Warning**, and say plainly in the output that they do
   not block advancement in this epoch. Do not silently omit them because they are
   non-blocking — an unreported gap is exactly the omitted-requirement failure the
   check exists to surface, and an advisory finding nobody sees is worth nothing.
   Conversely, do not present them as Blockers: promotion to blocking is a named
   follow-up REQ, and pre-empting it here would fail every REQ written before
   obligations existed.
3. If all checks pass, confirm the artifact is ready to advance
4. If blockers exist, list specific fixes needed

### Step 4: Recommend Next Action
- Spec validated → "Ready for `/architect`"
- Architecture validated → "Ready for implementation"
- Tasks validated → "Ready for implementation"
- Implementation validated → "Ready for `/review`"
