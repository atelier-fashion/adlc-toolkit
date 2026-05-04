---
id: REQ-380
title: "Architecture — Drop /proceed Phase 7.5 and Phase 8a"
created: 2026-05-04
updated: 2026-05-04
---

## Approach

Pure-markdown refactor of `proceed/SKILL.md` to remove two phases, plus a small annotation to `canary/SKILL.md`, plus a global REQ-counter policy mirror in adlc-toolkit's operator-facing doc, plus a wrapup lesson. No application code, no template schemas, no `/init` template touch. Symlink-install means the change goes live immediately on merge.

External dep status: REQ-379 (atelier-fashion) shipped earlier today (PRs #773 + #774, both MERGED 2026-05-04). The replacement workflow `snapshot-promotion-on-staging-green.yml` is live on staging, so removing Phase 8a does not leave a gap in promote-PR creation.

## Open Questions Resolved

1. **Q: Delete `pipeline.snapshot_promotion` doc from `proceed/SKILL.md` entirely, or annotate as no-op?** → **Delete.** BR-2 mandates removal of behavior-toggle prose. The config-key schema (in `templates/config-template.yml` and `presets/*.yml`) stays per Out-of-Scope #5; that's a follow-up cleanup.
2. **Q: Blast radius beyond `proceed/SKILL.md`?** → grep on 2026-05-04 found:
   - `proceed/SKILL.md` — heavy edits (the target).
   - `canary/SKILL.md:63` — references `/proceed` Phase 7.5 as caller. **In scope** per BR-7.
   - `canary/SKILL.md:208` — Step 7 ("Update Pipeline State if in /proceed context") is general — not Phase-7.5-specific. Leave as-is; manual `/canary` invocations during a parallel `/proceed` for some other REQ may still legitimately update phase history.
   - `bugfix/SKILL.md:128` — `Steps (mirrors /proceed Phase 7.5)` is a stale conceptual cross-reference. **Out of scope** per AC #8 (diff is bounded). Filed as follow-up.
   - `.adlc/context/architecture.md:75` — toolkit's own pipeline-shape diagram shows `/canary` as a /proceed step. **In scope** as self-coherence — this doc describes /proceed's behavior; the diagram becomes wrong otherwise. 1-line edit.
   - `README.md` — `/canary` listed as a standalone skill, no /proceed coupling. No edit.
   - `templates/config-template.yml`, `presets/*.yml` — `services:` block + (likely) `pipeline.snapshot_promotion` schema. **Out of scope** per Out-of-Scope #5.
   - `ETHOS.md:27` — "Every deploy has a canary" — aspirational, not a /proceed coupling. No edit.
3. **Q: Lesson co-authoring with REQ-379?** → **Separate lessons, cross-reference.** REQ-379's lesson focuses on the workflow side (atelier-fashion repo). This REQ's lesson focuses on the skill side (adlc-toolkit repo).

## Operator-Facing Doc Decision (BR-8)

The global REQ-counter policy goes into `.adlc/context/project-overview.md` rather than a new `CLAUDE.md`. Rationale:
- adlc-toolkit's `.adlc/context/project-overview.md` already exists and is the canonical operator-facing doc for this repo (mirrors atelier-fashion's `CLAUDE.md` role).
- A new `CLAUDE.md` would duplicate context-loading semantics with project-overview.md; consumer-project context loading already prefers `.adlc/context/` files.
- atelier-fashion uses `CLAUDE.md` because it's a consumer project, not a toolkit. Asymmetric naming reflects asymmetric roles.

## Task Breakdown

5 tasks, mostly independent. Topology:

```
TASK-001 (proceed SKILL edits)         ←──┐
TASK-002 (canary annotation)          ←───┤
TASK-003 (architecture.md self-coherence) ←┤  All independent, parallel
TASK-004 (project-overview.md REQ-counter)←┘
TASK-005 (wrapup lesson)               ← runs in /wrapup (Phase 8), not Phase 4
```

TASK-005 is the wrapup lesson — by ADLC convention, lessons land via `/wrapup` after merge. It is listed here for visibility but executes in Phase 8, not Phase 4.

Phase 4 implementation tasks: TASK-001 through TASK-004. Tasks 002, 003, 004 are tiny (1–3 line edits) and could be batched into a single commit, but per convention each task gets its own commit for traceability.

## ADRs

**ADR-380-A: Delete (don't deprecate-in-place) Phase 7.5 and Phase 8a sections.** A "deprecated but still present" phase is more confusing than a clean removal. Old `pipeline-state.json` files with `currentPhase: "7.5"` or `"8a"` are a theoretical compat concern but the assumption-grep on 2026-05-04 found no such files in the wild. Operator note: if any future state file is found mid-pipeline at those phases, the operator manually edits `currentPhase` to `8` and reruns. This edge case is documented in the wrapup lesson, not in the skill itself.

**ADR-380-B: Keep `snapshotBranch` / `snapshotPR` fields nullable in the schema.** BR-5: keep them in the schema example (marked `// deprecated since REQ-380, retained for read-back compatibility`) so older state files load without error. The skill stops writing them. Cleaner alternative (remove the fields entirely) was rejected because some atelier-fashion state files written between REQ-362 and REQ-380 may still be on disk in `.worktrees/`.

**ADR-380-C: Operator-facing doc location for global REQ-counter policy.** See "Operator-Facing Doc Decision" above — `.adlc/context/project-overview.md`, not new `CLAUDE.md`.

## Halt-point recount

Before: 5 legitimate halts. After: 3.

| # | Halt | Status |
|---|------|--------|
| 1 | Validation fails 3× | **kept** |
| 2 | Reflector user-facing questions | **kept** |
| ~~3~~ | ~~Canary fails~~ | **removed with Phase 7.5** |
| ~~4~~ | ~~Merge conflicts~~ → renumber to **3** | **kept** |
| ~~5~~ | ~~Phase 8a 30-min poll timeout~~ | **removed with Phase 8a** |

The autonomous-execution contract preamble must explicitly enumerate (1) validation, (2) reflector, (3) merge conflicts. BR-3 governs.

## Out of scope (deferred follow-ups)

- `bugfix/SKILL.md:128` stale cross-reference to `/proceed` Phase 7.5
- `templates/config-template.yml` removal of `pipeline.snapshot_promotion` schema
- JSON schema file (if separate from SKILL.md prose) for `pipeline-state.json`
