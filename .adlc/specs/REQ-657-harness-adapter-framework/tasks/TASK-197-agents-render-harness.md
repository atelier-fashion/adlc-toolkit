---
id: TASK-197
title: "adlc agents render --harness; per-harness tier column"
status: complete
parent: REQ-657
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-193, TASK-196]
repo: adlc-toolkit
---

## Description

Copy renders of the canonical agents through an adapter, and the per-harness tier
column (BR-4, BR-5).

## Files to Create/Modify

- `tools/adlc/agents_render.py` — `--harness`, `--adapter-path`, harness columns, tier_map
- `tools/adlc/harness_render.py` — claude-agent-md copy format
- `tools/adlc/tests/test_harness_framework.py` — AC-3, AC-4 cases

## Acceptance Criteria

- [ ] `adlc agents render [--harness claude]` leaves `agents/` unchanged; test_agents_render.py passes unchanged
- [ ] The fake fixture vectors of AC-3 and AC-4 hold

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-4 | test-case | `tools/adlc/tests/test_harness_framework.py::test_agents_copy_render` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_harness_framework.py::test_harness_tier_column` | yes |
| AC-3 | test-case | `tools/adlc/tests/test_harness_framework.py::test_agents_copy_render` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_harness_framework.py::test_harness_tier_column` | yes |

## Technical Notes

ADR-9.
