---
id: TASK-132
title: "Python tools: one identity-checked toolkit_root helper replaces the ~/.claude/skills fallback arms"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-122]
---

## Description

This is the Python half of architecture ADR-2. Python tools already resolve their root from `os.path.realpath(__file__)`, which is correct inside the plugin cache. Four modules still keep a literal `~/.claude/skills` fallback arm: `forge_config.py`, `lane_check.py`, `renumber.py` and `checks.py`'s `_partial_path`.

A new `tools/adlc/toolkit_root.py` holds the one rule. It returns the realpath-derived root, identity-checked as `tools/delegate/_common.py` does: a candidate is accepted only if `realpath(<root>/tools/adlc/toolkit_root.py)` is the running file (ASSUME-001, LESSON-620). The four arms switch to it.

One silent failure is fixed. When the recheck partial cannot be found, `renumber.remote_collision` returns "no collision". It now raises.

## Files to Create/Modify

- `tools/adlc/toolkit_root.py` — new. `toolkit_root()` returns the identity-checked root and raises with the two candidate paths when the check fails. `toolkit_file(rel)` joins, rejects `..`, and requires the file to exist. Stdlib only.
- `tools/adlc/forge_config.py` — the `_machine_config.py` fallback arm uses `toolkit_file`.
- `tools/adlc/lane_check.py` — the same loader fallback arm uses `toolkit_file`.
- `tools/adlc/renumber.py` — `_find_partial`'s third candidate uses `toolkit_file`. `remote_collision` raises, instead of returning False, when no recheck partial is found.
- `tools/adlc/checks.py` — `_partial_path`'s fallback arm uses `toolkit_file`. Only that function changes here; TASK-128 owns the doctor checks.
- `tools/adlc/tests/test_toolkit_root.py` — new.
- `tools/adlc/tests/test_renumber.py` — the missing-partial case now raises.
- `tools/adlc/tests/test_forge_config.py` — a case on a cache-shaped tree with no `~/.claude/skills`.

## Acceptance Criteria

- [x] On a cache-shaped copy of the tree (no `.git`, a sandbox `HOME` with no `~/.claude/skills`), `toolkit_root()` returns the copy's root, and `forge_config` and `lane_check` load their sibling `_machine_config.py` from it.
- [x] `toolkit_root()` refuses, rather than returning a wrong root, when `<root>/tools/adlc/toolkit_root.py` is not the running file. It must not refuse on a legitimate cache-shaped copy or on the symlink checkout (the benign paths).
- [x] `renumber.remote_collision` raises with a message naming the missing partial. It does not return False.
- [x] A search of `tools/adlc/*.py` finds no `~/.claude/skills` read except in the doctor's symlink-route checks in `checks.py`, which TASK-129 lists as an exception.
- [x] `toolkit_root.py` imports only the standard library, because the doctor imports it (LESSON-395).
- [x] `python3 -m pytest tools/adlc/tests -q` passes, collecting more than zero cases.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/adlc/tests/test_toolkit_root.py::test_cache_shaped_copy_resolves_without_skills_symlink` | no |
| BR-2 | test-case | `tools/adlc/tests/test_forge_config.py::test_machine_config_loader_from_cache_shaped_tree` | no |
| BR-3 | test-case | `tools/adlc/tests/test_toolkit_root.py::test_symlink_checkout_resolves_unchanged` | yes |
| BR-7 | test-case | `tools/adlc/tests/test_toolkit_root.py::test_stdlib_only_imports` | no |
| AC-3 | test-case | `tools/adlc/tests` on a symlink-only sandbox | yes |

## Technical Notes

- Use `os.path.realpath`, never `abspath`. A symlinked install walks wrongly from the link's directory (ASSUME-001).
- Do not trust `git rev-parse --show-toplevel` for the toolkit root. `~/.claude` can sit inside an enclosing dotfiles repo, and the cache copy may have no `.git` at all.
- `test_install_shim.py` slices `install.sh` text. This task does not touch `install.sh`, and that test must pass unchanged.
