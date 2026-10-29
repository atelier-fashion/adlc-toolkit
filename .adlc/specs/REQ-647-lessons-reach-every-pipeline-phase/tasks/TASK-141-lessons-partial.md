---
id: TASK-141
title: "partials/lessons.sh — the sourced adlc_lessons wrapper, its contract doc, and a four-shell harness"
status: complete
parent: REQ-647
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-140]
repo: adlc-toolkit
---

## Description

The fence-facing half (BR-12). `adlc_lessons <subcommand> [args…]` runs the
installed toolkit's `tools/adlc/lessons.py` through `_adlc_forge_python`,
passing stdout and the return code through, and turns a missing engine, a
missing resolver or a relative root into rc 2 with one
`lessons: unavailable — <reason>` line.

## Files to Create/Modify

- `partials/lessons.sh` — create; sourceable partial defining `adlc_lessons`
- `partials/lessons.md` — create; contract: subcommands, return codes, the never-halts rule
- `partials/tests/lessons.test.sh` — create; harness run under bash, zsh, /bin/sh, dash
- `partials/tests/run.sh` — modify; add the harness to the `run_all` list
- `partials/README.md` — modify; list the partial

## Acceptance Criteria

- [ ] `adlc_lessons select …` through the wrapper prints the same stdout and rc as the engine run directly
- [ ] An absent engine, an unset resolver and a relative `ADLC_TOOLKIT_ROOT` each return rc 2 with a `lessons: unavailable —` line
- [ ] The harness reports executed cases > 0 under every installed shell, and `sh partials/tests/run.sh` lists it
- [ ] `tools/lint-skills` passes (no `case` inside `$( )`, guarded sourcing)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-12 | test-case | `partials/tests/lessons.test.sh` (bash, zsh, /bin/sh, dash via `partials/tests/run.sh`) | yes |
| AC-13 | test-case | `partials/tests/run.sh` lists `lessons.test.sh`; executed cases > 0 | no |

## Technical Notes

- Mirror `partials/lane-check.sh` for interpreter resolution and the `-E` flag; drop the inside-worktree refusal (retrieval is not a gate) but keep the absolute-root check.
- Prefixed globals (`adlc_ls_*`), no `local`, no arrays, no `case` in `$( )` (LESSON-582).
- The harness points `HOME` at a sandbox whose `.claude/skills` is this checkout, as `lane-check.test.sh` does.
