---
id: TASK-122
title: "The canonical ToolkitRoot line, the new guarded-source operand, and the lint that pins both"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-121]
---

## Description

Define the one root line from architecture ADR-1, and the guarded-source spelling whose fallback operand is `"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"`. Prove the line's four arms under every target shell. Move `tools/lint-skills` and its fixtures to the new spelling in one change, because the old spelling is pinned in three places that must move together (`CANONICAL_SOURCE_RE`, `DOT_SOURCE_PARTIAL_RE`, `CANONICAL_LITERALS`). This task changes the contract. TASK-123, TASK-124 and TASK-126 apply it to the corpus. **The change is transitional so the repo never goes lint-red between tasks.** After this task `unguarded-source` accepts both the new operand and the REQ-610 one. TASK-124 retires the old operand once nothing uses it.

## Files to Create/Modify

- `.adlc/context/conventions.md` — "Bash in skills": the root line and the new guarded spelling, byte-exact, replacing the REQ-610 spelling at every place it is quoted. Add a sentence on arm order and why `${CLAUDE_PLUGIN_ROOT:-…}` is never written.
- `tools/lint-skills/check.py`:
  - `CANONICAL_SOURCE_RE`, `CANONICAL_LITERALS`, `DOT_SOURCE_PARTIAL_RE` and the messages accept the new operand **in addition to** the REQ-610 `~/.claude/skills/partials/` operand. A named constant, `TRANSITIONAL_OLD_OPERAND`, marks the old form for removal in TASK-124.
  - New check `toolkit-root-line`: in any fence that references `$ADLC_TOOLKIT_ROOT`, the canonical root line appears byte-exact before the first reference. A differing line, or a use without the line, is a finding.
- `tools/lint-skills/tests/test_check.py` — update the `unguarded-source` and `canonical-helper` cases and the partial-walk cases. Add `toolkit-root-line` cases.
- `tools/lint-skills/tests/fixtures/guarded-source-ok.md` — add the new-spelling form beside the existing one; both must pass.
- `tools/lint-skills/tests/fixtures/unguarded-source-fence.md` — add must-fire variants of the new operand: `||`-chained, unguarded, and a mismatched `<name>`.
- `tools/lint-skills/tests/fixtures/toolkit-root-line-ok.md` — new.
- `tools/lint-skills/tests/fixtures/toolkit-root-line-missing.md` — new.
- `tools/lint-skills/tests/fixtures/toolkit-root-line-variant.md` — new.
- `tools/lint-skills/README.md` — item 9 rewritten for the new spelling. New item for `toolkit-root-line`.
- `partials/tests/toolkit-root.test.sh` — new harness, run as a `.sh` the way `source-guard.test.sh` runs extracted spellings.
- `partials/tests/source-guard.test.sh` — `TOKEN_RE`, `RETIRED`, `CANON_SPELLING` and the fixture trees move to the new spelling. The conventions.md verbatim check now pins the new line.
- `partials/tests/run.sh` — register `toolkit-root.test.sh`.

## Acceptance Criteria

- [x] `toolkit-root.test.sh` extracts the root line from conventions.md, so it tests the documented bytes and not a copy. It runs each case in a sandbox `HOME`:
  - (a) substituted: the harness rewrites `${CLAUDE_PLUGIN_ROOT}` to a cache path, as Claude Code does, and the resolved root is that path even when `~/.claude/skills/partials` and the pointer file also exist;
  - (b) symlink only: the root is `$HOME/.claude/skills`;
  - (c) doubled machine, unsubstituted text: the symlink arm wins over the pointer file;
  - (d) plugin only, unsubstituted text: the pointer file's path wins;
  - (e) neither install: the root is `$HOME/.claude/skills`, and sourcing a partial through it fails loudly, with a non-empty stderr naming the path;
  - (f) a `.adlc/partials/<name>.sh` present: the vendored copy is sourced, not the root copy.
- [x] The harness passes under bash, zsh, sh and dash through `partials/tests/run.sh`. On macOS `/bin/sh` is bash 3.2 in POSIX mode. Dash's skip notice is not acceptable for this AC: install dash or run the harness under it explicitly, and record which. Recorded: dash was already installed at `/bin/dash` (macOS 27.0.1), and `run.sh` ran it as its fourth pass (`=== dash ===`, `toolkit-root.test.sh: ALL CASES PASS (dash)`), not the skip notice.
- [x] `tools/lint-skills/check.sh` on the unchanged repo still reports zero `unguarded-source` findings, because the old operand stays accepted. A scratch copy with one real SKILL.md fence rewritten to the new spelling also reports zero, and the same copy with the root line removed reports one `toolkit-root-line` finding. This proves the checks read real trees and not only their fixtures (LESSON-019).
- [x] A fence with the root line and the new spelling passes. A fence using `$ADLC_TOOLKIT_ROOT` with no root line, or with a one-character variant of it, fails `toolkit-root-line`.
- [x] `pytest tools/lint-skills/tests/ -q` and `sh partials/tests/run.sh` pass.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `partials/tests/toolkit-root.test.sh::case_symlink_only` | yes |
| BR-3 | test-case | `partials/tests/toolkit-root.test.sh::case_doubled_unsubstituted_prefers_symlink` | yes |
| BR-4 | test-case | `partials/tests/toolkit-root.test.sh::case_substituted_wins` | no |
| BR-4 | test-case | `tools/lint-skills/tests/test_check.py::test_toolkit_root_line_variant_fails` | no |
| BR-5 | test-case | `partials/tests/toolkit-root.test.sh::case_vendored_partial_first` | yes |
| BR-17 | test-case | `partials/tests/run.sh` under bash, zsh, sh and dash: `toolkit-root.test.sh` | no |
| AC-5 | test-case | `partials/tests/run.sh` under bash, zsh, sh and dash: `toolkit-root.test.sh`, `source-guard.test.sh` | no |

## Technical Notes

- Use the root line exactly as architecture ADR-1 writes it. If TASK-120 retired arm 3 (hooks do not run), drop the pointer clause here and in conventions.md together, and record that in this task's PR.
- `cross-fence-var` already flags a variable set in one fence and read in another. The root line is per fence by design, so `$ADLC_TOOLKIT_ROOT` set in fence 1 and read in fence 2 must still be a finding.
- `.` of a missing file is fatal under `sh` (LESSON-617). Case (e) runs each source inside its own child shell, so the harness itself survives.
- Do not use `\b` in `grep -E` (LESSON-013). Use `command grep` where the harness branches on status (LESSON-717).
