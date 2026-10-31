---
id: TASK-202
title: "Add the Cursor and Copilot manifests and absorb plugin-manifest into manifest-parity"
status: complete
parent: REQ-665
created: 2026-10-30
updated: 2026-10-30
dependencies: []
repo: adlc-toolkit
---

## Description

Add the two manifests and turn `plugin-manifest` into a registry-driven
`manifest-parity` check (architecture.md ADR-1 to ADR-9). These land together:
`check.sh` fails on the checkout if either half ships alone.

## Files to Create/Modify

- `.cursor-plugin/plugin.json` — new; keys below
- `.github/plugin/plugin.json` — new; keys below
- `tools/lint-skills/check.py` — registry, rules, new check id
- `tools/lint-skills/tests/test_plugin_manifest.py` — move to the new id, overlay at `_stage`, `scanned` literals, name cases
- `tools/lint-skills/tests/test_manifest_parity.py` — new; one test per BR-7 rule
- `tools/lint-skills/tests/fixtures/plugin-manifest/ok/.cursor-plugin/plugin.json` — new fixture
- `tools/lint-skills/tests/fixtures/plugin-manifest/ok/.github/plugin/plugin.json` — new fixture
- `tools/adlc/tests/e2e/plugin-sandbox.sh` — `cmd_set_version` writes all three manifests
- `tools/adlc/tests/test_install_home.py` — hidden-entry check (line ~236) also lists `.cursor-plugin` and `.github`

## Acceptance Criteria

- [x] Both manifests hold exactly: `name` `adlc`, `version` = `VERSION`, `description` (copy plugin.json's, reworded only to drop "for Claude Code"), `author` `{"name": "Atelier Fashion"}`, `license` `MIT`, `repository` as in plugin.json, `skills` `"./"`, `agents` `[]`, `hooks` `{}`
- [x] `tools/lint-skills/check.sh` exits 0 on the checkout
- [x] Every BR-7 rule has a firing test and the clean checkout is its must-not-fire case
- [x] Every REQ-669 rule still fires under `manifest-parity`
- [x] `python3 -m pytest tools/lint-skills/tests -q`, `sh partials/tests/plugin-route.test.sh`, and `sh tools/adlc/tests/e2e/plugin-sandbox.selftest.sh` pass
- [x] No change to `.claude-plugin/`, `hooks/`, `install.sh`, `partials/*.sh`, `agents/`, any `SKILL.md`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_committed_manifests_are_clean` | yes |
| BR-2 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_root_skills_dir_is_skill_extra` | yes |
| BR-3 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_agents_ref_invalid` | yes |
| BR-4 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_hooks_ref_invalid` | yes |
| BR-5 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_version_mismatch_per_manifest` | yes |
| BR-7 | test-case | `tools/lint-skills/tests/test_manifest_parity.py` | yes |
| BR-11 | structural-check | `tools/lint-skills/check.sh` and `sh partials/tests/run.sh` | no |
| AC-1 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_committed_manifests_are_clean` | yes |
| AC-2 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_skill_added_and_removed` | yes |
| AC-3 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_version_mismatch_per_manifest` | yes |
| AC-4 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_set_incomplete_and_path_missing` | yes |
| AC-5 | test-case | `tools/lint-skills/tests/test_manifest_parity.py` | yes |
| AC-12 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_unknown_key_per_harness` | yes |

## Technical Notes

Registry key sets, each the vendor's documented top-level keys (read 2026-10-30):

- `claude`, `.claude-plugin/plugin.json`, companion `.claude-plugin/marketplace.json`, agents `canonical`, hooks `default`: `$schema name displayName version description author homepage repository license keywords metadata icon documentationUrl supportUrl privacyPolicyUrl termsOfServiceUrl defaultEnabled dependencies settings userConfig types channels skills commands agents hooks mcpServers lspServers outputStyles workflows experimental`
- `cursor`, `.cursor-plugin/plugin.json`, agents `empty`, hooks `empty`: `name description version author homepage repository license keywords logo rules agents skills commands hooks mcpServers variables`
- `copilot`, `.github/plugin/plugin.json`, agents `empty`, hooks `empty`: `name description version author homepage repository license keywords tags category agents skills commands hooks extensions mcpServers lspServers`

Rules, each message `<rule>: …— <exact edit> in <file> (REQ-665 BR-n)`:

- `set-incomplete`: a registry path absent in an armed root; keep the word "missing".
- `path-missing`: a registry companion absent, or a string path, or array of them, in `agents hooks commands mcpServers lspServers outputStyles workflows logo icon rules extensions` that does not exist. Skip inline objects and anything with `://`. `skills` entries go to the skill rules instead.
- `unparseable`: keep `_load_json_manifest`.
- `name-mismatch`: compare every manifest's `name` to the first string name in registry order; the Claude-only shape rules stay Claude-only.
- `version-mismatch`: per manifest. A missing `VERSION` is one finding on `VERSION` (test at line 179 pins it).
- `skill-missing`: a SkillSet member not reachable through `skills`, on every manifest, generalising today's reachability code. `dangling-entry`: an array entry naming a directory that does not exist. `skill-extra`: an entry naming an existing directory that holds no `SKILL.md`, and a root `skills` directory of any kind (`os.path.lexists`, ADR-8).
- `agents-ref-invalid`: `canonical` keeps today's rule; `empty` requires the key present and `== []`. `hooks-ref-invalid`: `empty` requires the key present and `== {}`.
- `unknown-key`: a top-level key not in `keys`; remediation says remove it from that file.
- `machine-path`: a walk of every string value (Python `re`, stdlib): a value starting `/` or `~/`, containing `$HOME` or `${HOME}`, or containing `/Users/` or `/home/` not preceded by a word character or dot. URLs pass.

`is_plugin_root` and its seven other callers do not change. Keep identifiers per ADR-1 and update the `:22`, `:3834`, `:3842`, `:4367`, `:4482`, `:4540` comments to name the new check. `test_inert_outside_a_plugin_root`'s filter must use the new id or it passes vacuously. `_stage` overlays `.cursor-plugin/` and `.github/` from `ok` into any fixture lacking them, writing that fixture's `VERSION` into `version`. Do not name retired words: the literal `plugin-manifest` stays only in history comments and the fixture path.
Run commands from the repo root; never touch the real `~/.claude`.
