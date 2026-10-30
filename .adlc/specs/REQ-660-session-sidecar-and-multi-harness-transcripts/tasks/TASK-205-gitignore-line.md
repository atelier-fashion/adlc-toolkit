---
id: TASK-205
title: "The gitignore line and its lint check"
status: complete
parent: REQ-660
created: 2026-10-30
updated: 2026-10-30
dependencies: []
repo: adlc-toolkit
---

## Description

Add `.adlc/.session/` here and to what `/init` writes, and a lint check holding the `/init` line (BR-7, BR-15).

## Files to Create/Modify

- `.gitignore` — add `.adlc/.session/`
- `init/SKILL.md` — add the line in Step 5
- `tools/lint-skills/check.py` — new `session-gitignore` check
- `tools/lint-skills/tests/test_session_gitignore.py` — missing line fails naming the file; real tree passes
- `tools/lint-skills/README.md` — document the check, additively

## Acceptance Criteria

- [ ] Deleting the line from `init/SKILL.md` Step 5 fails the check naming the file
- [ ] The real tree passes
- [ ] `git status` with a sidecar present shows nothing

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-7 | test-case | `tools/lint-skills/tests/test_session_gitignore.py::test_real_tree_passes` | yes |
| BR-15 | test-case | `tools/lint-skills/tests/test_session_gitignore.py::test_missing_line_names_file` | yes |
| AC-12 | test-case | `tools/lint-skills/tests/test_session_gitignore.py::test_missing_line_names_file` | yes |

## Technical Notes

Follow `ethos-line` (`check_ethos_line`, `tests/test_ethos_line.py`). Read the `### Step 5` section only, so a mention elsewhere cannot satisfy it. Keep `### Step 6:` and the sync marker block intact; tests anchor on both.

## Dependencies

None.
