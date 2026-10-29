---
id: TASK-129
title: "toolkit-path lint: no literal ~/.claude/skills or ~/.claude/agents read on the plugin-reachable surface"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-125, TASK-126, TASK-132]
---

## Description

Apply architecture ADR-9 (BR-13). After the rewrites in TASK-123 through TASK-126, the plugin-reachable surface has no literal toolkit read path outside a short exception list. This check keeps it that way. It is written so REQ-666's `no-harness-path` can absorb it in one change. The check runs last so it lands green on the real tree, and its first run is the proof the rewrites were complete.

## Files to Create/Modify

- `tools/lint-skills/check.py` — new per-root `check_toolkit_path(root)`, wired into `run()`.
  - Scanned surface: `*/SKILL.md`, `proceed/phase*.md`, `agents/*.md`, `partials/*.sh`, `partials/*.md`, `workflows/*.js`, and non-test `tools/**` source.
  - Flagged spellings: `~/.claude/skills`, `$HOME/.claude/skills`, `${HOME}/.claude/skills`, `${HOME:-}/.claude/skills`, `~/.claude/agents`.
  - Exceptions, as one named list in the code:
    - the canonical root line;
    - the ADR-2 default-expansion spelling;
    - `install.sh` and `tools/adlc/checks.py`;
    - the lint's own rule table;
    - comment lines;
    - `tests/` and `fixtures/` trees.
- `tools/lint-skills/tests/test_toolkit_path.py` — new.
- `tools/lint-skills/tests/fixtures/toolkit-path/` — new fixture trees, including `literal-read-path.sh`, a new partial that reads `~/.claude/skills/partials/x.sh`.
- `tools/lint-skills/README.md` — new item, with the exception list and a note that REQ-666 absorbs this check.

## Acceptance Criteria

- [x] The `literal-read-path.sh` fixture fails with one finding naming its line. Each of the five spellings fails in its own fixture.
- [x] The canonical root line, the default-expansion spelling, a comment line, and a test-tree file each produce zero findings (the benign paths).
- [x] On the real repo the check reports zero findings, and its scanned-file count covers every surface listed above, with each surface non-empty. A surface that scanned zero files is a failure (LESSON-019).
- [x] Run from inside a `.worktrees/` checkout, the check still scans its own root (LESSON-019's skipped-root case).
- [x] `pytest tools/lint-skills/tests/ -q` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-13 | test-case | `tools/lint-skills/tests/test_toolkit_path.py::test_literal_read_in_new_partial_fails` | no |
| BR-13 | test-case | `tools/lint-skills/tests/test_toolkit_path.py::test_exceptions_do_not_fire` | yes |
| BR-13 | test-case | `tools/lint-skills/tests/test_toolkit_path.py::test_repo_root_clean_and_every_surface_scanned` | yes |
| BR-2 | test-case | `tools/lint-skills/tests/test_toolkit_path.py::test_repo_root_clean_and_every_surface_scanned` | no |
| AC-7 | test-case | `tools/lint-skills/tests/test_toolkit_path.py::test_literal_read_in_new_partial_fails` | no |

## Technical Notes

- Match the exception lines as byte-exact literals, not patterns, so a near-miss variant of the root line is a finding.
- Use plain substring matching for the five spellings. Do not use `\b` (LESSON-013).
- Keep the exception list in one constant that the README quotes by name, so REQ-666 can lift it whole.
