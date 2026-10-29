---
id: TASK-128
title: "adlc doctor: route-aware checks, a plugin-route check, and the doubled-install finding"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-127, TASK-132]
---

## Description

Apply architecture ADR-7. The doctor learns its route from `realpath(__file__)`: `plugin` under `~/.claude/plugins/cache/`, `symlink` otherwise. Today a plugin-only machine FAILs four checks: `skills-symlink`, `agents-symlink`, `toolkit-clean` (a misleading "detached HEAD") and `path-shims`. Those four become `applies_to: symlink` and SKIP with a notice on the plugin route. Two checks are new:

- **`plugin-route`** reports the route and version. On the plugin route it checks the pointer file and the `scripts/adlc` shim.
- **`doubled-install`** fires only when both installs are present. It names which copy each spelling of a sample skill reaches, and prints one copy-pasteable fix per way out.

## Files to Create/Modify

- `tools/adlc/doctor.py` — `Profile.route`, derived once.
- `tools/adlc/checks.py`:
  - `check_plugin_route` and `check_doubled_install`, registered in `REGISTRY`: `plugin-route` first, `doubled-install` after `agents-symlink`;
  - `applies_to` gating on the four symlink-shaped checks;
  - route-aware remediation text: "re-run ./install.sh --repair" only on the symlink route.
- `tools/adlc/tests/test_plugin_route.py` — new. It covers three sandbox machine shapes (symlink-only, plugin-only, both) through the `expanduser` sandbox pattern in `test_checks.py`.
- `tools/adlc/tests/test_checks.py` — update the `--checks` id list and any symlink case that needs an explicit `route`.
- `tools/adlc/README.md` — rows for the two checks, plus the route-aware remediations.

## Acceptance Criteria

- [x] On a plugin-only sandbox, `adlc doctor` exits 0 with no FAIL. The four symlink checks print SKIP with a notice naming the plugin route.
- [x] On a doubled sandbox, `doubled-install` FAILs and prints three things:
  - that bare `/spec` reaches the personal copy at `~/.claude/skills` and `/adlc:spec` reaches the plugin;
  - `claude plugin uninstall adlc@adlc-toolkit`;
  - the two `rm` commands for the symlinks.
- [x] On a symlink-only sandbox and on a plugin-only sandbox, `doubled-install` passes and prints no doubled-install finding (the benign paths).
- [x] On a symlink-only sandbox, every pre-existing check returns the same result and detail as before this task (BR-3).
- [x] `checks.py` and `doctor.py` import only the standard library (LESSON-395). A test asserts this by AST-walking their imports.
- [x] `python3 -m pytest tools/adlc/tests -q` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-11 | test-case | `tools/adlc/tests/test_plugin_route.py::test_doubled_install_reported_with_fixes` | no |
| BR-11 | test-case | `tools/adlc/tests/test_plugin_route.py::test_no_doubled_finding_symlink_only` | yes |
| BR-11 | test-case | `tools/adlc/tests/test_plugin_route.py::test_no_doubled_finding_plugin_only` | yes |
| BR-7 | test-case | `tools/adlc/tests/test_plugin_route.py::test_doctor_imports_stdlib_only` | no |
| BR-3 | test-case | `tools/adlc/tests/test_checks.py` symlink cases unchanged | yes |
| AC-1 | test-case | `tools/adlc/tests/test_plugin_route.py::test_plugin_only_doctor_no_failures` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_plugin_route.py::test_doubled_install_reported_with_fixes` | no |

## Technical Notes

- Detecting the plugin install takes two signals:
  - a directory matching `~/.claude/plugins/cache/*/adlc/*/` whose `.claude-plugin/plugin.json` names `adlc`;
  - when `~/.claude/plugins/installed_plugins.json` exists, its record. TASK-120 recorded where installs are listed.

  Prefer the record when present. When the two disagree, report it as `unknown`; never as the more reassuring class (LESSON-581).
- `realpath` everything before comparing (ASSUME-001). `~/.claude` may sit inside a dotfiles repo, so do not trust `git rev-parse --show-toplevel` for the route.
- The bare-name claim in the finding cites TASK-120's verification row. If that row refuted it, the finding states what was measured instead.

## Implementation Notes

- **Route rule (N3).** `plugin` when the running copy is inside `~/.claude/plugins/cache/` *or* is a root `installed_plugins.json` records for `adlc@*`. A `directory` marketplace's root is read from `known_marketplaces.json` (`installLocation`, then `source.path`) and its `marketplace.json`, because a local-path install runs from its source (verification.md row 12, E4). Anything else is `symlink`, the route whose checks all run.
- **Unknown is a FAIL.** A record that is unreadable, not schema version 2, missing an absolute `installPath`, pointing at a tree with no `plugin.json` naming adlc, or listing no adlc while the cache holds one gives `unknown`. `plugin-route` then FAILs (cannot confirm the running copy), and `doubled-install` FAILs next to a live symlink install.
- **Route-aware fixes beyond `--repair`.** `pyyaml` and `delegate-gate` also printed `install.sh --with-delegation`, which on the plugin route would symlink the cache copy into `~/.claude` and double the install. On the plugin route they now print the pinned pip install (pin read from `tools/delegate/requirements.txt`) and the config edit.
- **Keep-the-plugin fix removes `~/bin/adlc`** when that shim runs the clone. Without it, `adlc doctor` keeps running the clone after the links are gone and advises re-creating them. Verified end to end on a sandbox: the printed line turns the doctor green.
- **Report.** A remediation with several lines prints one `-> fix:` line each; the `profile:` line carries `route=`.
- `doctor._detect_repo_root` and `adlc._repo_root` use `toolkit_root` instead of `git rev-parse` (left by TASK-132).
- `plugin-route` treats "adlc not on PATH" as a FAIL only inside a Claude Code session, recognised by `CLAUDECODE=1`. That variable was observed on Claude Code 2.1.309 and is not part of TASK-120's record.
