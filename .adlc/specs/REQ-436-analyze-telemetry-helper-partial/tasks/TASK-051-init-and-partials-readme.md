---
id: TASK-051
title: "Register the new partial: /init copy coverage + partials/README.md"
status: draft
parent: REQ-436
created: 2026-05-16
updated: 2026-05-16
dependencies: [TASK-047]
---

## Description

Ensure `partials/emit-step-telemetry.sh` and `partials/emit-step-telemetry.md`
are copied into consumer projects' `.adlc/partials/` by `/init`, and register the
new sourceable partial in `partials/README.md`. Implements BR-11.

## Files to Create/Modify

- `init/SKILL.md` — locate the partials-copy step. If it already copies
  `partials/*` (glob) into `.adlc/partials/`, no code change — record the
  verification (the glob provably covers the two new files). If it enumerates
  partials explicitly, add `emit-step-telemetry.sh` and `emit-step-telemetry.md`.
- `partials/README.md` — add `emit-step-telemetry.sh` to the "model 2 / sourceable
  partial (defines a function)" section alongside `kimi-gate.sh`; note it has a
  companion `.md` because its call-site protocol (same-fenced-block source) is
  non-obvious, and that it self-sources `kimi-tools-path.sh`.

## Acceptance Criteria

- [ ] The `/init` partials handling provably copies both new files into a consumer's `.adlc/partials/` — demonstrated by reading the copy step (glob covers `partials/*` incl. `.sh` and `.md`) or by an explicit dry-run listing (AC-12).
- [ ] `partials/README.md` lists `emit-step-telemetry.sh` as a sourceable (model-2) partial with a companion `.md`, and references its `kimi-tools-path.sh` self-source.
- [ ] No regression to how `kimi-gate.sh` / `kimi-tools-path.sh` / `ethos-include.sh` are copied.

## Technical Notes

- Read `init/SKILL.md`'s actual partials-copy logic before deciding glob-vs-explicit
  (REQ-426 added partials drift/tests — confirm consistency with that).
- If the copy step is a glob, the AC is satisfied by verification, not edits — say
  so explicitly rather than making a no-op change.
- The companion `.md` must be copied too (the call-site protocol doc travels with
  the partial), matching how `kimi-gate.md` is handled.
