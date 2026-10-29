---
id: TASK-170
title: "Probe module data and pure verdict logic"
status: draft
parent: REQ-664
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Create `tools/adlc/harness_probe.py` with everything that is data or a pure
function: the HarnessProfile table (`PROFILES`), the eleven-row `CATALOGUE`, the
13-key `COVERAGE` map, the four-class `ROUTINE_SET`, `FENCE_LINES` (ADR-6), the
per-harness allow/deny/hook renderers, nonce generation, `REDACT_RE` and the `~`
rewrite, the evidence-tail cap, the verdict rules (BR-5 three-way rules,
conjunction, disjunction, `ask-tier-deny`'s control gating and witness, BR-17),
`plan()` (launch ids, order, implicit `trust-then-headless`, launch count), and
the `--only` merge of an existing result file. Pure-stdlib, imports nothing from
`tools/adlc`.

## Files to Create/Modify

- `tools/adlc/harness_probe.py` — new: data tables and pure logic
- `tools/adlc/tests/test_harness_probe_unit.py` — new: combinators, nonce, plan, merge, redaction
- `tools/adlc/tests/test_harness_probe_pins.py` — new: AC-7 fence and routine-set pins, ADR-3 redaction parity, AC-14 import set

## Acceptance Criteria

- [ ] `CATALOGUE` has exactly eleven ids in run order; `COVERAGE` names every §6 item (6.1a, 6.1b, 6.2–6.12)
- [ ] the nonce is 8 lowercase alphanumerics, never a palindrome, over 5 000 draws
- [ ] conjunction/disjunction/`ask-tier-deny` rules reproduce every status and reason the spec names
- [ ] `plan()` puts `trust-then-headless` first, `transcript-locate` last, counts seven `ask-tier-deny` launches, adds the implicit trust launch on codex/gemini for `--only`
- [ ] the fence is byte-identical to `partials/README.md`'s block; the routine set is a subset of the template's allow entries
- [ ] the module's imports are all standard library

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/adlc/tests/test_harness_probe_pins.py::test_module_imports_only_stdlib` | no |
| BR-5 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_combinators` | yes |
| BR-6 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_catalogue_and_coverage` | no |
| BR-7 | test-case | `tools/adlc/tests/test_harness_probe_pins.py::test_fence_byte_identical_to_partials_readme` | no |
| BR-12 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_plan_counts` | no |
| BR-16 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_nonce_shape` | no |
| BR-17 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_ask_tier_deny_gating` | yes |
| BR-18 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_ask_tier_deny_variant_keys` | no |
| AC-7 | test-case | `tools/adlc/tests/test_harness_probe_pins.py::test_routine_set_subset_of_template` | no |
| AC-14 | test-case | `tools/adlc/tests/test_harness_probe_pins.py::test_module_imports_only_stdlib` | no |
| AC-17 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_nonce_shape` | no |
| AC-18 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_ask_tier_deny_variant_keys` | no |

## Technical Notes

Python 3.9 floor (the macOS system python): `Optional[...]`, no `X | Y`, no
`match`. Routine-set entries are command prefixes; the pin test renders each as
Claude's `Bash(<p>:*)` or `Bash(<p>)` and asserts membership in
`templates/claude-settings-template.json`'s `permissions.allow` (or the routine
allow entries of `templates/permissions.yml` when that file exists). The
`$HOME/.claude/skills` literals inside `FENCE_LINES` carry `# adlc-home: alias`.
