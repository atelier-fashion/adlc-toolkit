---
id: TASK-125
title: "/init and /template-drift take ToolkitRoot as canonical; /template-drift names the plugin version as baseline"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-124]
---

## Description

Apply architecture ADR-8. `/init`'s preflight, its copy commands and its template guards read from `$ADLC_TOOLKIT_ROOT`. `/template-drift` replaces its one toolkit-reaching `!` line with a fence, and branches Step 0a on route:

- **symlink:** today's BUG-204 checks are unchanged.
- **plugin:** the baseline is `adlc plugin <version>`, read from the cache copy's `plugin.json`. The run downgrades to `unverified-baseline` when that file is unreadable.

The presets and config-template comments that cite `~/.claude/skills/presets/` move with them, because `/init` copies them.

## Files to Create/Modify

- `init/SKILL.md`:
  - the preflight guard and its error message, which names both routes;
  - the copy commands for ETHOS, templates, partials, workflows, taxonomy, the settings template and the config template;
  - the template guards and the copy-surface list;
  - the scaffold comments.
- `template-drift/SKILL.md`:
  - remove the `!` line that lists `~/.claude/skills/templates/`, and add an equivalent fence;
  - Step 0a route branch: `readlink ~/.claude/skills` becomes `$ADLC_TOOLKIT_ROOT`;
  - the baseline line names the plugin version;
  - prose paths become `$ADLC_TOOLKIT_ROOT`.
- `templates/config-template.yml` — the two preset-path comments.
- `presets/README.md` — the copy path.
- `tools/lint-skills/tests/test_sync_surface_parity.py` — keep `/init`'s copy-surface list and `INIT_COPIED_SURFACES` in parity after the edit.

## Acceptance Criteria

- [x] In a sandbox with only `ADLC_TOOLKIT_ROOT` pointing at a cache-shaped copy, which has no `.git` and no `~/.claude/skills`, `/init`'s copy fences, extracted and run, produce the same `.adlc/` tree as on the symlink route.
- [x] `/template-drift`'s Step 0a, extracted and run on a plugin-shaped root, prints a baseline line that contains the plugin version from `plugin.json`. With `plugin.json` removed, it reports `unverified-baseline` and does not report `stale`.
- [x] On the symlink route, Step 0a's output is byte-identical to today's for a clean, current checkout and for a dirty one. This is the BUG-204 behavior, kept, and it is the benign path.
- [x] `tools/lint-skills/check.sh` passes, including `sync-surface-parity`, `unguarded-source` and `toolkit-root-line`.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-8 | test-case | `tools/lint-skills/tests/test_sync_surface_parity.py::test_init_surfaces_match` | no |
| BR-8 | test-case | `partials/tests/plugin-route.test.sh::case_template_drift_names_plugin_version` | no |
| BR-8 | test-case | `partials/tests/plugin-route.test.sh::case_template_drift_symlink_baseline_unchanged` | yes |
| AC-8 | test-case | `partials/tests/plugin-route.test.sh::case_template_drift_names_plugin_version` | no |

## Technical Notes

- BUG-204's rule holds: a drift detector may say it could not establish a trustworthy baseline, but it never quietly substitutes another one.
- Removing the `!` line follows REQ-666 BR-2's direction (run-and-read fences), so that REQ's later rewrite has one less line to move.
- `plugin.json` is read with the same duplicate-key-rejecting parse TASK-121 uses, through a one-line `python3 -c` or the lint helper. A shell `sed` of JSON is not a parser (LESSON-716).
- The two `case_template_drift_*` cases are added to `partials/tests/plugin-route.test.sh`, which TASK-123 creates.
