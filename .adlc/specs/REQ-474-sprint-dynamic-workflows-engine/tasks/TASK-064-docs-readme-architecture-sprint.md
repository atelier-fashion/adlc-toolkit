---
id: TASK-064
title: "Docs — README catalog + context/architecture.md + sprint NOT-DOES"
status: complete
parent: REQ-474
created: 2026-05-29
updated: 2026-05-30
dependencies: [TASK-061]
---

## Description

Document the two-engine model so future maintainers and a future `/validate` understand it. Includes the Step-3.3 proposed addition to the toolkit's own `context/architecture.md`. (Step 3.3)

## Files to Create/Modify

- `README.md` — MODIFY. Skill catalog: note `/sprint` has a workflow engine (`--workflow`) and a legacy fallback; add `workflows/` to the layout.
- `.adlc/context/architecture.md` — MODIFY. Add a "Workflow engine" subsection: the `workflows/` dir, the two-engine `/sprint`, the agents-are-leaves model, and the `pipeline-state.json` + journal duality.
- `sprint/SKILL.md` — MODIFY. Extend "What This Skill Does NOT Do" to clarify the workflow-vs-legacy boundary and the research-preview gating.

## Acceptance Criteria

- [ ] README skill catalog and layout reflect the two engines and the `workflows/` dir.
- [ ] `context/architecture.md` gains the Workflow-engine subsection with rationale (consumer-portable; no project-specific paths).
- [ ] `sprint/SKILL.md` NOT-DOES names the gating (Dynamic Workflows research-preview / plan-gated → legacy fallback).
- [ ] No project-specific (atelier-fashion) paths leak into any doc.

## Technical Notes

- Keep additive; do not rename existing fields/sections (conventions: additive frontmatter, no casual new skill dirs).
- This task closes the documentation loop; it depends only on the dispatcher (TASK-061) being defined.
