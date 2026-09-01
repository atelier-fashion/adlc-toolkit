---
id: BUG-209
title: "`ADLC_DISABLE_DELEGATE=1` is inert in the delegate CLIs — the documented emergency stop lives only in the vendored shell gate, and a run with it set still transmits file contents"
status: resolved
severity: high
created: 2026-09-01
updated: 2026-09-01
component: "tools/delegate"
domain: "adlc"
stack: ["python", "shell"]
concerns: ["data-governance", "privacy", "correctness", "silent-failure", "test-coverage"]
tags: ["delegation", "kill-switch", "opt-out", "disable-delegate", "vendored-gate", "precedence", "third-party-transmission"]
introduced_by: []
attribution: none
---

<!--
attribution: none. The CLI-side arm never existed, so no merge introduced the defect —
there is no commit where the behavior changed, which is the shape BR-7 describes. `git
blame` on delegation_enabled() yields the BUG-205 rework (a3350f1), considered and
rejected: that commit reordered the opt-in cascade and is why the function is correct
about `enabled`; it did not remove a kill-switch arm, because there was never one to
remove. Blaming it would attribute an omission to the commit that most recently
improved the surrounding code.

Nearest relative is BUG-206 (462bebd, PR #144), which fixed exactly this class of defect
for `enabled` and stopped one variable short. That is a scope gap in a fix, not the
introduction of this defect, so it is not recorded as introduced_by either.
-->

## Description

`ADLC_DISABLE_DELEGATE=1` is the toolkit's emergency stop for third-party data
transmission. It is documented in three places as absolute:

- `tools/delegate/README.md:64` — "forces it off from the environment, **overriding
  everything including `ADLC_DELEGATE_ENABLED=1`**"
- `tools/delegate/claude-md-routing.txt:51` — "forces it off"
- the user-facing global `CLAUDE.md` — "forces it off ahead of all of it"

It was implemented only in `partials/delegate-gate.sh:163`. `delegation_enabled()` in
`tools/delegate/_common.py` — the single predicate both CLIs consult — never read the
variable. Setting it and running `adlc-read` printed the privacy notice, transmitted the
corpus to the configured endpoint, and returned a completion.

The shell gate is **vendored per repo**: skills source `.adlc/partials/delegate-gate.sh`
ahead of the toolkit copy. So a repo carrying a stale vendored gate, any direct CLI
invocation, and any caller that reaches the binary by another path all walked straight
past the emergency stop.

This is the defect BUG-206 named and fixed one variable short. Its own reasoning applies
verbatim — *a governance control cannot live only in a layer that gets copied around* —
and it added the CLI backstop for `enabled` only. The gap is sharper for this variable
than for the one that got fixed: `enabled` is steady-state configuration, while
`ADLC_DISABLE_DELEGATE` exists specifically to be reachable when something has already
gone wrong and the operator needs transmission to stop now.

Compounding it, BUG-206's own refusal message told the operator
"`ADLC_DISABLE_DELEGATE=1` forces it off regardless" — a claim that was false in the very
file that printed it.

## Reproduction Steps

With delegation enabled (`delegate.enabled: true`, or `ADLC_DELEGATE_ENABLED=1`):

1. `ADLC_DISABLE_DELEGATE=1 adlc-read --version` → reports `enabled: true`.
2. `ADLC_DISABLE_DELEGATE=1 adlc-read --paths VERSION --question "..."` → prints the
   `delegate: sending file contents...` notice, transmits, and returns model output.

Observed 2026-08-31 against `main` at 462bebd, immediately after BUG-206 merged.

## Expected Behavior

`ADLC_DISABLE_DELEGATE=1` disables delegation everywhere, outranking every opt-in arm
including `ADLC_DELEGATE_ENABLED=1`, and is reported as `enabled: false` by `--version` /
`--print-enabled`. No file contents leave the machine.

## Actual Behavior

The variable had no effect on either CLI. `--version` reported `enabled: true` and real
calls transmitted.

## Environment

- Platform: macOS (darwin 25.6.0), zsh executor, Python 3.9
- Version: adlc-toolkit 5.0.0, `main` at 462bebd

## Root Cause

A governance control implemented once, in the copied layer.

`delegation_enabled()` implemented a four-arm cascade (`ADLC_DELEGATE_ENABLED` → config
`enabled` → legacy key → default off) with no kill-switch arm. The only occurrence of the
string in `_common.py` was inside BUG-206's error-message text.

Two things kept it invisible for the toolkit's whole life:

1. **The shell side was tested; the Python side was not.**
   `partials/tests/delegate-gate.test.sh:114` asserts "ADLC_DISABLE_DELEGATE=1 beats
   everything" and passes. That green test covers the vendored copy — the layer whose
   staleness is the actual threat model — and none of the 499 Python tests referenced the
   variable. Coverage existed exactly where it was least load-bearing.

2. **The test fixture did not know the variable existed.** `_DELEGATE_VARS` in
   `test_resolve_provider.py`, whose docstring says it clears "every delegate/legacy
   var", omitted `ADLC_DISABLE_DELEGATE`. A developer with it exported in their shell
   would have gotten different results from the same suite — the fixture's guarantee was
   false, silently.

Worth separating from BUG-205 and BUG-206, which this sits between and resembles. BUG-205
was a precedence bug — the arms existed and were ordered wrong. BUG-206 was a layering
bug — the right answer computed in a layer that could be bypassed. This is a layering bug
whose arm was never written at all, which is why no reordering or backstop caught it: you
cannot mis-order a branch that does not exist.

## Resolution

Added the kill-switch arm as step 0 of `delegation_enabled()`, ahead of every opt-in arm,
matching `delegate-gate.sh`'s ordering. Matched the shell's exact-`"1"` test so the two
layers cannot disagree about what counts as set — a truthy-looking `"true"` or `"yes"`
disables in neither.

`require_delegation_enabled()` now names the switch when it is the cause, instead of
advising the operator to enable delegation they deliberately turned off. This mirrors the
gate's `disabled-via-env` / `not-opted-in` split, and removes the false claim the message
previously made about itself.

Added `ADLC_DISABLE_DELEGATE` to `_DELEGATE_VARS` so the fixture's stated guarantee is
true, and seven tests covering the Python side: the switch beating each opt-in arm
individually, beating all three at once (mirroring the shell case on equal terms), the
exact-`"1"` boundary, the `--version` report, and the refusal message naming itself.

Six of the seven fail against the unfixed cascade, verified by reverting the arm and
re-running. The seventh (`test_disable_requires_exactly_one`) passes in both directions
by design — it guards the boundary against an over-broad future match rather than the
absence being fixed here (LESSON-602 on vacuous exclusion tests).

## Files Changed

- `tools/delegate/_common.py` — kill-switch arm as step 0 of `delegation_enabled()`;
  `require_delegation_enabled()` distinguishes `disabled-via-env`; docstring records the
  precedence and why the arm belongs in the uncopied layer
- `tools/delegate/tests/test_resolve_provider.py` — `ADLC_DISABLE_DELEGATE` added to
  `_DELEGATE_VARS`; seven BUG-209 tests
- `CHANGELOG.md` — Unreleased/Fixed entry
- `.adlc/bugs/BUG-209-kill-switch-inert-in-the-delegate-clis.md` — this report

## Notes

The one-line form: **an emergency stop implemented only in the layer that gets copied is
not an emergency stop — and the test that proves it works in that layer is the reason
nobody looks.**

Severity `high`, matching BUG-205, for the same reason: silent and outward-facing. The
operator takes the documented action to halt transmission, receives no error, and
transmission continues. It is not `critical` only because two working controls remain —
`delegate.enabled: false` (correct since BUG-205) and, for skills routing through a
current gate, the vendored copy.

Follow-up worth its own artifact: the shell gate and `delegation_enabled()` now encode
the same five-arm precedence in two languages, verified by two disjoint test suites that
were unequal for the toolkit's entire life. This fix equalizes the suites but not the
duplication. A single Python resolver the gate shells out to — it already refuses to
parse config in shell (REQ-515 ADR-3) — would make a repeat structurally impossible
rather than merely tested for. That is a design change, deliberately not folded into a
governance fix.
