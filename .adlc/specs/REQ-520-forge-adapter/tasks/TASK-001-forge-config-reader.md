---
id: TASK-001
title: "Forge config reader + provider resolution (tools/adlc/forge_config.py)"
status: complete
parent: REQ-520
created: 2026-06-11
updated: 2026-06-11
dependencies: []
---

## Description

A thin Python reader for the `forge:` block of the shared ADLC config, mirroring
`tools/kimi/_common.parse_delegate_config` (flat `key: value`, no PyYAML). Resolves
the provider with precedence per-project `.adlc/config.yml` > machine config > `auto`,
and refuses key-shaped `auth:` values (BR-6). Provider auto-detection from an `origin`
URL is exposed as a callable so both the partial and the doctor check use one source.

## Files to Create/Modify

- `tools/adlc/forge_config.py` — new: `parse_forge_config(path)`, `looks_like_key(v)`
  (ported from `_common._looks_like_key`), `detect_provider_from_url(url)`,
  `resolve_provider(repo_dir, cfg_project, cfg_machine)` returning
  `(provider, source)` or raising on unrecognized-host `auto`.

## Acceptance Criteria

- [ ] `parse_forge_config` reads `forge.provider` and `forge.auth` from a flat YAML
      `forge:` block; absent/unreadable file → `{}`.
- [ ] `detect_provider_from_url` maps `github.com`→`github`, `dev.azure.com` and
      `*.visualstudio.com`→`azure-devops`, everything else → raise/`None` (caller
      fails loud naming URL + supported providers).
- [ ] Precedence: per-project config > machine config > `auto`.
- [ ] A key-shaped `auth:` value is refused with an actionable error (reuses the
      `_looks_like_key` signature: known key families, underscore-free long
      mixed-class blob, or non-env-var-name shape).
- [ ] Pure standard library (no PyYAML); importable without the delegation venv.

## Technical Notes

Port `_strip_inline` and `_looks_like_key` from `tools/kimi/_common.py` (do not import
across the kimi/adlc boundary — adlc keeps no hard dependency on the kimi module, same
as `checks._config_enabled`'s subprocess probe). Block-parsing loop is the same shape
as `parse_delegate_config` (top-level `forge:` mapping, dedent ends block).
