---
id: REQ-603
title: "Single-source the delegation opt-in predicate — the gate asks, Python answers"
status: draft
deployable: true
created: 2026-09-01
updated: 2026-09-01
component: "adlc/delegate-gate"
domain: "adlc"
stack: [bash, python, claude-skills]
concerns: [data-governance, privacy, correctness, structural-enforcement, test-coverage]
tags: [delegation, opt-in, kill-switch, precedence, vendored-partial, single-source-of-truth, gate-reason]
---

## Description

The delegation opt-in predicate is implemented **twice** — once in shell
(`partials/delegate-gate.sh`) and once in Python (`_common.delegation_enabled`) — and
verified by two disjoint test suites. Every arm of the precedence cascade exists in both
languages except the config arm, which the gate already delegates to Python:

| Precedence arm | Shell | Python |
|---|---|---|
| `ADLC_DISABLE_DELEGATE=1` | `delegate-gate.sh:163` | `delegation_enabled` (added by BUG-209) |
| `ADLC_DELEGATE_ENABLED=1` | `_adlc_delegate_opted_in` step 1 | `delegation_enabled` |
| config `delegate.enabled` | **defers to `--print-enabled`** | `delegation_enabled` |
| legacy key continuity | `_adlc_delegate_opted_in` step 3 | `_legacy_key_present` |

This is not a tidiness complaint. The duplication has already produced **two
data-governance defects**, one per arm that shell reimplements:

- **BUG-205** — the config arm was a pure-shell fast path that avoided a fork. Correct
  for `enabled: true` (every arm agrees) and wrong for `enabled: false` (the arms
  disagree and the cheap one won), so an operator's written opt-out was silently
  overridden and file contents were transmitted. The fix moved that one arm behind the
  Python probe; `delegate-gate.sh` now records that the fork is "the correct price for a
  governance decision".
- **BUG-209** — `ADLC_DISABLE_DELEGATE` existed in shell and **nowhere** in Python, so
  both CLIs ignored the documented emergency stop entirely. A run with it set transmitted
  and returned a completion.

Each fix corrected the arm that had just failed. Neither removed the condition that lets
the next one drift: two implementations checked by two suites can disagree, and nothing
structural stops them.

BUG-209 shows the shape. `partials/tests/delegate-gate.test.sh` asserts
`"ADLC_DISABLE_DELEGATE=1 beats everything"` and passes, while the CLIs ignored the
variable entirely — coverage of the copied layer standing in for coverage of the real
resolver. Precision matters about how long that lasted: that harness was added by
**BUG-205 on 2026-08-31** (a3350f1), one day before BUG-209 was found, so it did not
provide years of false comfort. The durable defect was the *absence* of Python coverage,
not the presence of shell coverage. What the new harness demonstrates is the trap's
shape going forward — a governance assertion can be green in the vendored layer while
the uncopied layer has no such arm at all, and nothing in the repo compares the two.

The threat model makes the shell copy the wrong home for the answer. `delegate-gate.sh`
is **vendored per repo**: skills source `.adlc/partials/delegate-gate.sh` ahead of the
toolkit copy, so a consumer repo runs whatever version it vendored, however old.
`_common.py` is reached through the `~/bin` wrapper and is not copied. A governance
control whose only implementation is in the copied layer is a control that a stale vendor
silently removes — which is what `/template-drift` exists to detect and cannot be relied
on to have run.

This REQ makes Python the sole resolver and reduces the gate to: resolve the binary, ask,
map the answer to a return code.

### The cost, measured — and smaller than it first appears

The objection to full deferral is the fork. Measured on this machine:
`adlc-read --print-enabled` costs **~23ms** per call, and the gate fires per delegating
step across `/spec`, `/wrapup`, `/analyze`, `/architect`, `/proceed` Phase 5, multiplied
by REQs in flight under `/sprint`.

But the gate **already forks whenever a config file exists** (BUG-205's fix), and
`install.sh:168` scaffolds `~/.claude/adlc/config.yml` on every install since REQ-519. So
the population that pays a *new* fork is only installs with **no config file at all** —
precisely the pre-config legacy population BR-11's continuity exception was written for,
and the population that by definition has never been configured. The steady-state cost
for a current install is **zero additional forks**, not one per gate call.

That reframes the tradeoff: this is not "buy safety with latency" but "stop paying for a
fast path that only serves un-migrated installs and has caused two governance defects."

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| GateVerdict | `enabled` | boolean | the full cascade's answer, including the kill switch |
| GateVerdict | `reason` | string | enum: `ok` \| `disabled-via-env` \| `disabled-via-config` \| `not-opted-in`; never empty |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `verdict_requested` | the gate needs an opt-in answer and the binary resolved | none |
| `verdict_returned` | the probe exits 0 with a parseable verdict | `enabled`, `reason` |
| `verdict_unavailable` | probe non-zero, unparseable, or empty | none — gate fails closed |

## Business Rules

- [ ] BR-1: `_common.delegation_enabled()` is the **single** resolver for every arm of the cascade. `delegate-gate.sh` contains no arm that re-decides opt-in — no `ADLC_DELEGATE_ENABLED` test, no legacy-key test, no `ADLC_DISABLE_DELEGATE` test. Deleting an arm from Python must change the gate's behavior; if it does not, the arm is still duplicated.
- [ ] BR-2: the probe reports **both** the verdict and the reason, because the gate's `ADLC_DELEGATE_GATE_REASON` values are a documented contract with downstream consumers — `partials/delegate-gate.md:59` tabulates them and `tools/delegate/check-delegation.sh` aggregates the telemetry `reason` column. A verdict-only probe would force the gate to re-derive the reason from the same env and config it was just told not to read, reintroducing the duplication in a second form. The existing `--print-enabled` contract (prints `1`/nothing) is **preserved unchanged** for any caller that already depends on it; the reason-bearing form is additive.
- [ ] BR-3: the reason strings and the 0/1/2 return-code shape are byte-identical to today's. This REQ changes *where* the answer is computed, never *what* it is. Any change to the reason vocabulary is a separate REQ — telemetry rows already in `~/Library/Logs/adlc-skill-telemetry.log` must stay comparable across the upgrade.
- [ ] BR-4: `no-binary` (return 2) is still decided in shell, before any probe, because it is the one question the probe cannot answer — an unresolvable binary cannot be asked whether delegation is enabled. This is not an exception to BR-1: binary resolution is not an opt-in arm.
- [ ] BR-5: the gate fails **closed**. A probe that exits non-zero, prints nothing, prints an unparseable verdict, or names a reason outside the enum yields *not delegated*. Preserves the existing rule that a gate which cannot establish consent must not assume it, and keeps the `_probe_rc=$?`-immediately-after-substitution discipline that BUG-205's fix introduced.
- [ ] BR-6: exactly **one** probe invocation per gate call. The gate must not fork once for the verdict and again for the reason — two forks would double the cost this REQ is arguing is acceptable, and two invocations could straddle an env change and report an incoherent pair.
- [ ] BR-7: `partials/tests/delegate-gate.test.sh` is rewritten to assert **delegation**, not re-assert the cascade. Its cases become: the gate returns what the probe said; the gate fails closed on a broken probe; the gate returns 2 without probing when the binary is missing. Cascade semantics — which arm wins — are asserted once, in the Python suite. Keeping the shell suite's current cases would preserve the exact condition this REQ removes: a green shell assertion standing in for coverage of the real resolver (BUG-209's failure mode).
- [ ] BR-8: the Python suite gains the cases the shell suite is giving up, so total cascade coverage does not decrease. Verified by the BUG-209 method: revert an arm and confirm the Python suite fails (informed by LESSON-602 on vacuous exclusion tests).
- [ ] BR-9: `--print-enabled`'s own resolution must not be self-referential. The probe runs the full predicate including the kill switch, so `ADLC_DISABLE_DELEGATE=1` makes the probe report *disabled* rather than making it refuse to run. `require_delegation_enabled()` must not gate the probe itself, or the gate can never learn why it was refused.
- [ ] BR-10: all shell stays BSD- and zsh-safe: no `\b` in `grep -E` (LESSON-013), no bare `$<digit>`, no `status` variable, no unquoted word-splitting (LESSON-329, LESSON-335).
- [ ] BR-11: no new skill directory. This touches `partials/delegate-gate.sh`, `partials/delegate-gate.md`, `tools/delegate/_common.py`, the two CLIs' flag surface, and both test suites (conventions: don't create skills casually).
- [ ] BR-12: `/template-drift` must flag a vendored `.adlc/partials/delegate-gate.sh` that still carries the removed shell arms. A consumer repo that upgrades the toolkit but not its vendored partial would otherwise keep resolving opt-in locally — the exact staleness this REQ exists to defuse — and would do so while the toolkit believes the gate defers. The partial is already reported as `stale` on drift; this rule is that the check must not be satisfiable by a copy predating this REQ.

## Acceptance Criteria

- [ ] `grep -E 'ADLC_DELEGATE_ENABLED|ADLC_DISABLE_DELEGATE|MOONSHOT_API_KEY|KIMI_API_KEY' partials/delegate-gate.sh` returns no *decision* sites — any surviving mention is documentation or pass-through, not a branch that decides opt-in.
- [ ] Removing the `ADLC_DISABLE_DELEGATE` arm from `delegation_enabled()` causes the **shell** gate suite to fail — proving the gate now depends on Python for that arm rather than deciding it independently. This is the regression test for BUG-209's root cause.
- [ ] With `ADLC_DISABLE_DELEGATE=1` and every opt-in signal set (`ADLC_DELEGATE_ENABLED=1`, `delegate.enabled: true`, a legacy key exported), the gate returns `1 disabled-via-env` and both CLIs refuse.
- [ ] With `delegate.enabled: false` and a legacy key exported, the gate returns `1 disabled-via-config` — BUG-205's case, unchanged.
- [ ] With no config file and a legacy key exported, the gate returns `0 ok` — BR-11 continuity, unchanged.
- [ ] A probe that exits 0 but prints garbage, and a probe that prints a valid verdict then exits non-zero, both yield not-delegated.
- [ ] `adlc-read --print-enabled` with no arguments still prints `1`/nothing exactly as before — verified against a caller written before this REQ.
- [ ] The gate forks at most once per call, verified by counting probe invocations in a run with an instrumented `ADLC_READ_BIN`.
- [ ] `sh partials/tests/run.sh` passes under bash and zsh; the full Python suite passes; neither suite's cascade coverage decreased (BR-8).
- [ ] Telemetry rows written after the change carry the same `reason` values as rows written before, for the same conditions.

## External Dependencies

- None. No new packages; the probe seam and the `~/bin` wrapper already exist.

## Assumptions

- **The ~23ms probe cost is representative.** Measured on this machine (macOS, Python 3.9, warm filesystem) as 10 sequential `--print-enabled` calls in 0.228s. A cold cache, a slower disk, or a Python with heavier site-packages will differ. Re-measure before treating the "zero additional forks for a configured install" conclusion as settled — it depends on the fork already happening today, not on its absolute cost.
- **`install.sh` scaffolds a config on every current install** (`install.sh:168`, REQ-519), so the no-config population is legacy-only and shrinking. If that ever stops being true, the marginal-cost argument weakens and BR-6's one-probe rule becomes load-bearing rather than merely tidy.
- **No caller depends on `ADLC_DELEGATE_GATE_REASON` values outside the documented enum.** `check-delegation.sh` aggregates them and `agents/delegate-pre-pass.md` passes `gateReason` through verbatim (per BUG-205's changes). A consumer skill matching on a reason string this REQ does not change would be unaffected, but the assumption is untested outside this repo.
- **The gate is always sourced, never re-implemented inline by a skill.** `partials/delegate-gate.md:140` documents a lint check for skills that mention `ADLC_DISABLE_DELEGATE` without sourcing the partial, which suggests inline copies have occurred before. If a skill open-codes the cascade, this REQ does not reach it — `tools/lint-skills` is the enforcement surface, and BR-12's drift check is the detection one.

## Open Questions

- **OQ-1: probe flag shape.** A new `--print-gate` emitting `<enabled> <reason>` on one line, versus extending `--print-enabled` with a second field behind a flag. One line keeps BR-6's single fork trivial; a second flag risks callers combining them and forking twice. Leaning to a new flag, with `--print-enabled` frozen as-is for compatibility (BR-2).
- **OQ-2: whether the gate should cache a verdict within a pipeline phase.** Would cut the no-config population's new cost to one fork per phase, but caches a governance decision across a window in which the operator might set the kill switch precisely because something is going wrong. Leaning **no** — the measured steady-state cost is already zero for configured installs, so the cache buys little and weakens the one control that must work under duress.
- **OQ-3: whether `_legacy_key_present()` should move behind the same seam for the no-config path,** or whether the gate may keep a shell existence check for the case where no config file exists and no probe is therefore strictly required. Keeping it would preserve today's zero-fork path for legacy installs but leaves one duplicated arm — the shape this REQ exists to eliminate. Leaning to full deferral; the legacy population is the one least able to notice a divergence.
