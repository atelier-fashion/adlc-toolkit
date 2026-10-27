---
id: TASK-119
title: "Docs: README, CHANGELOG, architecture and conventions context"
status: draft
parent: REQ-652
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-118]
---

## Description

Catalogue and context updates so the lane is discoverable and the next REQ's `/spec` retrieval sees it.

## Files to Create/Modify

- `README.md` — `/spec` row mentions `--lite`/`--full`; `/proceed` row mentions the lite lane and `--full`; `/sprint` row notes the workflow engine runs lite on full; `/status` row mentions the lane; `lanes.lite` row in the config table.
- `CHANGELOG.md` — `[Unreleased]` Added (the lite lane, lane check, lite-reviewer, lane-vocabulary lint) and Changed (four halts, absent `lane` behaves as before), citing REQ-652. VERSION is not bumped (5.4.0 at release cut).
- `.adlc/context/architecture.md` — the Lanes entry, the pipeline-shape lite branch, the workflow-engine note (architecture.md "Proposed additions").
- `.adlc/context/conventions.md` — Pipeline state: `lane` is additive, absent means full.

## Acceptance Criteria

- [ ] Every new flag, file and check introduced by TASK-111–118 is named in README or CHANGELOG.
- [ ] `sh tools/lint-skills/check.sh --root .` stays clean.

## Technical Notes

- Follow the REQ-594 `--intake` precedent for how a new flag appears in the README skill table.
