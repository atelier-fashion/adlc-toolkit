---
id: TASK-043
title: "Add kimi-tools-path.sh resolver partial"
status: complete
parent: REQ-433
created: 2026-05-16
updated: 2026-05-16
dependencies: []
repo: adlc-toolkit
---

## Description

Create the sourced POSIX partial that exports `KIMI_TOOLS` — the directory
containing the three Kimi telemetry executables — resolving project-local first,
then the global `~/.claude/skills` symlink, then a non-fatal degrade. This is the
foundational artifact every other task in REQ-433 depends on; it mirrors the
`kimi-gate.sh` sourced-partial pattern (REQ-416 ADR-2).

## Files to Create/Modify

- `partials/kimi-tools-path.sh` — **new**. ~15-line POSIX `sh` snippet, mode `+x`
  to match sibling partials, with a header comment documenting the contract.

## Acceptance Criteria

- [ ] `partials/kimi-tools-path.sh` exists and is `chmod +x`.
- [ ] Sourcing it sets and `export`s `KIMI_TOOLS` on **every** path (BR-1).
- [ ] Resolution per ADR-2: `[ -x tools/kimi/emit-telemetry.sh ]` → `tools/kimi`; elif `[ -x "$HOME/.claude/skills/tools/kimi/emit-telemetry.sh" ]` → `$HOME/.claude/skills/tools/kimi`; else → `tools/kimi`. `$HOME` (not `~`) in assignments.
- [ ] No `set -eu`; no bashisms (`[[`, arrays, `local` w/o POSIX care); no GNU-only utilities; no python/node (BR-3, LESSON-012/013).
- [ ] Sourcing the partial from a caller running under `set -eu` does NOT abort the caller, and never writes to stdout/stderr (BR-4).
- [ ] Header comment states: purpose, the exported var, resolution order, and "sourced not executed" (mirror `kimi-gate.sh` header style).

## Technical Notes

- Model the file on `partials/kimi-gate.sh`: a `# comment` header block, a
  default `export KIMI_TOOLS=...` defensive assignment before any branching
  (so even a caller that sources but mis-branches still has it set), then the
  `if/elif/else` resolution.
- Do NOT use a function (the gate uses `adlc_kimi_gate_check()` because callers
  invoke it explicitly; the resolver should resolve at source-time so call sites
  need only `"$KIMI_TOOLS"` with no extra call). Sourcing executes top-level
  statements — that is the intended trigger.
- The `[ -x ... ]` probe MUST use `emit-telemetry.sh` as the discriminator file
  (stable across all 3 scripts' shared dir) per ADR-2.
- POSIX portability: `[ -x path ]` is POSIX; avoid `[[`. Quote `"$HOME"`.
- No symlink mutation — read-only `[ -x ]` test; LESSON-014 TOCTOU not applicable.
