---
id: TASK-139
title: "lint-skills `adlc-home` check, its fixtures and tests, and the per-line markers across the corpus"
status: complete
parent: REQ-654
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-135, TASK-136, TASK-138]
repo: adlc-toolkit
---

## Description

A per-root lint (ADR-9) that fails on any new home-directory `.claude` literal in the code
of `tools/`, `scripts/`, `install.sh` and `partials/*.sh`, with comment, docstring, test-tree,
root-line and ADR-2-token exemptions and one per-line marker for the Claude Code-owned paths
and the aliases. The corpus is clean under it.

## Files to Create/Modify

- `tools/lint-skills/check.py` — `ADLC_HOME_CHECK`, surfaces, patterns, `adlc_home_findings`, `scan_adlc_home`, registered in `run()`
- `tools/lint-skills/tests/test_adlc_home_lint.py` — new: fires on each spelling, benign cases, marker validation, corpus clean
- `tools/lint-skills/tests/fixtures/adlc-home/` — new fixture tree (a tool with `$HOME/.claude`, marked and unmarked lines)
- `tools/lint-skills/README.md` — the check's entry
- every corpus file with a Claude Code-owned or alias literal — `# adlc-home: <kind>` markers

## Acceptance Criteria

- [ ] The check fires on a fixture that introduces `$HOME/.claude` into a tool
- [ ] It does not fire on comments, docstrings, test trees, the root line, the ADR-2 token or a marked line
- [ ] An unknown marker value is a finding
- [ ] `bash tools/lint-skills/check.sh` is clean on the repo

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-13 | test-case | `tools/lint-skills/tests/test_adlc_home_lint.py::test_fires_on_new_literal_in_tool` | no |
| BR-13 | test-case | `tools/lint-skills/tests/test_adlc_home_lint.py::test_benign_lines_do_not_fire` | yes |
| AC-10 | test-case | `tools/lint-skills/tests/test_adlc_home_lint.py::test_repo_is_clean` | yes |

## Technical Notes

- Reuse `_scan_surfaces`, `is_plugin_root`, `_is_tools_code_file` and the `tests`/`fixtures`
  tree exemption; never `\b` in a pattern a shell tool might copy (Python `re` is fine).
- Docstring lines come from `ast` (module, class, function first statements); a parse
  failure exempts nothing.
