---
id: TASK-193
title: "Adapter YAML subset, schema and loader; harness/claude.yml"
status: complete
parent: REQ-657
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

The stdlib YAML-subset parser, the HarnessAdapter schema and the one loader every
consumer calls (BR-1, ADR-1, ADR-2), and the only shipped adapter.

## Files to Create/Modify

- `tools/adlc/harness_yaml.py` — closed YAML subset parser; duplicate keys and anything outside the subset fail loud naming the line
- `tools/adlc/harness_adapter.py` — schema, loader, path expansion, permissions/hooks source loaders
- `harness/claude.yml` — the `claude` adapter (trust user-config-entry, subagent_start_hook no)
- `tools/adlc/tests/test_harness_framework.py` — loader cases
- `tools/adlc/tests/fixtures/harness/fake.yml` — test-only adapter

## Acceptance Criteria

- [ ] `harness/claude.yml` loads; each AC-1 mutation fails naming the field
- [ ] `grandfathered` outside claude's `prefix`, `fence-prefix` granularity, and a bare `if`/`sh`/`bash`/`zsh` `fence_broad_spelling` fail the loader
- [ ] Tests pass under `python3 -m pytest tools/adlc/tests/test_harness_framework.py`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_harness_framework.py::test_claude_adapter_loads` | yes |
| AC-1 | test-case | `tools/adlc/tests/test_harness_framework.py::test_loader_rejects` | yes |
| AC-16 | test-case | `tools/adlc/tests/test_harness_framework.py::test_loader_rejects_grandfathered_elsewhere` | yes |

## Technical Notes

Detect cross-check reads `harness.HARNESSES`. `exec` is validated map-or-absent.
`--adapter-path` is the only way a non-detect name loads.
