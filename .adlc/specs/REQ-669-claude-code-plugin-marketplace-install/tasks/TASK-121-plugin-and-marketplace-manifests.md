---
id: TASK-121
title: "Plugin and marketplace manifests, and the plugin-manifest lint check"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-120]
---

## Description

Add the two manifests that make this repo both the marketplace and the plugin (architecture ADR-3). Add the lint check that keeps the manifests in step with the repo (BR-12) and keeps a top-level `bin/` out (BR-20).

## Files to Create/Modify

- `.claude-plugin/plugin.json` — new. Fields: `name: "adlc"`, `version` equal to `VERSION`, `description`, `author`, `license: "MIT"`, `repository: "https://github.com/atelier-fashion/adlc-toolkit"`, `skills: "./"`. No `agents` field, because the default `agents/` scan exposes all agents.
- `.claude-plugin/marketplace.json` — new. Fields: `name: "adlc-toolkit"`, `owner`, `description`, and `plugins: [{ "name": "adlc", "source": "./" }]`.
- `tools/lint-skills/check.py` — new per-root `check_plugin_manifest(root)`, wired into `run()` beside `check_sync_surface_parity`.
- `tools/lint-skills/tests/test_plugin_manifest.py` — new tests.
- `tools/lint-skills/tests/fixtures/plugin-manifest/` — new fixture trees: `ok/`, `version-mismatch/`, `skill-missing/`, `agents-field-partial/`, `duplicate-key/`, `top-level-bin/`, `two-marketplace-entries/`.
- `tools/lint-skills/README.md` — new numbered item for `plugin-manifest`.

## Acceptance Criteria

- [x] `claude plugin validate . --strict` passes on the repo root, for both manifests. Record the Claude Code version in the PR.
- [x] `plugin-manifest` reports one finding for each of these:
  - `plugin.json` `version` is not the trimmed content of `VERSION`;
  - a `*/SKILL.md` directory is not reachable through `skills`;
  - an `agents` field is present but omits an `agents/*.md`;
  - a repeated JSON key;
  - a top-level `bin/` exists;
  - `marketplace.json` has a number of plugin entries other than one;
  - a marketplace entry's name differs from the manifest name;
  - the plugin name breaks the reserved-prefix rule.
- [x] The check reports zero findings on the `ok/` fixture and on the real repo root (the benign path).
- [x] The test suite exercises each fixture, and the check's file count is non-zero on every run. A run that scanned no manifest is a failure (LESSON-019).
- [x] `pytest tools/lint-skills/tests/ -q` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/lint-skills/tests/test_plugin_manifest.py::test_single_marketplace_entry_named_adlc` | no |
| BR-12 | test-case | `tools/lint-skills/tests/test_plugin_manifest.py::test_version_mismatch_fails` | no |
| BR-12 | test-case | `tools/lint-skills/tests/test_plugin_manifest.py::test_skill_missing_from_manifest_fails` | no |
| BR-12 | test-case | `tools/lint-skills/tests/test_plugin_manifest.py::test_repo_root_and_ok_fixture_are_clean` | yes |
| BR-20 | test-case | `tools/lint-skills/tests/test_plugin_manifest.py::test_top_level_bin_rejected` | yes |
| AC-7 | test-case | `tools/lint-skills/tests/test_plugin_manifest.py::test_version_mismatch_fails` | no |

## Technical Notes

- Parse with `json.loads(..., object_pairs_hook=...)` and reject repeated keys. `json.loads` alone keeps the last value silently, and the loader may read it differently (LESSON-716).
- "Reachable through `skills`" means one of two things. Either `skills` is `"./"`, `"."` or an array containing one of them, or the array names each skill directory. Compute the skill set by walking root-level directories that hold a `SKILL.md`, with the same rule the loader applied in the architecture probe (one level, no `.adlc/`, no `tools/`).
- The `top-level-bin` finding message cites the claude.ai sync rule and points at `scripts/` (architecture ADR-3, ADR-4).
- The marketplace `description` is required by `validate --strict`. The architecture probe failed without it.
