---
id: TASK-089
title: "Add resolve_gate_verdict() as the single authority, exposed as --print-gate"
status: draft
parent: REQ-603
created: 2026-09-01
updated: 2026-09-01
dependencies: []
---

## Description

Create the single resolver the whole REQ depends on: `_common.resolve_gate_verdict()`,
returning `(enabled: bool, reason: str)` over every arm the probe owns — veto, env opt-in,
config, legacy key. Expose it on both CLIs as `--print-gate`, emitting `<enabled> <reason>` on
one line.

This is the foundation task; nothing else can land first.

## Files to Create/Modify

- `tools/delegate/_common.py` — add `resolve_gate_verdict()`; it wraps `resolve_provider()` and catches the key-in-config `SystemExit`, mapping it to `disabled-via-config`
- `tools/delegate/adlc-read` — add `--print-gate`, handled beside `--print-enabled`, before every transmission guard
- `tools/delegate/adlc-write` — same flag, same placement

## Acceptance Criteria

- [ ] `resolve_gate_verdict()` returns one of the four probe reasons: `ok`, `disabled-via-env`, `disabled-via-config`, `not-opted-in` — never `no-binary` or `unset`, which are the gate's alone
- [ ] It routes through `resolve_provider()`, not `delegation_enabled()` alone, so a key-in-config config reports `0 disabled-via-config` rather than `1 ok` (LESSON-392)
- [ ] `--print-gate` prints exactly one line, `<enabled> <reason>`, and exits 0 on every path including disabled
- [ ] `--print-gate` is never routed through `require_delegation_enabled()`; with `ADLC_DISABLE_DELEGATE=1` it exits 0 reporting `0 disabled-via-env` rather than refusing (REQ-603 BR-10)
- [ ] `--print-enabled` output is byte-identical to before, verified against a frozen fixture copy of the pre-REQ `_adlc_delegate_opted_in`
- [ ] Both flags run on a machine with no `openai` SDK installed — imports stay lazy (LESSON-022, BUG-056)
- [ ] `ADLC_DISABLE_DELEGATE` outranks every authorizing arm, and only the literal `"1"` disables

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/delegate/tests/test_print_gate.py::test_print_gate_emits_verdict_and_reason` | no |
| BR-3 | test-case | `tools/delegate/tests/test_print_gate.py::test_print_enabled_output_unchanged` | yes |
| BR-6 | test-case | `tools/delegate/tests/test_print_gate.py::test_reason_always_within_enum` | no |
| BR-10 | test-case | `tools/delegate/tests/test_print_gate.py::test_probe_reports_disabled_never_refuses` | yes |
| AC-12 | test-case | `tools/delegate/tests/test_print_gate.py::test_probe_exits_zero_under_kill_switch` | yes |
| AC-13 | test-case | `tools/delegate/tests/test_print_gate.py::test_print_enabled_against_frozen_caller` | yes |
| BR-4 | test-case | `tools/delegate/tests/test_print_gate.py::test_enabled_false_without_legacy_key_is_disabled_via_config` | no |

## Technical Notes

`resolve_provider()` — not `delegation_enabled()` — is the required entry point. The existing
`--print-enabled` at `adlc-read:116-122` already does this and catches `SystemExit` for
malformed config; `--print-gate` must preserve that behaviour or it silently regresses
LESSON-392 while passing every test in this REQ.

Reason derivation follows architecture ADR-4, **ratified as option (b)**: an explicit
`enabled: false` yields `disabled-via-config` regardless of whether a legacy key is exported.
Derive it from the three-state config `parse_delegate_config` already returns — do **not** port
the shell heuristic ("config file exists AND a legacy key is present"), which is the
imprecision being corrected and which would re-introduce a legacy-key read on the Python side
purely to emulate shell.

This is the REQ's only intentional behaviour change. The return code is unchanged (`1` either
way); only the label moves, from `not-opted-in` to `disabled-via-config`. Everything else in
the six-reason matrix must stay byte-identical, which AC-21 asserts exhaustively.
