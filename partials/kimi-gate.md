# Kimi delegation gate protocol

This partial factors the predicate that decides whether a skill should
delegate a bulk-read or bulk-draft step to `ask-kimi` or fall back to
Claude doing the work directly. The predicate appears in `analyze`,
`proceed` (Phase 5), `spec`, and `wrapup`. Per REQ-416 BR-3 (ADR-2),
the predicate lives here once; per-skill stderr messages and fallback
bodies stay inline at the call site.

## Sourcing the partial

Use a two-level fallback so the macro works in consumer projects that
haven't re-run `/init` since the toolkit shipped the partial:

```sh
. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh
```

`.` (dot) is POSIX; do NOT use `source` (bash-only).

## Return-code contract

`adlc_kimi_gate_check` returns:

- **0 — delegated**: `ask-kimi` is on PATH AND `ADLC_DISABLE_KIMI` is not `1`. Run the delegated path.
- **1 — disabled**: `ADLC_DISABLE_KIMI=1` is set. Run the fallback path and emit the **disabled-via-env** stderr line.
- **2 — unavailable**: `ask-kimi` is not on PATH. Run the fallback path and emit the **unavailable** stderr line.

Read `$?` IMMEDIATELY into a local variable — `$?` is clobbered by every
subsequent command:

```sh
. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh
adlc_kimi_gate_check; gate=$?
case $gate in
  0) # delegated path — invoke ask-kimi, capture stdout, post-validate
     ;;
  1) # disabled path — emit "/<skill>: ask-kimi disabled via ADLC_DISABLE_KIMI — <purpose>"
     ;;
  2) # unavailable path — emit "/<skill>: ask-kimi unavailable — <purpose>"
     ;;
esac
```

## Canonical stderr emit pattern

Each skill defines its own `<purpose>` clause; the partial does NOT emit
anything itself. The two fallback templates parameterized by skill name
and purpose are:

- Unavailable (return 2): `/<skill>: ask-kimi unavailable — <purpose>`
- Disabled (return 1):    `/<skill>: ask-kimi disabled via ADLC_DISABLE_KIMI — <purpose>`

Examples currently in use:

| skill   | purpose clause                                           |
|---------|----------------------------------------------------------|
| analyze | `Claude is reading shape files directly` (Step 1.5)      |
| analyze | `agents running without candidate pre-pass` (Step 1.6)   |
| spec    | `Claude reading docs directly`                           |
| proceed | `reviewers running without candidate pre-pass` (Phase 5) |
| wrapup  | `Claude drafting lesson directly`                        |

When the **delegated path itself fails** (e.g., `ask-kimi` was on PATH
but the call returned non-zero), the skill emits its own combined
`ask-kimi failed — <fallback action>` line and falls through to the
fallback body — but **suppresses** the unavailable/disabled emit, so
that path still produces exactly one stderr line per invocation.

## BR-4: one stderr line per invocation

Every skill that uses this gate must emit **exactly one** stderr line
per invocation describing what happened (delegated, disabled, unavailable,
or delegation-failed-fell-back). Multiple lines per invocation make the
audit trail noisier than the signal it's supposed to provide. The case
branches above are the only places these lines should be emitted; the
partial itself stays silent.

## Adding a new Kimi-delegating skill

Source this partial; do NOT inline the predicate. The greppable check

```sh
grep -l 'command -v ask-kimi.*ADLC_DISABLE_KIMI' */SKILL.md
```

must remain empty across the toolkit. Any skill containing
`ADLC_DISABLE_KIMI` MUST also contain `partials/kimi-gate.sh`.
