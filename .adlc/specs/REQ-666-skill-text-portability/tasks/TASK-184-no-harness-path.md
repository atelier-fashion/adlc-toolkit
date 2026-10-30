---
id: TASK-184
title: "no-harness-path absorbs toolkit-path; remaining prose literals rewritten"
status: complete
parent: REQ-666
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Rename `toolkit-path` to `no-harness-path` and widen it per ADR-5: every harness
home in the Markdown families, toolkit and foreign-harness paths in code; the
exception list grows by the two default-expansion tokens, the `adlc-home:`
marker, whole-line HTML comments and `tools/adlc/harness_probe.py`. Rewrite the
remaining literal lines in skill and partial prose.

## Files to Create/Modify

- `tools/lint-skills/check.py` — rename and widen
- `tools/lint-skills/tests/test_toolkit_path.py` — follow the rename
- `tools/lint-skills/tests/test_no_harness_path.py` — new: AC-12 fixtures
- `tools/lint-skills/tests/test_builtin_collision.py` — follow the rename if it imports the shared names
- `bugfix/SKILL.md` — counter paths
- `spec/SKILL.md` — counter path
- `wrapup/SKILL.md` — counter and transcript paths
- `partials/forge.md` — config and venv paths
- `partials/README.md` — transcript and home paths
- `partials/lesson-check.md` — home path wording, if flagged

## Acceptance Criteria

- [ ] one finding per fixture line holding `~/.claude/agents`, `$HOME/.claude/adlc`, `~/.codex`, `~/.copilot`, `~/.gemini` or `~/.cursor` in a skill, partial, agent or tool
- [ ] none on the root line, the default-expansion tokens, a comment line, `install.sh`, or the `unguarded-source` literal
- [ ] the finished tree is clean and every surface scanned at least one file

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-13 | test-case | `tools/lint-skills/tests/test_no_harness_path.py::test_repo_clean_every_surface_scanned` | yes |
| AC-12 | test-case | `tools/lint-skills/tests/test_no_harness_path.py::test_each_harness_home_fires_once` | yes |

## Technical Notes

Keep `scan_toolkit_path`'s return shape so `builtin-collision` and its tests are
untouched; add the new name as the primary and keep the old function name as an
alias only if a test imports it.
