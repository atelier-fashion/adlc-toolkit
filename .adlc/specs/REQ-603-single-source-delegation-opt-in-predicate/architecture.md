# REQ-603 — Architecture

## Approach

The gate stops deciding authorization and becomes a dispatcher:

```
adlc_delegate_gate_check()
  1. resolve binary            → unresolvable?  return 2 no-binary        (shell, BR-5)
  2. veto                      → DISABLE=1?     return 1 disabled-via-env (shell, BR-2, no fork)
  3. one probe                 → adlc-read --print-gate  → "<enabled> <reason>"
  4. map verdict to rc         → 0 ok | 1 <reason>
```

Steps 1–2 are the only shell decisions and both can only *withhold* delegation. Every path
that concludes *delegated* runs through Python (BR-1).

On the Python side a new `_common.resolve_gate_verdict()` becomes the single authority,
returning `(enabled: bool, reason: str)`. Both CLIs expose it as `--print-gate`.

Three properties drive the design and are easy to lose:

1. **The probe must share the real call's resolution.** `--print-enabled` today calls
   `resolve_provider()` — not `delegation_enabled()` — and catches `SystemExit` so a
   malformed config (key-in-config) reports not-enabled. That is LESSON-392's fix: an
   enablement probe that checks a cheaper subset than the real call green-lights delegation
   that then fails on the first API call, mislabelled as a runtime error.
   `resolve_gate_verdict()` MUST wrap `resolve_provider()` for the same reason. Calling
   `delegation_enabled()` alone would regress LESSON-392 while passing every test in this REQ.
2. **The veto is duplicated on purpose, under a condition.** BR-2 permits it because a veto
   can only return *disabled*; the condition is that Python's veto recognises at least every
   input shell's does. Nothing but the new cross-layer test enforces that.
3. **Imports stay lazy.** `--print-gate` is a pre-API guard and must run on a machine with no
   SDK installed (LESSON-022, BUG-056).

## Data model / API / service layer

Not applicable. This toolkit has no Firestore, no HTTP API, and no routes → services →
repositories layering; the template's sections for those are deliberately empty rather than
silently dropped. The only interface changed is a CLI flag surface and a sourced shell
function contract.

## ADR-1 — The probe grows a new `--print-gate` flag; `--print-enabled` is frozen

**Decision.** Add `--print-gate`, emitting `<enabled> <reason>` as one space-separated line
(`1 ok`, `0 disabled-via-env`, …). Leave `--print-enabled` byte-identical.

**Rationale.** Resolves REQ-603 OQ-1. One line keeps BR-7's single-fork rule trivially true —
a two-flag design invites a caller to fork twice and straddle an env change. Freezing
`--print-enabled` honours BR-3 and costs nothing: the flag stays a thin wrapper over the same
resolver, so the two cannot diverge.

## ADR-2 — The `ADLC_DISABLE_DELEGATE` veto stays in shell

**Decision.** Keep it in `delegate-gate.sh` *and* in Python.

**Rationale.** BR-2's asymmetry: a veto can only return disabled, so duplication is
redundancy; an authorizing arm can return enabled, so duplication is divergence risk
(BUG-205's shape). Keeping it preserves today's zero-fork emergency stop — the alternative
made the most important control the most expensive path. The safety argument holds only while
Python's predicate is at least as broad as shell's, which is why TASK-091 adds a single test
driving *both* layers over one input vector rather than two per-layer tests that each pass in
isolation while diverging.

## ADR-3 — `resolve_gate_verdict()` wraps `resolve_provider()`, and a config refusal is a named reason

**Decision.** The verdict function resolves the provider (not merely the opt-in cascade) and
catches the key-in-config `SystemExit`, mapping it to `disabled-via-config`.

**Rationale.** LESSON-392. Today the probe collapses that refusal to `0` and the *shell*
re-derives a reason; once the gate stops deriving reasons, Python must carry the mapping or
the information is lost. `disabled-via-config` is the honest label — the config is why
delegation is unavailable.

## ADR-4 — The reason heuristic is imprecise today, and this REQ must decide whether to preserve the imprecision ⚠️ **NEEDS RATIFICATION**

**Finding.** `_adlc_delegate_disabled_by_config` never reads `enabled`. It returns
"disabled-via-config" when *a config file exists AND a legacy key is exported*. Verified:

| Config | Legacy key | Reason today |
|---|---|---|
| `enabled: false` | absent | `not-opted-in` |
| `enabled: false` | present | `disabled-via-config` |

The same operator instruction produces two different reasons depending on an unrelated
variable. `disabled-via-config` is correct in both.

**The collision.** BR-4 freezes reason strings byte-identical. But `resolve_gate_verdict()`
has the three-state config `delegation_enabled()` already parses, so the natural
implementation emits `disabled-via-config` in **both** rows — improving the label and
breaking BR-4 as written.

**Options.**

- **(a) Replicate the heuristic in Python.** Satisfies BR-4 exactly. Requires porting
  "config exists AND legacy key present" into the verdict function — deliberately reproducing
  a known-wrong mapping, and re-introducing a legacy-key read on the Python side purely to
  emulate shell.
- **(b) Emit the accurate reason.** One row changes: `enabled: false` with no legacy key moves
  `not-opted-in` → `disabled-via-config`. Return codes are unchanged (both `1`), so no
  caller's control flow moves; only the label improves. Requires amending BR-4 to name this
  exception.
- **(c) Defer** — ship (a), file the mislabel as a bug, fix later. Cost: option (a)'s port is
  throwaway work, and the wrong label persists.

**Recommendation: (b),** with BR-4 amended to "byte-identical except the `enabled: false`
without-legacy-key case, which is corrected from `not-opted-in` to `disabled-via-config`". The
rc is unchanged, `delegate-pre-pass` accepts any of the frozen six verbatim, and
`check-delegation.sh` aggregates `mode` not `reason` — so no known consumer breaks. Option (a)
would port a bug across a rewrite whose stated purpose is removing a second source of truth.

**This is a spec amendment and is not `/architect`'s to make unilaterally.** Tasks are written
against (b); if the answer is (a), TASK-089 gains the heuristic port and TASK-091 gains a case
pinning the old label.

## ADR-5 — The legacy-key shell arm is removed in one change

**Decision.** Remove it with the rest of the authorizing arms rather than deprecating across a
release. Resolves REQ-603 OQ-2.

**Rationale.** It is an authorizing arm, so BR-1 requires its removal; a half-migrated gate is
the state this REQ exists to end. Consumer repos with a lagging vendored partial keep working —
an old gate's shell arms remain individually correct (REQ-603 BR-13's future-conditional
hazard) — and `/template-drift` is the signal that they should update.

## Lessons applied

| Lesson | Applied as |
|---|---|
| LESSON-392 | ADR-3 — the probe shares the real call's resolution; the single highest-risk regression in this REQ |
| LESSON-022 | `--print-gate` keeps imports lazy; it is a pre-API guard and must run without the SDK |
| LESSON-019 | Checked `tools/lint-skills` for guard rot: `DELEGATE_GATE_ANCHORS = ("ADLC_DISABLE_DELEGATE",)` and the sourcing literal both survive, because BR-2 keeps the veto and no SKILL.md changes. **No rot introduced** — verified, not assumed |
| LESSON-602 | Every new test proven load-bearing by reverting the arm it covers |
| LESSON-008 | `--print-gate` output is parsed by shell: reject any reason outside the frozen enum before use (BR-6 fail-closed) |
| LESSON-329 / LESSON-013 | Gate rewrite stays split-free and BSD-safe; no `\b` in `grep -E` |
| LESSON-011 | Env is frozen at fork, but the gate passes its own env to the child probe, so both layers observe the same values. No new exposure — noted so the next reader does not re-derive it |

## Proposed additions to `.adlc/context/architecture.md`

One paragraph under the delegation section: *the opt-in predicate has exactly one
implementation (`_common.resolve_gate_verdict`); the shell gate may withhold delegation
(no-binary, veto) but may never grant it.* This is the invariant BUG-205 and BUG-209 each
violated from a different direction, and it belongs in the durable context rather than only in
this REQ.
