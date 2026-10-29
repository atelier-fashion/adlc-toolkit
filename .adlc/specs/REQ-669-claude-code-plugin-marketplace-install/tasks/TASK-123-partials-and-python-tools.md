---
id: TASK-123
title: "Partials resolve toolkit-owned files through ToolkitRoot; allocation no longer needs install.sh"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-122]
---

## Description

Apply architecture ADR-2 to the five partials that read toolkit-owned files from a literal `~/.claude/skills` path today. The Python half of ADR-2 is TASK-132. Close the one machine-state gap the mapper found: the lock `mkdir` needs `~/.claude` to exist (BR-6). Every vendored-surface partial changes body, so consumers' copies will report `stale`, which is expected (LESSON-441). TASK-130's CHANGELOG entry names the re-sync.

## Files to Create/Modify

- `partials/lane-check.sh` — engine path becomes `"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/lane_check.py"`. The error text no longer says only "run install.sh"; it names both routes.
- `partials/forge.sh` — the `_adlc_forge_py` third tier reads through ToolkitRoot.
- `partials/delegate-tools-path.sh` — the global tier reads through ToolkitRoot. The silent relative default stays the last resort.
- `partials/ethos-include.sh` — the toolkit ETHOS fallback reads through ToolkitRoot.
- `partials/intake.sh` — the template candidate reads through ToolkitRoot. The rc 2 failure is unchanged.
- `partials/id-recheck.sh` — its fallback source operand moves to the new spelling. The `BASH_SOURCE` / zsh `%x` self-location is unchanged.
- `partials/emit-step-telemetry.sh` — its fallback source operand moves to the new spelling.
- `partials/id-alloc.sh` — `mkdir -p "$HOME/.claude"` before lock acquisition. Header comment updated.
- `partials/attribution.sh` — header comment quotes the new spelling.
- `partials/conflict-bound.sh` — header comment quotes the new spelling.
- `partials/lesson-check.sh` — header comment quotes the new spelling.
- `partials/trial-merge.sh` — header comment quotes the new spelling.
- `partials/README.md` — spelling and fallback prose updated. The retired `sh … || sh ~/.claude/skills/…` macro example is removed.
- `partials/delegate-gate.md` — spelling and fallback prose updated.
- `partials/lane-check.md` — spelling and engine-path prose updated.
- `partials/forge.md` — spelling updated.
- `partials/emit-step-telemetry.md` — spelling updated.
- `partials/trial-merge.md` — spelling updated.
- `partials/lesson-check.md` — spelling updated.
- `tools/delegate/tests/test_delegate_tools_path.py` — fallback cases follow the new tier.
- `partials/tests/id-alloc.test.sh` — new case: allocation in a sandbox `HOME` with no `~/.claude` directory at all succeeds and creates the counter.
- `partials/tests/lane-check.test.sh` — the `engine_not_found` case is re-pointed. A new case covers the engine found through `ADLC_TOOLKIT_ROOT` with no `~/.claude/skills`.
- `partials/tests/plugin-route.test.sh` — new harness. In a sandbox `HOME` with no `~/.claude/skills` and no `~/.claude/agents`, and `ADLC_TOOLKIT_ROOT` pointing at a copy of the tree, it sources and runs every partial the skills use. It asserts no read under `$HOME/.claude/skills`: that path is created as a mode-000 directory, so any read fails loudly.
- `partials/tests/run.sh` — register `plugin-route.test.sh`.

## Acceptance Criteria

- [x] `plugin-route.test.sh` passes under bash, zsh, sh and dash. It exercises a sourced partial and an exec'd tool for each of lane-check, forge, delegate-tools-path, ethos-include, intake, id-alloc and id-recheck, and its executed-case count is non-zero.
- [x] On a symlink-only sandbox, every existing harness in `partials/tests/run.sh` passes unchanged in its assertions (BR-3).
- [x] A search of the changed partials finds no `~/.claude/skills` or `$HOME/.claude/skills` read outside the ADR-2 default-expansion spelling and comments.
- [x] `python3 -m pytest tools/delegate/tests -q` and `sh partials/tests/run.sh` pass.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `partials/tests/plugin-route.test.sh::case_no_skills_symlink_reads` | no |
| BR-3 | test-case | `partials/tests/run.sh` on a symlink-only sandbox: all existing harnesses | yes |
| BR-5 | test-case | `partials/tests/plugin-route.test.sh::case_vendored_copy_still_first` | yes |
| BR-6 | test-case | `partials/tests/id-alloc.test.sh::case_no_dot_claude_dir` | yes |
| BR-17 | test-case | `partials/tests/run.sh` under bash, zsh, sh and dash: `plugin-route.test.sh` | no |
| AC-3 | test-case | `partials/tests/run.sh` on a symlink-only sandbox | yes |
| AC-5 | test-case | `partials/tests/run.sh` under bash, zsh, sh and dash: `plugin-route.test.sh`, `id-alloc.test.sh`, `lane-check.test.sh` | no |

## Technical Notes

- `lane-check.sh` must keep reading the *installed* engine, never `<worktree>/tools/adlc/lane_check.py` (LESSON-718). ToolkitRoot is installed by definition. Keep the comment that says why.
- The ADR-2 default `${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}` is the exception TASK-129's lint allows. Write it byte-identical at every site, so the exception is a literal, not a pattern.
- The mode-000 guard needs a cleanup trap that restores the mode before `rm -rf`, and the sandbox path must be validated as a `mktemp` result before deletion (LESSON-619).
