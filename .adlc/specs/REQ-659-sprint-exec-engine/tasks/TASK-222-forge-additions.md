---
id: TASK-222
title: "Forge additions: pinned merge, protection, commit PRs, ADO allowlist, stateful mock"
status: complete
parent: REQ-659
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

BR-26 in `partials/forge.sh`, and the mock the engine's tests need.

## Files to Create/Modify

- `partials/forge.sh` — `adlc_forge_pr_view` fields, `adlc_forge_pr_list --head`, `adlc_forge_branch_protection`, `adlc_forge_commit_prs`, `--match-head-commit`, the ADO flag allowlist, mock routing
- `partials/forge.md` — the contract for each
- `tools/adlc/forge_mock.py` — stateful offline forge (ADR-8)
- `tools/adlc/forge_protection.py` — closed verdict
- `partials/tests/forge.test.sh`, `tools/adlc/tests/test_forge_mock.py` — tests

## Acceptance Criteria

- [x] Every call in AC-38 returns the named shape on both mock providers
- [x] The ADO backends pass only the five flags and reject the five named ones before `az` runs
- [x] `branch_protection` prints exactly one of three values, and any lookup failure is `unknown`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-26 | test-case | `partials/tests/forge.test.sh`: forge additions block | yes |
| AC-18 | test-case | `tools/adlc/tests/test_forge_mock.py::test_protection_verdicts` | yes |
| AC-35 | test-case | `partials/tests/forge.test.sh`: ado flag allowlist | yes |
| AC-38 | test-case | `tools/adlc/tests/test_forge_mock.py` | yes |

## Technical Notes

Stay inside `forge.sh`'s portability rules. The `gh api` placeholders resolve from cwd, so the op
runs in `${ADLC_FORGE_REPO:-.}`. Query as the identity the child pushes with (BR-8).
