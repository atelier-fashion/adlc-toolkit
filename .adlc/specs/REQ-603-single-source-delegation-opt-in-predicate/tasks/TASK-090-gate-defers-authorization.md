---
id: TASK-090
title: "Reduce delegate-gate.sh to veto + dispatch; remove every authorizing arm"
status: draft
parent: REQ-603
created: 2026-09-01
updated: 2026-09-01
dependencies: [TASK-089]
---

## Description

Rewrite the gate so it decides only what it may: binary resolution and the veto. Every
authorizing arm — `ADLC_DELEGATE_ENABLED`, the config probe branch, legacy-key continuity —
is replaced by a single `--print-gate` invocation whose verdict and reason the gate maps to
its return code.

## Files to Create/Modify

- `partials/delegate-gate.sh` — delete `_adlc_delegate_opted_in` and `_adlc_delegate_disabled_by_config`; `adlc_delegate_gate_check` becomes resolve-binary → veto → one probe → map

## Acceptance Criteria

- [ ] No `if`/`case` in the file branches on `ADLC_DELEGATE_ENABLED`, `MOONSHOT_API_KEY`, or `KIMI_API_KEY`, and nothing reads the config file path
- [ ] The `ADLC_DISABLE_DELEGATE` veto remains, positioned **after** binary resolution and **before** any probe
- [ ] Binary unresolvable returns `2 no-binary` with zero probe invocations, including when `ADLC_DISABLE_DELEGATE=1` is also set
- [ ] The veto path returns `1 disabled-via-env` with zero probe invocations
- [ ] At most one probe invocation on any path, counted with an instrumented `ADLC_READ_BIN`
- [ ] A probe that exits non-zero, prints nothing, prints garbage, or names a reason outside the enum yields not-delegated, with `_probe_rc=$?` captured immediately after the substitution
- [ ] All six gate reason strings and the 0/1/2 shape are unchanged, except the single ADR-4 correction
- [ ] BSD- and zsh-safe: no `\b` in `grep -E`, no bare `$<digit>`, no `status` variable, no unquoted word-splitting

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `partials/tests/delegate-gate.test.sh`: no-authorizing-arm grep over the file's conditionals | no |
| BR-2 | test-case | `partials/tests/delegate-gate.test.sh::veto short-circuits with zero probes` | yes |
| BR-4 | test-case | `partials/tests/delegate-gate.test.sh::all six reasons unchanged` | yes |
| BR-5 | test-case | `partials/tests/delegate-gate.test.sh::no-binary returns 2 without probing` | yes |
| BR-6 | test-case | `partials/tests/delegate-gate.test.sh::fails closed on a broken probe` | no |
| BR-7 | test-case | `partials/tests/delegate-gate.test.sh::at most one probe per call` | yes |
| BR-11 | structural-check | `partials/tests/run.sh`: bash and zsh parity over the rewritten gate | yes |
| AC-1 | structural-check | `partials/tests/delegate-gate.test.sh`: conditional-scan for the three authorizing variables | no |
| AC-2 | structural-check | `partials/tests/delegate-gate.test.sh`: veto present and correctly positioned | yes |
| BR-6 | test-case | `partials/tests/delegate-gate.test.sh::a well-formed probe is NOT treated as failure` | yes |
| AC-4 | test-case | `partials/tests/delegate-gate.test.sh::veto beats every authorizing signal` | yes |
| AC-7 | test-case | `partials/tests/delegate-gate.test.sh::enabled false plus legacy key is disabled-via-config` | yes |
| AC-8 | test-case | `partials/tests/delegate-gate.test.sh::no config plus legacy key is ok` | yes |
| AC-9 | test-case | `partials/tests/delegate-gate.test.sh::no-binary returns 2 without probing` | yes |
| AC-10 | test-case | `partials/tests/delegate-gate.test.sh::broken probe yields not-delegated` | no |
| AC-11 | test-case | `partials/tests/delegate-gate.test.sh::at most one probe across all four paths` | yes |
| AC-19 | test-case | `partials/tests/delegate-gate.test.sh::all six reasons byte-identical` | yes |

## Technical Notes

Order is load-bearing and is now pinned by REQ-603 BR-5: binary resolution precedes the veto,
so binary-missing plus veto-set returns `2 no-binary` as today. Inverting them silently breaks
the return-code guarantee on a path no other rule covers.

Parse the probe line defensively — it is untrusted input to shell (LESSON-008). Validate the
reason against the frozen enum before exporting it; an unrecognised value is a fail-closed
condition, not a pass-through.

Keep the existing `_probe_rc=$?`-immediately-after-substitution discipline from BUG-205's fix:
command substitution discards the exit code, so a probe that printed a verdict and *then*
failed would otherwise be read as consent.
