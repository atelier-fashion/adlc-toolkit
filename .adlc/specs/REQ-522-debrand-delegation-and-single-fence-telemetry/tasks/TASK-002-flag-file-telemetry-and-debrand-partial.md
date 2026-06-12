---
id: TASK-002
title: "Single-fence-safe telemetry: skill-flag.sh KV store + flag-derived emit-step-telemetry"
status: complete
parent: REQ-522
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-001]
---

## Description

Fix the inert telemetry (BR-4, ADR-3). Make the cross-step state survive across
fenced blocks by persisting it in the flag file, then rewrite the shared
`_adlc_emit_step_telemetry` to derive every input from the flag file instead of from
caller shell vars. De-brand the telemetry variable names in the partial.

## Files to Create/Modify

- `tools/delegate/skill-flag.sh` — add two subcommands:
  - `mark <path> <key> <value>` — append `key=value` to the flag file (creates if absent).
  - `read <path> <key>` — echo the LAST value for `<key>` (empty string + exit 0 if
    absent). POSIX `awk -F=` keyed on the last matching line.
  Keep `create`/`check`/`clear` byte-compatible. `create` still prints the path and the
  file starts empty.
- `partials/emit-step-telemetry.sh` — rewrite `_adlc_emit_step_telemetry`:
  - Source `delegate-tools-path.sh` (not `kimi-tools-path.sh`); use `$DELEGATE_TOOLS`.
  - Read `start_s`, `invoked`, `exit`, `reason` from the flag file via
    `"$DELEGATE_TOOLS"/skill-flag.sh read "$flag" <key>` — do NOT read caller shell
    vars `$start_s`/`$ASK_KIMI_INVOKED`/`$KIMI_EXIT`.
  - Signature gains a skill arg so spec/proceed/wrapup can reuse it:
    `_adlc_emit_step_telemetry <skill> <step>` (analyze passes `analyze`).
  - Resolution precedence unchanged (no-invoke→fallback/reason; invoked+flag-still-set
    →ghost-skip; invoked+exit0→delegated; invoked+exit≠0→fallback/api-error). A missing
    flag file (lost path) → `mode=fallback,reason=no-flag,gate_result=fail`.
  - Clear the flag at the end on every path (AC-3).
  - Rename header references away from "Kimi"; `ADLC_KIMI_GATE_REASON` → read the
    `reason` the skill `mark`ed (the gate reason is now persisted at gate time).

## Acceptance Criteria

- [ ] `skill-flag.sh mark`/`read` round-trip the last value for a key; `read` of an
      absent key echoes empty and exits 0.
- [ ] `_adlc_emit_step_telemetry` derives ALL state from the flag file — zero caller
      shell-var reads — and takes `<skill> <step>` args.
- [ ] Driving the partial with `invoked=1,exit=0` and the flag cleared produces
      `mode=delegated,gate_result=pass`, `duration_ms` computed from the marked
      `start_s` (>0).
- [ ] Driving it with `invoked=1` but the flag STILL present produces `mode=ghost-skip`.
- [ ] Driving it with no `invoked` mark produces `mode=fallback,gate_result=fail`.
- [ ] No flag file remains after the partial runs to completion.
- [ ] `emit-telemetry.sh` output schema is unchanged (BR-6).

## Technical Notes

- `start_s` is marked once at create time so duration is real (fixes the garbage-arith
  bug).
- Verify by executing the real partial under BOTH `zsh -c` and `bash -c` (BR-6,
  LESSON-329) — covered in TASK-006's equivalence test.
- POSIX/zsh/BSD-safe (BR-7): no `local`, no bare `$<digit>`, `mktemp -t name.XXXXXX`.
