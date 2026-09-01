---
id: TASK-091
title: "Relocate cascade coverage to Python; add the cross-layer veto agreement test"
status: complete
parent: REQ-603
created: 2026-09-01
updated: 2026-09-01
dependencies: [TASK-089, TASK-090]
---

## Description

Move cascade assertions out of the shell suite (which now owns only the gate's own
responsibilities) into the Python suite, and add the one test that makes BR-2's duplication
safe: a cross-layer check that both veto implementations agree over a shared input vector.

This task is where BUG-209's structural cause is actually closed. The shell suite has asserted
`"ADLC_DISABLE_DELEGATE=1 beats everything"` and passed while the CLIs ignored the variable —
coverage of the copied layer standing in for coverage of the real resolver.

## Files to Create/Modify

- `partials/tests/delegate-gate.test.sh` — reduce to BR-8's four classes; drop cases asserting which authorizing arm wins
- `tools/delegate/tests/test_resolve_provider.py` — absorb the relocated cascade cases
- `tools/delegate/tests/test_cross_layer_veto.py` — new: drives shell and Python over one input vector

## Acceptance Criteria

- [ ] The shell suite contains a case for each of BR-8's four classes — probe pass-through, fail-closed, no-binary without probing, veto short-circuit — and **no** case whose setup asserts which authorizing arm wins
- [ ] For each of `1`, `0`, `` (empty), `true`, `yes`, `2`, `01`, and unset, the shell veto and `delegation_enabled()` reach the same disabled/not-disabled conclusion, asserted by a **single** test driving both layers over the same list so widening one alone fails
- [ ] Removing the `ADLC_DELEGATE_ENABLED` arm from `delegation_enabled()` changes the gate's verdict for an install whose only opt-in signal is that variable
- [ ] Removing the `ADLC_DISABLE_DELEGATE` arm from `delegation_enabled()` causes the Python suite to fail and `require_delegation_enabled()` to stop refusing, while the gate's veto still holds — asserted **without** performing any transmission
- [ ] Reverting each of the four arms individually causes at least one Python test to fail; enumerate the four results
- [ ] `sh partials/tests/run.sh` passes under bash and zsh; the full Python suite passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/delegate/tests/test_cross_layer_veto.py::test_both_layers_agree_over_input_vector` | yes |
| BR-8 | test-case | `partials/tests/delegate-gate.test.sh`: case-list audit for authorizing-arm setups | no |
| BR-9 | test-case | `tools/delegate/tests/test_resolve_provider.py::test_each_arm_reverted_fails_a_test` | no |
| AC-3 | test-case | `tools/delegate/tests/test_cross_layer_veto.py::test_shared_input_vector_parity` | yes |
| AC-5 | test-case | `tools/delegate/tests/test_resolve_provider.py::test_removing_env_arm_changes_gate_verdict` | no |
| AC-6 | test-case | `tools/delegate/tests/test_resolve_provider.py::test_removing_veto_stops_cli_refusing` | yes |
| AC-14 | test-case | `tools/delegate/tests/test_resolve_provider.py::test_per_arm_revert_enumeration` | no |
| AC-15 | test-case | `partials/tests/delegate-gate.test.sh`: four-class coverage audit | no |
| BR-8 | test-case | `partials/tests/delegate-gate.test.sh::a compliant suite is NOT flagged by the case-list audit` | yes |
| BR-9 | test-case | `tools/delegate/tests/test_resolve_provider.py::test_covered_arm_reports_no_false_gap` | yes |
| AC-17 | test-case | `partials/tests/delegate-gate.test.sh::passes identically under bash and zsh after relocation` | yes |
| AC-7 | test-case | `tools/delegate/tests/test_resolve_provider.py::test_gate_verdict_enabled_false_plus_legacy_key` | yes |
| AC-8 | test-case | `tools/delegate/tests/test_resolve_provider.py::test_gate_verdict_no_config_plus_legacy_key` | yes |

## Technical Notes

The cross-layer test is the point of the task. Two per-layer tests cannot substitute: each
passes in isolation precisely while the layers diverge, which is the failure mode. Drive the
real `delegate-gate.sh` in a subshell and `delegation_enabled()` in-process over the same
vector, and compare.

AC-6 must **not** be verified by transmitting. Assert that `require_delegation_enabled()`
returns instead of raising `SystemExit`; a network call would put the governance violation
inside the suite that exists to prevent it, and would break the hermetic-test posture.

Prove every new case load-bearing by reverting the arm it covers and confirming failure
(LESSON-602). A case that passes both before and after is a boundary guard, not coverage —
label it as such rather than counting it.
