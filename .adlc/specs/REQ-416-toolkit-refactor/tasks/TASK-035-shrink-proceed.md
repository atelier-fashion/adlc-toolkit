---
id: TASK-035
title: "Shrink proceed/SKILL.md by extracting Phases 1–3 and 6–8 to companion files"
status: complete
parent: REQ-416
created: 2026-05-15
updated: 2026-05-15
dependencies: [TASK-033]
---

## Description

Resolve REQ-416 BR-4 (ADR-3, with the amended ≤450-line target documented in
the architecture). Extract the four "thin" phase sections of `proceed/SKILL.md`
into companion files, leaving the load-bearing core (Repo Config, Pipeline
State Tracking, Step 0, Phase 5 with the Kimi gate, error handling) inline.

Depends on TASK-033 only loosely — the partials/ directory exists, so the
companion-files pattern can mirror it stylistically. No code dependency.

## Files to Create/Modify

- `proceed/phases-1-3-validation.md` — NEW. Extracts current SKILL.md lines
  ~243–284: Phase 1 (Validate the Requirement Spec), Phase 2 (Architect &
  Break Into Tasks), Phase 3 (Validate Architecture & Tasks). 42 lines.
- `proceed/phase-4-implementation.md` — NEW. Extracts current lines ~289–321:
  Phase 4 (Implement). 33 lines.
- `proceed/phases-6-8-ship.md` — NEW. Extracts current lines ~427–536:
  Phase 6 (Create PR), Phase 7 (PR Cleanup & CI), Phase 8 (Wrapup). 38 lines.
- `proceed/SKILL.md` — replace each extracted section with a 4–6 line inline
  summary plus a `<!-- companion: <relative-path> -->` marker. Preserve a
  one-line statement of what the phase does and the gate-protocol contract
  the phase honors, so a maintainer reading SKILL.md top-to-bottom never
  needs to context-switch to know what each phase guarantees. Detailed
  steps live in the companion.
- `.adlc/context/architecture.md` — under "ADLC pipeline shape", add a note
  that `/proceed` phases live in companion files referenced from SKILL.md.

## Acceptance Criteria

- [ ] Three companion files exist with the specified content, each with
      its own frontmatter (`parent: proceed`, `phase: <n>` or `phases: <n-m>`).
- [ ] `wc -l proceed/SKILL.md` reports ≤ 450 (the ADR-3 amended target —
      down from current 556, original BR-4 target was ≤300 but architecture
      explicitly negotiates this to keep Phase 5 inline).
- [ ] No load-bearing invariant is lost. Verified by:
      ```bash
      cat proceed/SKILL.md proceed/phases-1-3-validation.md \
          proceed/phase-4-implementation.md proceed/phases-6-8-ship.md \
        | wc -l
      ```
      MUST equal the pre-refactor SKILL.md line count plus a small constant
      (≤30 lines) for inline summaries and companion frontmatter. A diff of
      the union vs the pre-refactor SKILL.md (with whitespace normalized)
      shows only structural reorganization, no semantic content removal.
- [ ] Each companion file's frontmatter includes a back-reference
      `parent: proceed` so retrieval tooling can find them.
- [ ] In-flight `/proceed` pipelines remain valid (BR-9): re-running a
      half-completed pipeline picks up the new file structure on the next
      phase invocation. Verified by manually creating a pipeline-state.json
      pinned at "Phase 4 mid-flight" and confirming Phase 5 invocation reads
      the (still inline) Phase 5 section without referencing missing
      companions.
- [ ] `.adlc/context/architecture.md` reflects the new layout.
- [ ] All REQ-413 pytest tests still pass (BR-8).

## Technical Notes

- The `<!-- companion: ... -->` marker is documentation-only — Claude Code
  does not auto-load referenced files. A `/proceed` invocation reads
  SKILL.md, sees the inline summary, and the maintainer/agent opens the
  companion only when adding/changing detail.
- The inline summary for each extracted phase MUST include:
  - One sentence on what the phase does
  - The gate-protocol contract (what state advance/halt this phase produces)
  - Pointer to the companion for full step-by-step
- Phase 5 (Verify) is intentionally NOT extracted. The Kimi pre-pass gate
  (lines ~336–393) is load-bearing for the verify protocol; splitting it
  fragments the gate-handoff logic. Architecture ADR-3 documents this trade.
- BR-4 amendment: the requirement was amended at validate-time (2026-05-15) from
  ≤300 to ≤450 with the keep-Phase-5-inline rationale. /wrapup should still
  capture the negotiation as a LESSON for future refactor REQs.
- After this task lands, the companion files become the authoritative source
  for their phase content; SKILL.md is the orchestration spine. Future
  edits to a phase's content go in the companion, with a corresponding
  one-line summary update in SKILL.md if the phase's contract changes.
