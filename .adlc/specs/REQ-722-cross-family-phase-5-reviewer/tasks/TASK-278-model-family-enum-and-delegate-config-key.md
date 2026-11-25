---
id: TASK-278
title: "Closed ModelFamily enum and the delegate config `family` key"
status: complete
parent: REQ-722
created: 2026-11-24
updated: 2026-11-24
dependencies: []
---
## Description

Define the closed `ModelFamily` enum once, in a stdlib-only module, and add `family` to
the closed delegate config schema with its own validation branch. Expose the resolved
value through `adlc-read --print-family`, the only path by which shell learns the reviewer
family (architecture ADR-2, ADR-3).

## Files to Create/Modify

- `tools/delegate/model_family.py` — new: `MODEL_FAMILIES`, `parse_family()`, `families_differ()`; no PyYAML import
- `tools/delegate/_machine_config.py` — `family` joins `DELEGATE_KEYS`; dedicated `parse_family` branch in `validate_delegate_section`; absent resolves to `unknown`
- `tools/delegate/_common.py` — `Provider` gains a `family` slot; `version_report_lines` prints `family:` only when a config file exists
- `tools/delegate/adlc-read` — `--print-family` flag beside `--print-gate`; added to the flag list the CLI recognises
- `tools/delegate/README.md` — `family` row in the marked schema table
- `tools/delegate/tests/test_model_family.py` — new: enum closed, equality only, `unknown` never differs, no substring inference
- `tools/delegate/tests/test_machine_config.py` — unknown value rejected; absent reads `unknown`; existing configs unchanged; pinned key set
- `tools/delegate/tests/test_req609_docs.py` — README table parity includes `family`
- `tools/delegate/tests/test_differential_oracle.py` — `_ALLOWED_KEYS` gains `family`
- `tools/delegate/tests/config_corpus.py` — seeded shapes with `family` (valid, unknown value, nested, duplicate)
- `tools/delegate/tests/test_version.py` — `family:` line present with config, absent without; existing exact lines unchanged
- `tools/delegate/tests/test_print_family.py` — new: `--print-family` prints the value, `unknown` without config, exits 0

## Acceptance Criteria

- [ ] `parse_family` accepts exactly the seven enum values and raises on anything else, including case variants and model-name strings such as `kimi-k2.6`
- [ ] `families_differ` is false when either side is `unknown`, and true only on two different known values
- [ ] The strict loader rejects `family: gpt` and `family: [anthropic]` with the field named in the error, and a config without `family` resolves to `unknown`
- [ ] Every config in the existing corpus loads to the same resolved values as before (oracle and corpus tests green)
- [ ] `adlc-read --print-family` prints one enum value and exits 0 with no network call, and `ADLC_DISABLE_DELEGATE=1` does not change what it prints
- [ ] All `tools/delegate/tests` pass

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/delegate/tests/test_model_family.py::test_families_compared_by_equality_only` | no |
| BR-10 | test-case | `tools/delegate/tests/test_machine_config.py::test_family_key_unknown_value_rejected` | yes |
| BR-10 | test-case | `tools/delegate/tests/test_machine_config.py::test_existing_configs_resolve_unchanged_with_family_key` | yes |
| AC-16 | test-case | `tools/delegate/tests/test_machine_config.py::test_absent_family_reads_unknown` | yes |
| AC-5 | test-case | `tools/delegate/tests/test_print_family.py::test_print_family_without_key_is_unknown` | no |

## Technical Notes

- LESSON-614: the generic `isinstance(str)` branch at `_machine_config.py:805-812` accepts any string, so give `family` its own branch, before that branch.
- Keep `ADLC_DISABLE_DELEGATE` checks out of the `ADLC_DISABLE_DELEGATE ==` pattern that `test_cross_layer_veto.py:187-205` greps for; `--print-family` needs no veto check because it transmits nothing.
- Do not add values to the gate reason enum (`test_print_gate.py:147` pins six).
- `test_version.py:666-673, 1022` assert exact lines for the no-config and error cases; print `family:` only on the config-present path.
