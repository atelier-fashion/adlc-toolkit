---
id: TASK-052
title: "Document the SKILL.md fenced-block execution model in context docs"
status: complete
parent: REQ-436
created: 2026-05-16
updated: 2026-05-16
dependencies: []
---

## Description

Make the execution-model finding explicit and discoverable in the toolkit's own
context docs so future skill authors don't reintroduce a cross-block shell
function. Implements BR-12, AC-9.

## Files to Create/Modify

- `.adlc/context/conventions.md` — in "Bash in skills", add a clear statement:
  SKILL.md fenced shell blocks do not share shell state (functions,
  non-exported variables) across steps; they may each be an independent shell
  invocation. Shared shell functions MUST be sourced from a `partials/*.sh`
  at each call site (in the same fenced block as the invocation) and MUST NOT
  be defined in one fenced block and invoked from another. Point to
  `partials/kimi-gate.sh` / `partials/emit-step-telemetry.sh` as the canonical
  pattern, and note the `lint-skills` `cross-fence-fn` check enforces it.
- `.adlc/context/architecture.md` — in "Partials" (and/or "Skill anatomy"), add a
  one-paragraph cross-reference to the same invariant so the architectural
  rationale lives alongside the partials description.

## Acceptance Criteria

- [ ] `.adlc/context/conventions.md` contains a greppable statement (e.g. a sentence with "do not share shell state across" near "partial") in the "Bash in skills" section.
- [ ] `.adlc/context/architecture.md` "Partials"/"Skill anatomy" cross-references the invariant and the `cross-fence-fn` enforcement.
- [ ] Wording is consistent with the new LESSON (Phase 8) and cites the enforcement mechanism (sourced partial + `cross-fence-fn` lint check) rather than relying on prose alone (LESSON-012).

## Technical Notes

- This is the prose-companion to the structural enforcement (LESSON-012:
  prose alone is honor-system — it must name the enforcing check).
- Independent of the code tasks — no dependency; can land in parallel.
- Keep it tight: a short subsection/paragraph, not a treatise. Match the
  existing terse style of conventions.md / architecture.md.
