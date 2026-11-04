---
id: TASK-242
title: "Docs, CHANGELOG and the full gate run"
status: draft
parent: REQ-691
created: 2026-11-04
updated: 2026-11-04
dependencies: [TASK-241]
---

## Description

Record REQ-691 where people look for it, and run every gate the release checklist names on the final tree.

## Files to Create/Modify

- `CHANGELOG.md` — an `## [Unreleased]` entry: the setting, `off` when absent, the template default, the check and its CI use, and that existing bugs read as legacy.
- `README.md` — a row for `bugfix.regression_test` in the config capability table, and a clause on the `/bugfix` catalog row.
- `.adlc/context/architecture.md` — the bug-template row in "Template anatomy" names the two optional fields, and a **Regression tests (REQ-691)** bullet goes under "Key cross-cutting dependencies" (the text proposed in this REQ's architecture.md).

## Acceptance Criteria

- [ ] On the final tree, `tools/lint-skills/check.sh`, `python3 -m pytest tools -q`, `sh partials/tests/run.sh`, `node --test 'space/tests/*.test.js'` and `node --test 'workflows/tests/*.test.js'` all pass. Each reports a non-zero count of files scanned or cases run.
- [ ] The README's skill-body-cap row still names exactly the skills over the cap.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| AC-14 | structural-check | `tools/lint-skills/check.sh` (all checks) and `sh partials/tests/run.sh` on the final tree | no |

## Technical Notes

- The "scanned N" / "collected" counts are the vacuous-run evidence: lint exits 255 on zero files, and pytest exits 5 on zero collected.
- No consumer project's CI is touched. The embolden-website follow-up REQ wires the check into `gates`.
