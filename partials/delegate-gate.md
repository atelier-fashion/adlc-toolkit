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

## Where the answer comes from (REQ-603)

The gate **may veto; only Python may authorize.** It makes exactly two decisions,
and both can only *withhold* delegation:

1. **binary resolution** — an unresolvable `adlc-read` returns `2 no-binary`. It
   is the one question the probe cannot answer.
2. **the veto** — `ADLC_DISABLE_DELEGATE=1` returns `1 disabled-via-env`, with
   **zero forks**, so the emergency stop stays the cheapest path in the gate.

Everything that could *grant* delegation is resolved by one call to
`adlc-read --print-gate`, which prints `<enabled> <reason>` and exits 0 on every
path — it reports, it never refuses. The gate validates the reason against the
frozen enum and fails closed on anything else.

The veto is deliberately implemented in **both** layers — and in exactly two places total: this file, and `_common._kill_switch_set()`, which every Python site calls. It briefly had four Python-side comparisons while the parity test checked only two of them. That is safe only because
a veto can never return *enabled*: the copies agree or abstain, but cannot
contradict — **provided Python recognises at least every input the shell does.**
Both test the literal `"1"`; widening one alone reintroduces BUG-209, and
`tools/delegate/tests/test_cross_layer_veto.py` is what enforces it.

**Upgrade note:** the gate and `adlc-read` must be upgraded together. An
`adlc-read` predating `--print-gate` makes the gate fail closed — delegation is
off, safely but silently, reported as `not-opted-in`.

## Return-code contract

`adlc_delegate_gate_check` returns:

- **0 — delegated**: `adlc-read` resolves (on PATH, or executable at `$HOME/bin/adlc-read`) AND `ADLC_DISABLE_DELEGATE` is not `1` AND opt-in is satisfied. Run the delegated path.
- **1 — disabled**: `ADLC_DISABLE_DELEGATE=1` is set, OR delegation is not opted in (fresh-install posture, BR-11). Run the fallback path and emit the **disabled-via-env** stderr line.
- **2 — unavailable**: `adlc-read` does not resolve (not on PATH and no executable at `$HOME/bin/adlc-read`). Run the fallback path and emit the **unavailable** stderr line.

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
| 1      | `disabled-via-config`       | `delegate.enabled: false` — an operator opt-out (BUG-205), **or** a config the real call refuses (key-in-config, LESSON-392) |
| 1      | `not-opted-in`              | no opt-in signal (fresh install, BR-11)  |
| 2      | `no-binary`                 | `adlc-read` not resolvable (PATH or `$HOME/bin`) |

> **Behaviour change (REQ-603 ADR-4).** `delegate.enabled: false` now reports
> `disabled-via-config` whether or not a legacy key is exported. The pre-REQ shell
> helper never read `enabled` — it returned `disabled-via-config` only when a
> config file existed *and* a legacy key happened to be set, so the same written
> instruction produced two different labels depending on an unrelated variable.
> The **return code is unchanged** (`1` either way); only the label is corrected.

`disabled-via-config` and `not-opted-in` both mean "delegation is off", and a
caller that only branches on the return code can keep treating them alike. They
are distinguished so telemetry can tell a deliberate opt-out apart from a machine
that was simply never opted in — the two look identical in a return code and call
for opposite responses (leave it alone vs. offer to enable it).

The gate reports `disabled-via-config` when a config file exists, the opt-in
check came back false, and a legacy key IS present. That combination can only
arise from a written `enabled: false`: a config whose `enabled` is *absent* would
have fallen through to the key-continuity arm and opted in. With no key present
the two cases are genuinely indistinguishable and both report `not-opted-in`.

`export` is intentional (not just assignment) so the variable is visible
to child processes the skill spawns — e.g., a future `adlc-read` invocation
could read it for self-documentation. Adding a new gate condition (e.g.,
a budget cap) means editing ONLY this file — no per-skill churn.

## `ADLC_READ_BIN`: the resolved binary

GUI-launched Claude Code sessions may run with a PATH that lacks `~/bin`
(only `.zshrc` adds it), so `command -v adlc-read` alone would report
`no-binary` on machines where `~/bin/adlc-read` is installed and working.
Sourcing the partial (and every `adlc_delegate_gate_check` call) resolves and
exports `ADLC_READ_BIN`:

- `adlc-read` — the bare name, when it is on PATH (PATH wins);
- `$HOME/bin/adlc-read` — the absolute path, when not on PATH but executable
  there;
- empty — neither (the gate returns 2 / `no-binary`).

Delegated-invocation fences MUST source this partial in the same fenced
block and invoke `"${ADLC_READ_BIN:-adlc-read}"` instead of bare
`adlc-read` — fenced blocks do not share shell state, so the export from
the gate-check fence does not reach the invocation fence. The `:-adlc-read`
default keeps the invocation working in a consumer repo whose vendored
`.adlc/partials/delegate-gate.sh` predates this variable.

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
