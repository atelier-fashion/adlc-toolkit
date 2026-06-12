# Delegation gate protocol

This partial factors the predicate that decides whether a skill should
delegate a bulk-read or bulk-draft step to `adlc-read` / `adlc-write` or fall
back to Claude doing the work directly. The predicate appears in `analyze`,
`proceed` (Phase 5), `spec`, and `wrapup`. Per REQ-416 BR-3 (ADR-2),
the predicate lives here once; per-skill stderr messages and fallback
bodies stay inline at the call site.

## Sourcing the partial

Use a two-level fallback so the macro works in consumer projects that
haven't re-run `/init` since the toolkit shipped the partial:

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
```

`.` (dot) is POSIX; do NOT use `source` (bash-only).

## Return-code contract

`adlc_delegate_gate_check` returns:

- **0 — delegated**: `adlc-read` is on PATH AND `ADLC_DISABLE_DELEGATE` is not `1` AND opt-in is satisfied. Run the delegated path.
- **1 — disabled**: `ADLC_DISABLE_DELEGATE=1` is set, OR delegation is not opted in (fresh-install posture, BR-11). Run the fallback path and emit the **disabled-via-env** stderr line.
- **2 — unavailable**: `adlc-read` is not on PATH. Run the fallback path and emit the **unavailable** stderr line.

Read `$?` IMMEDIATELY into a variable — `$?` is clobbered by every
subsequent command:

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
adlc_delegate_gate_check; gate=$?
case $gate in
  0) # delegated path — invoke adlc-read, capture stdout, post-validate
     ;;
  1) # disabled path — emit "/<skill>: adlc-read disabled via ADLC_DISABLE_DELEGATE — <purpose>"
     ;;
  2) # unavailable path — emit "/<skill>: adlc-read unavailable — <purpose>"
     ;;
esac
# Telemetry reads the reason string the gate exported — never re-derives it:
reason="$ADLC_DELEGATE_GATE_REASON"
```

## Reason string

`adlc_delegate_gate_check` ALSO exports `ADLC_DELEGATE_GATE_REASON` on every
code path (REQ-426 BR-2, ADR-2). This is part of the public contract: callers
that need to emit "why the gate denied" telemetry SHOULD read this var
rather than re-interrogating `ADLC_DISABLE_DELEGATE` or running
`command -v adlc-read` a second time. The canonical values, paired with
their return codes, are:

| return | `ADLC_DELEGATE_GATE_REASON` | meaning                                 |
|--------|-----------------------------|-----------------------------------------|
| 0      | `ok`                        | delegated — adlc-read available, enabled |
| 1      | `disabled-via-env`          | `ADLC_DISABLE_DELEGATE=1` opted out      |
| 1      | `not-opted-in`              | no opt-in signal (fresh install, BR-11)  |
| 2      | `no-binary`                 | `adlc-read` not on PATH                  |

`export` is intentional (not just assignment) so the variable is visible
to child processes the skill spawns — e.g., a future `adlc-read` invocation
could read it for self-documentation. Adding a new gate condition (e.g.,
a budget cap) means editing ONLY this file — no per-skill churn.

## Canonical stderr emit pattern

Each skill defines its own `<purpose>` clause; the partial does NOT emit
anything itself. The two fallback templates parameterized by skill name
and purpose are:

- Unavailable (return 2): `/<skill>: adlc-read unavailable — <purpose>`
- Disabled (return 1):    `/<skill>: adlc-read disabled via ADLC_DISABLE_DELEGATE — <purpose>`

Examples currently in use:

| skill   | purpose clause                                           |
|---------|----------------------------------------------------------|
| analyze | `Claude is reading shape files directly` (Step 1.5)      |
| analyze | `agents running without candidate pre-pass` (Step 1.6)   |
| spec    | `Claude reading docs directly`                           |
| proceed | `reviewers running without candidate pre-pass` (Phase 5) |
| wrapup  | `Claude drafting lesson directly`                        |

When the **delegated path itself fails** (e.g., `adlc-read` was on PATH
but the call returned non-zero), the skill emits its own combined
`adlc-read failed — <fallback action>` line and falls through to the
fallback body — but **suppresses** the unavailable/disabled emit, so
that path still produces exactly one stderr line per invocation.

## BR-4: one stderr line per invocation

Every skill that uses this gate must emit **exactly one** stderr line
per invocation describing what happened (delegated, disabled, unavailable,
or delegation-failed-fell-back). Multiple lines per invocation make the
audit trail noisier than the signal it's supposed to provide. The case
branches above are the only places these lines should be emitted; the
partial itself stays silent.

## Adding a new delegating skill

Source this partial; do NOT inline the predicate. The greppable check

```sh
grep -l 'command -v adlc-read.*ADLC_DISABLE_DELEGATE' */SKILL.md
```

must remain empty across the toolkit. Any skill containing
`ADLC_DISABLE_DELEGATE` MUST also source the gate partial
(`partials/delegate-gate.sh`). `lint-skills` enforces this (REQ-515 BR-4 /
ADR-9, REQ-522 ADR-7).
