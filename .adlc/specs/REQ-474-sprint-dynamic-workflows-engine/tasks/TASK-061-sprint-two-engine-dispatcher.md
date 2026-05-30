---
id: TASK-061
title: "/sprint two-engine dispatcher"
status: complete
parent: REQ-474
created: 2026-05-29
updated: 2026-05-29
dependencies: [TASK-057]
---

## Description

Turn `/sprint` into the two-engine dispatcher: detect Dynamic Workflows availability, read the `--workflow` flag, and route to the workflow engine (invoke the `Workflow` tool with the resolved `adlc-sprint` script path) or the unchanged legacy background-`pipeline-runner` engine. (ADR-1, ADR-2)

## Files to Create/Modify

- `sprint/SKILL.md` — MODIFY. Add the engine-selection step at the top of Instructions; the workflow branch resolves the script path (two-level fallback) and invokes `Workflow({scriptPath, args:{reqs, integrationBranch, answers:{}}})`; the legacy branch (existing Step 3 dispatch) is left intact. Update `argument-hint` to mention `--workflow`.

## Acceptance Criteria

- [ ] The skill selects `workflow` only when Dynamic Workflows is available AND (`--workflow` passed OR graduated-to-default); otherwise `legacy`, with no behavior change.
- [ ] The workflow branch resolves the script path via `.adlc/workflows/adlc-sprint.workflow.js` → `~/.claude/skills/workflows/adlc-sprint.workflow.js` and invokes the `Workflow` tool with the documented `args`.
- [ ] The legacy branch's existing eligibility/preflight/dispatch/monitor/merge steps are byte-for-byte preserved (AC-2 oracle: no diff to legacy prose).
- [ ] `sprint/SKILL.md` passes `tools/lint-skills` (sentinels, balance, canonical, posix-fence, cross-fence-fn).

## Technical Notes

- The dispatcher prose is the *only* place the `Workflow` tool is invoked — the SKILL instructs the agent to call it; the script itself is the engine (ADR-3).
- Do not add telemetry partials to `sprint/SKILL.md` (avoids the canonical-literal lint obligations); telemetry lives in the workflow/agents.
- Surfacing blocked REQs + the `resumeFromRunId` relaunch contract is added in TASK-062.
