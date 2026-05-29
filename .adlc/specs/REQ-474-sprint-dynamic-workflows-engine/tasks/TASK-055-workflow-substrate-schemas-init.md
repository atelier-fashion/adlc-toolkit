---
id: TASK-055
title: "Workflow substrate — schemas module + workflows/ dir + /init distribution"
status: complete
parent: REQ-474
created: 2026-05-29
updated: 2026-05-29
dependencies: []
---

## Description

Establish the substrate the workflow engine builds on: the JSON-Schema literals every `agent({schema})` call validates against, the new `workflows/` directory convention, and `/init` distribution into consumer projects. Foundational — no engine logic yet. (ADR-2, ADR-7)

## Files to Create/Modify

- `workflows/schemas.js` — CREATE. Exports the 7 schemas: `REPOS`, `VERDICT`, `TASKS`, `FINDINGS`, `CANDIDATES`, `PRS`, `TERMINAL`.
- `init/SKILL.md` — MODIFY. Copy `workflows/` → consumer `.adlc/workflows/` alongside `templates/`/`partials/`.
- `README.md` — MODIFY (minimal). Note the new `workflows/` top-level dir in the layout.

## Acceptance Criteria

- [ ] All 7 schemas are valid JSON Schema with `additionalProperties: false` on every object.
- [ ] `CANDIDATES.candidates[].dimension` enum has exactly the **5** reviewer dimensions (no `reflector`); `FINDINGS.dimension` enum has **6** (includes `reflector`).
- [ ] `TERMINAL.state` enum = `[merged, pr-ready, blocked, failed]`; `CANDIDATES` carries `invoked`/`exit`/`gateReason`/`changedFiles` per the spec System Model.
- [ ] `/init` copies `workflows/` into `.adlc/workflows/`; a fresh `/init` in a scratch repo produces `.adlc/workflows/schemas.js`.
- [ ] The two-level path-resolution convention (`.adlc/workflows/…` → `~/.claude/skills/workflows/…`) is documented in `workflows/` (a short README or header comment).

## Technical Notes

- Fields come verbatim from `requirement.md` System Model. Keep schemas in their own module so the workflow script and tests both import them.
- `/init` change mirrors the existing `templates/`/`partials/` copy loop — do not invent a new mechanism (architecture.md "Templates"/"Partials").
- No symlink/install change is needed (integration-explorer: `~/.claude/skills/workflows/` resolves via the existing skills symlink).
