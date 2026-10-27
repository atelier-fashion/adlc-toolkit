---
id: TASK-111
title: "Lane check engine: tools/adlc/lane_check.py, its config section and defaults"
status: draft
parent: REQ-652
created: 2026-10-27
updated: 2026-10-27
dependencies: []
---

## Description

The mechanical half of BR-6. A Python module that reads `lanes.lite` from the project's `.adlc/config.yml` through the shared loader, diffs the worktree against a base ref, and reports one normalized fact per failing rule (architecture ADR-3). The shell wrapper is TASK-112.

## Files to Create/Modify

- `tools/adlc/lane_check.py` — new. `main(argv)` taking `--worktree <path> --base <ref>`; prints `lane_check=`, `files_counted=`, then `trigger=`/`detail=` pairs; exit 0/1/2. Defaults as listed in architecture ADR-3; project lists extend them.
- `tools/adlc/tests/test_lane_check.py` — new. Real git sandboxes (tmp repo with a base branch and a feature branch).
- `tools/adlc/README.md` — document the module and its exit codes.
- `templates/config-template.yml` — commented `lanes.lite` block (`max_files`, `blocked_paths`, `count_exclude`, `deploy_units`) between `merge_order` and `branches`, with the note that lists extend the defaults.

## Acceptance Criteria

- [ ] A diff inside the limits with no blocked or dependency path reports `lane_check=pass`, exit 0.
- [ ] Each rule fails on its own fixture and reports its trigger: `blocked-path`, `dependency` (one lockfile case, one manifest case), `deploy-units` (two units touched, only when declared), `max-files` (four counted files with the default of 3).
- [ ] Tests and `.adlc/` files are not counted toward `max_files`, but a test file under a blocked path still reports `blocked-path`.
- [ ] Project `blocked_paths` and `count_exclude` extend the defaults; `max_files` overrides the default.
- [ ] A dirty worktree, an unknown base ref, or a config with a `lanes:` key that cannot be loaded reports `lane_check=error`, `trigger=check-error`, exit 2 — never a pass.
- [ ] A config with no line-start `lanes:` key is not loaded at all (defaults apply even when PyYAML is absent).
- [ ] `python3 -m pytest tools/adlc/tests/test_lane_check.py -q` passes and collects at least one case per rule.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/adlc/tests/test_lane_check.py::test_each_rule_escalates` | yes |
| BR-2 | test-case | `tools/adlc/tests/test_lane_check.py::test_count_excludes_tests_and_adlc` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_lane_check.py::test_pass_and_fail_fixture_per_rule` | yes |
| AC-15 | test-case | `tools/adlc/tests/test_lane_check.py::test_config_overrides_extend_defaults` | no |

## Technical Notes

- Read config through `tools/delegate/_machine_config.load_machine_config` exactly as `tools/adlc/forge_config.py` does (lazy PyYAML import, LESSON-022). Validate the `lanes.lite` section against a closed schema of its own (`max_files` int ≥ 1, the three lists of strings, `deploy_units` a string→string mapping); an unknown key is an error, not a silent skip (REQ-609).
- Changed files: `git -C <worktree> diff --name-only <base>...HEAD`. Refuse a dirty tree first (`git status --porcelain` non-empty ⇒ error), as `partials/trial-merge.sh` does.
- Glob matching with `fnmatch` against repo-relative POSIX paths; treat `**/` as "zero or more directories" (write a tiny helper and test it — `fnmatch` alone does not).
- `deploy_units`: map each changed, non-excluded file to the first matching glob's unit; files matching no glob are ignored; more than one distinct unit ⇒ `deploy-units`.
- LESSON-581: the fall-through for anything unexpected is `error`, never `pass`.
