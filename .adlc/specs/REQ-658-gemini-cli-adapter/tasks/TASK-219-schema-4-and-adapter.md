---
id: TASK-219
title: "Schema 4, the formats and harness/antigravity.yml"
status: complete
parent: REQ-658
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-218]
repo: adlc-toolkit
---

## Description

Add schema 4, four format renderers, the rendered `skills` surface, the adapter and its goldens.

## Files to Create/Modify

- `tools/adlc/harness_adapter.py` — schema 4, `hook_cwd`, `hook_output_envelope`, `fence_unmatchable`, the format table, `skills` as a rendered surface
- `tools/adlc/harness_render.py` — the four formats, the hook wrapper, the skills file, its golden
- `tools/adlc/agents_render.py` — `agent_header` and the refusal
- `harness/antigravity.yml`, `harness/antigravity/README.md`, `harness/antigravity/rendered/` — new
- `tools/adlc/lane_check.py` — `.agents/**`
- `tools/adlc/tests/test_harness_antigravity.py` — new
- `tools/adlc/tests/test_lane_check.py` — the blocked path

## Acceptance Criteria

- [ ] The adapter loads with no harness-specific code path, and an unknown key is refused naming it
- [ ] No deny-tier spelling is an allow, no first-token fence entry renders, and removing a key fails `allowlist-fidelity`
- [ ] A hook command is the canonical command with one `cd` line before it and the envelope after it
- [ ] An agent with an unmapped tool exits non-zero naming it and writes nothing; a headerless target is refused
- [ ] Every other adapter's goldens are byte-identical

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_no_harness_name_in_code | yes |
| AC-5 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_loader_refusals | yes |
| BR-6 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_render_holds_rule_b | yes |
| AC-6 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_rm_fixture_is_omitted | no |
| BR-7 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_no_merge_surface | yes |
| AC-7 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_no_merge_surface | yes |
| BR-8 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_hook_wraps_the_canonical_command | yes |
| AC-8 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_hook_prints_inject_steps | yes |
| BR-9 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_agents_render_and_refuse | yes |
| AC-9 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_agents_render_and_refuse | yes |
| BR-12 | test-case | tools/adlc/tests/test_lane_check.py::test_agents_dir_is_blocked | yes |
| BR-13 | structural-check | tools/lint-skills: render-parity, allowlist-fidelity | no |

## Technical Notes

ADR-1 to ADR-6. Run `adlc harness render --write-goldens` last, and read the rendered output (LESSON-756). Validate rendered agents with `agy plugin validate`, which is free.
