---
id: TASK-051
title: "Register the new partial: /init copy coverage + partials/README.md"
status: complete
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

- [ ] The `/init` `cp ~/.claude/skills/partials/*.sh .adlc/partials/` glob provably vendors `emit-step-telemetry.sh` into a consumer's `.adlc/partials/` (verified by reading init/SKILL.md's partials-copy step). The companion `emit-step-telemetry.md` is correctly **not** vendored — it stays beside the `.sh` in the toolkit repo, exactly as `kimi-gate.md` is handled (the glob is deliberately `*.sh`-only; consumer runtime sources only the `.sh`). Matches requirement AC-12. (AC-12)
- [ ] `partials/README.md` lists `emit-step-telemetry.sh` as a sourceable (model-2) partial with a companion `.md`, and references its `kimi-tools-path.sh` self-source.
- [ ] No regression to how `kimi-gate.sh` / `kimi-tools-path.sh` / `ethos-include.sh` are copied.

## Technical Notes

- Read `init/SKILL.md`'s actual partials-copy logic before deciding glob-vs-explicit
  (REQ-426 added partials drift/tests — confirm consistency with that).
- If the copy step is a glob, the AC is satisfied by verification, not edits — say
  so explicitly rather than making a no-op change.
- The companion `.md` must be copied too (the call-site protocol doc travels with
  the partial), matching how `kimi-gate.md` is handled.
