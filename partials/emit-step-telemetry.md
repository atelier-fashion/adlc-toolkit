# Per-step telemetry resolve-and-emit protocol

This partial factors `_adlc_emit_step_telemetry` — the resolve-the-mode-then-
emit-one-telemetry-record block that `/analyze` runs at the close of its
Step 1.5 (pre-read) and Step 1.6 (candidate pre-pass) Kimi-delegation points.
It was introduced inline by REQ-428 to dedupe those two emit blocks; REQ-436
relocated it here (ADR-1) because a function defined in one SKILL.md fenced
block is undefined at a call site in a *different* fenced block — SKILL.md
fenced shell blocks do not share shell state across steps, so the inline
helper's Step 1.6 emit silently failed (Defect-1). Behavior is byte-for-byte
the REQ-428 behavior; only the `local`s were removed (Defect-2, ADR-3).

## Sourcing the partial

Use a two-level fallback so the macro works in consumer projects that
haven't re-run `/init` since the toolkit shipped the partial:

```sh
. .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh
```

`.` (dot) is POSIX; do NOT use `source` (bash-only).

This partial **self-sources** `partials/kimi-tools-path.sh` (with the same
two-level fallback) as its first executable line, before defining the
function. Call sites therefore do **NOT** need to source the
`kimi-tools-path` resolver themselves at the call site — sourcing this
partial both resolves/exports `$KIMI_TOOLS` and defines the function in one
step. The resolver keeps its defensive `export KIMI_TOOLS="tools/kimi"`
default, so a missing `tools/kimi` degrades silently rather than blocking
telemetry (LESSON-008 / BR-4).

## The argument

`_adlc_emit_step_telemetry` takes exactly one positional argument:

- **`$1` — step label**, e.g. `Step-1.5` or `Step-1.6`. Passed straight
  through as the `step` field of the emitted telemetry record. The two
  `/analyze` call sites invoke it as `_adlc_emit_step_telemetry Step-1.5`
  and `_adlc_emit_step_telemetry Step-1.6` respectively.

## Caller-environment contract

The function **reads** the following caller-environment variables and does
**not** define them — the caller (the `/analyze` Step 1.5 / 1.6 prologue)
must have established them in the same shell before calling:

| variable                 | meaning                                                              |
|--------------------------|----------------------------------------------------------------------|
| `start_s`                | epoch seconds (`date -u +%s`) captured *before* the gate check       |
| `ASK_KIMI_INVOKED`       | empty string iff `ask-kimi` was never invoked this step              |
| `KIMI_EXIT`              | `ask-kimi`'s exit status (`0` == clean) when it was invoked          |
| `flag`                   | skill-invocation flag id returned by `skill-flag.sh create`          |
| `ADLC_KIMI_GATE_REASON`  | reason string exported by `partials/kimi-gate.sh` (see `kimi-gate.md`)|

`$KIMI_TOOLS` is **not** part of the caller contract — this partial resolves
and exports it itself via the self-sourced `kimi-tools-path.sh`.

## Mode resolution

The function resolves the delegation `mode`/`reason`/`gate_result` triple
with a fixed four-way decision over the caller-env, in this exact order:

1. **`ASK_KIMI_INVOKED` empty** → `mode=fallback`,
   `reason=$ADLC_KIMI_GATE_REASON`, `gate_result=fail` (gate denied or never
   ran; ask-kimi never invoked).
2. else **flag still present** (`skill-flag.sh check` succeeds) →
   `mode=ghost-skip`, `reason=gate-passed-no-call`, `gate_result=pass`
   (gate passed but the delegated call was skipped — REQ-424 ghost-skip).
3. else **`KIMI_EXIT` == 0** → `mode=delegated`, `reason=ok`,
   `gate_result=pass` (delegated path ran cleanly).
4. else → `mode=fallback`, `reason=api-error`, `gate_result=pass`
   (delegated path was attempted but `ask-kimi` failed).

The number and ordering of `"$KIMI_TOOLS"/skill-flag.sh clear "$flag"` calls
across these branches plus the unconditional trailing clear are part of the
preserved REQ-428 behavior and MUST NOT change (BR-4 / AC-7).

## The emitted record

The function ends by emitting exactly one telemetry record:

```sh
"$KIMI_TOOLS"/emit-telemetry.sh analyze "$_aest_step" unknown \
  "$_aest_gate_result" "$_aest_mode" "$_aest_reason" "$_aest_duration_ms"
```

i.e. one record with:

| field        | value                                                            |
|--------------|------------------------------------------------------------------|
| `skill`      | `analyze`                                                        |
| `step`       | the `$1` argument (`Step-1.5` / `Step-1.6`)                      |
| `req`        | `unknown` (the literal string — `/analyze` has no REQ context)   |
| `gate_result`| resolved `pass` / `fail` per the mode resolution above           |
| `mode`       | resolved `fallback` / `ghost-skip` / `delegated`                 |
| `reason`     | resolved reason string per the mode resolution above             |
| `duration_ms`| `(($(date -u +%s) - $start_s) * 1000)` — whole-second resolution |

The `emit-telemetry.sh` argument order and the telemetry schema are fixed
(REQ-424); this partial must reproduce them byte-for-byte (BR-4, AC-7).

## BR-4: telemetry never blocks

Telemetry is best-effort and MUST NOT abort or block `/analyze`. The
self-sourced `kimi-tools-path.sh` is sourced with `2>/dev/null || …` and
keeps its defensive `export KIMI_TOOLS="tools/kimi"` default, so even when
the resolver path is missing `$KIMI_TOOLS` is still set and the
`skill-flag.sh` / `emit-telemetry.sh` calls degrade to silent no-ops rather
than failing the skill — the non-fatal-degrade discipline of LESSON-008
(skill telemetry must never break the skill). No `set -eu` is used here for
the same reason.

## Call-site protocol

Because SKILL.md fenced shell blocks do **not** share shell state across
steps/blocks (a function defined in one fenced block is undefined in the
next — this is the exact Defect-1 the relocation fixes), the source line and
the invocation **MUST live in the same fenced block**, with the source
immediately before the call:

```sh
. .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh
_adlc_emit_step_telemetry Step-1.5
```

Never define-here-call-there: do **not** source the partial in one fenced
block and call `_adlc_emit_step_telemetry` from another — the function would
be undefined in the second block's shell and the emit would silently fail
(`command not found`, swallowed), reproducing the very telemetry-loss class
this partial exists to eliminate (REQ-436 BR-3, the REQ-424 failure class).
Each emit point re-sources the partial; that is intentional, not redundant
(mirrors how `kimi-gate.sh` is deliberately re-sourced per step).
