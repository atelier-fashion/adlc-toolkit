# Per-step telemetry resolve-and-emit protocol

This partial factors `_adlc_emit_step_telemetry` — the resolve-the-mode-then-
emit-one-telemetry-record block that the delegating skills (`analyze`, `spec`,
`proceed`, `wrapup`) run at the close of each delegation point. REQ-436
relocated it out of `analyze/SKILL.md` (ADR-1) because a function defined in
one SKILL.md fenced block is undefined at a call site in a *different* fenced
block — SKILL.md fenced shell blocks do not share shell state across steps.
REQ-522 (ADR-3) extended it to derive ALL of its inputs from the on-disk
flag-file sidecar instead of caller shell vars, fixing the inert-telemetry bug
(every run previously recorded `mode=fallback,gate=fail` because the caller
vars were empty across the fence boundary), and de-branded the identifiers.

## Sourcing the partial

Use a two-level fallback so the macro works in consumer projects that
haven't re-run `/init` since the toolkit shipped the partial:

```sh
. .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh
```

`.` (dot) is POSIX; do NOT use `source` (bash-only).

This partial **self-sources** `partials/delegate-tools-path.sh` (with the same
two-level fallback) as its first executable line, before defining the
function. Call sites therefore do **NOT** need to source the
`delegate-tools-path` resolver themselves — sourcing this partial both
resolves/exports `$DELEGATE_TOOLS` and defines the function in one step. The
resolver keeps its defensive `export DELEGATE_TOOLS="tools/delegate"` default,
so a missing `tools/delegate` degrades silently rather than blocking telemetry
(LESSON-008 / BR-4).

## The arguments

`_adlc_emit_step_telemetry` takes two positional arguments:

- **`$1` — skill name**, e.g. `analyze` / `spec` / `proceed` / `wrapup`.
  Passed through as the `skill` field of the emitted record.
- **`$2` — step label**, e.g. `Step-1.5` / `Step-1.6` / `Phase-5`. Passed
  through as the `step` field.

## Caller contract — only `$flag`, everything else from the sidecar

The function reads exactly ONE caller-shell value, the flag path:

| variable | meaning |
|----------|---------|
| `$flag`  | the flag path returned by `skill-flag.sh create` — a literal the skill threads through, not shared state |

All telemetry FACTS are read from the flag-file sidecar (`$flag.state`) that
the skill `mark`ed, via `"$DELEGATE_TOOLS"/skill-flag.sh read "$flag" <key>`.
The skill marks these keys, each in the SAME fenced block as the operation it
records (so no shell variable crosses a fence boundary — REQ-522 BR-4):

| sidecar key | marked when | meaning |
|-------------|-------------|---------|
| `start_s`   | at create time | epoch seconds, for duration |
| `reason`    | right after the gate | the gate's `ADLC_DELEGATE_GATE_REASON` |
| `invoked`   | immediately BEFORE the delegate call | `1` (absent if the call site was never reached) |
| `exit`      | immediately AFTER the call returns | the delegate's exit status (absent → call announced but never run) |

`$DELEGATE_TOOLS` is resolved/exported by the self-sourced
`delegate-tools-path.sh`, not part of the caller contract.

## Mode resolution

The function resolves `mode`/`reason`/`gate_result` from the sidecar facts in
this exact order:

1. **no sidecar at all** (lost flag path) → `mode=fallback`, `reason=no-flag`,
   `gate_result=fail`.
2. **`invoked` unset** → `mode=fallback`, `reason=`the marked gate reason (else
   `not-invoked`), `gate_result=fail` (gate denied or never ran).
3. else **`exit` unset** → `mode=ghost-skip`, `reason=gate-passed-no-call`,
   `gate_result=pass` (the call was announced via `invoked` but never actually
   ran — REQ-424 ghost-skip, now reachable).
4. else **`exit` == 0** → `mode=delegated`, `reason=ok`, `gate_result=pass`.
5. else → `mode=fallback`, `reason=api-error`, `gate_result=pass` (the delegate
   was invoked but returned non-zero).

The resolver clears the flag AND its sidecar as its final action on every path,
so no flag file remains after a normal run (REQ-522 AC-3).

## The emitted record

```sh
"$DELEGATE_TOOLS"/emit-telemetry.sh "$_aest_skill" "$_aest_step" "${REQ_NUM:-unknown}" \
  "$_aest_gate_result" "$_aest_mode" "$_aest_reason" "$_aest_duration_ms"
```

| field        | value                                                            |
|--------------|------------------------------------------------------------------|
| `skill`      | the `$1` argument                                                |
| `step`       | the `$2` argument                                                |
| `req`        | `$REQ_NUM` (spec/proceed) or `$REQ_ID` (wrapup) if set, else `unknown` |
| `gate_result`| resolved `pass` / `fail` per the resolution above                |
| `mode`       | resolved `fallback` / `ghost-skip` / `delegated`                 |
| `reason`     | resolved reason string                                           |
| `duration_ms`| `((now - start_s) * 1000)` if `start_s` was marked, else `-`     |

The `emit-telemetry.sh` argument order and the telemetry schema are fixed
(REQ-424) and reproduced byte-for-byte (BR-6).

## BR-4: telemetry never blocks

Telemetry is best-effort and MUST NOT abort or block the skill. The
self-sourced `delegate-tools-path.sh` is sourced with `2>/dev/null || …` and
keeps its defensive `export DELEGATE_TOOLS="tools/delegate"` default, so even
when the resolver path is missing `$DELEGATE_TOOLS` is still set and the
`skill-flag.sh` / `emit-telemetry.sh` calls degrade to silent no-ops rather
than failing the skill (LESSON-008). No `set -eu` is used here for the same
reason.

## Call-site protocol

Because SKILL.md fenced shell blocks do **not** share shell state across steps,
the source line and the invocation **MUST live in the same fenced block**, with
the source immediately before the call:

```sh
. .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh
_adlc_emit_step_telemetry analyze Step-1.5
```

Never define-here-call-there. Each emit point re-sources the partial; that is
intentional, not redundant (mirrors how `delegate-gate.sh` is deliberately
re-sourced per step). The flag-file sidecar is what carries state across the
*earlier* fences (create / gate / invoke) into this resolution fence.
