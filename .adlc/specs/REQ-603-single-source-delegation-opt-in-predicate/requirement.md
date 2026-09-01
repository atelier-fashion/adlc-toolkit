---
id: REQ-603
title: "Single-source the delegation authorization arms — the gate may veto, only Python may authorize"
status: approved
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
verified by two disjoint test suites. Every arm of the cascade REQ-515 defined exists in
both languages except the config arm, which BUG-205 already moved behind the Python probe:

| Precedence arm | Kind | Shell | Python |
|---|---|---|---|
| `ADLC_DISABLE_DELEGATE=1` | **veto** | `delegate-gate.sh:163` | `delegation_enabled` (added by BUG-209) |
| `ADLC_DELEGATE_ENABLED=1` | **authorizing** | `_adlc_delegate_opted_in` step 1 | `delegation_enabled` |
| config `delegate.enabled` | either | **defers to `--print-enabled`** | `delegation_enabled` |
| legacy key continuity | **authorizing** | `_adlc_delegate_opted_in` step 3 | `_legacy_key_present` |

This is not a tidiness complaint. The duplication has already produced **two
data-governance defects**, one per arm that shell decides:

- **BUG-205** — the config arm was a pure-shell fast path that avoided a fork. Correct for
  `enabled: true` (every arm agrees) and wrong for `enabled: false` (the arms disagree and
  the cheap one won), so an operator's written opt-out was silently overridden and file
  contents were transmitted. The fix moved that arm behind the probe; `delegate-gate.sh`
  now records that the fork is "the correct price for a governance decision".
- **BUG-209** — `ADLC_DISABLE_DELEGATE` existed in shell and **nowhere** in Python, so both
  CLIs ignored the documented emergency stop entirely. A run with it set transmitted and
  returned a completion.

Each fix corrected the arm that had just failed. Neither removed the condition that lets
the next one drift: two implementations checked by two suites can disagree, and nothing
structural stops them.

BUG-209 shows the shape. `partials/tests/delegate-gate.test.sh` asserts
`"ADLC_DISABLE_DELEGATE=1 beats everything"` and passes, while the CLIs ignored the
variable entirely — coverage of the copied layer standing in for coverage of the real
resolver. Precision about how long that lasted: the harness was added by **BUG-205 on
2026-08-31** (a3350f1), one day before BUG-209 was found, so it did not provide years of
false comfort. The durable defect was the *absence* of Python coverage, not the presence of
shell coverage. What it demonstrates is the trap's shape going forward — a governance
assertion can be green in the vendored layer while the uncopied layer has no such arm at
all, and nothing in the repo compares the two.

The threat model makes the shell copy the wrong home for the answer. `delegate-gate.sh` is
**vendored per repo**: skills source `.adlc/partials/delegate-gate.sh` ahead of the toolkit
copy, so a consumer repo runs whatever version it vendored, however old. `_common.py` is
reached through the `~/bin` wrapper and is not copied.

### The rule is about authorization, not duplication

An earlier draft of this REQ said the gate must contain *no arm that re-decides opt-in*.
That is too broad, and adversarial review showed it makes the emergency stop the most
expensive path in the gate — perverse for the one control that must work when something has
already gone wrong.

The arms are not equally dangerous to duplicate, because they do not have equal power:

- A **veto** arm can only ever return *disabled*. Duplicating `ADLC_DISABLE_DELEGATE` in
  shell and Python cannot produce a wrong *enabled* on any input: the copies either both
  vote disable, or one abstains and the other still vetoes. Duplication is **redundancy** —
  strictly safer than one copy, which is exactly what BUG-209 proved when the Python copy
  was missing.
- An **authorizing** arm can return *enabled*. A stale shell copy that short-circuits on
  `ADLC_DELEGATE_ENABLED` or a legacy key wrongly authorizes past a Python arm it does not
  know about. Duplication is **divergence risk** — and that is precisely BUG-205's shape,
  where shell's cheap arm beat the operator's written config.

So the rule this REQ imposes is: **the gate may veto; only Python may authorize.**

### Cost, measured

The objection to deferral is the fork. Measured on this machine (macOS, Python 3.9, warm),
50 iterations per case:

| | |
|---|---|
| bare interpreter startup | 9.9 ms |
| `adlc-read --print-enabled` | **21.0 ms** |
| gate calls per skill run | **1–2** (`proceed` 1, `wrapup` 1, `spec` 2, `analyze` 2), plus one per repo per REQ under `/sprint` via `delegate-pre-pass` |
| median delegated step | **104,000 ms** (max 2,133,000 ms; n=181 rows carrying a numeric `duration_ms`, of 212 total) |

Worst case is 2 forks × 21 ms = 42 ms against a median 104-second step: **0.04%**. Roughly
10 ms of the 21 is irreducible CPython startup; `_common.py` imports five stdlib modules
and has little left to trim. There is no general performance problem to solve here.

Under the veto rule the fork profile is:

| Path | Today | This REQ |
|---|---|---|
| `ADLC_DISABLE_DELEGATE=1` | 0 forks | **0 forks** — unchanged |
| `ADLC_DELEGATE_ENABLED=1` | 0 forks | 1 fork |
| config file present | 1 fork | 1 fork — unchanged |
| no config + legacy key | 0 forks | 1 fork |

The emergency stop stays exactly as fast as it is today. The two paths that gain a fork are
both authorizing arms, which is the trade this REQ exists to make.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| ProbeVerdict | `enabled` | boolean | the probe's answer over every arm it owns, veto included |
| ProbeVerdict | `reason` | string | enum: `ok` \| `disabled-via-env` \| `disabled-via-config` \| `not-opted-in` |

`ProbeVerdict` is deliberately **not** the gate's verdict. The gate emits two further
reasons the probe never produces: `no-binary` (BR-5 keeps it in shell — an unresolvable
binary cannot be asked anything) and `unset` (`delegate-gate.sh:53`, the pre-call initial
value). The gate's reason vocabulary is the union of the four above with those two, and
BR-4 freezes all six.

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `veto_applied` | `ADLC_DISABLE_DELEGATE=1` seen in shell | none — gate returns `1 disabled-via-env` without probing |
| `verdict_requested` | no veto, binary resolved | none |
| `verdict_returned` | probe exits 0 with a parseable verdict | `enabled`, `reason` |
| `verdict_unavailable` | probe non-zero, unparseable, or empty | none — gate fails closed |

## Business Rules

- [ ] BR-1: `delegate-gate.sh` contains **no authorizing arm**. It must not test `ADLC_DELEGATE_ENABLED`, `MOONSHOT_API_KEY`, or `KIMI_API_KEY`, and must not read the config file. Every path on which the gate concludes *delegated* passes through `_common.delegation_enabled()`. Deleting an authorizing arm from Python must change the gate's behavior; if it does not, that arm is still duplicated.
- [ ] BR-2: the `ADLC_DISABLE_DELEGATE` **veto stays in shell**, checked before any probe, **and** stays in Python. This is the one deliberate duplication, and it is permitted only under a stated condition: **the Python veto must recognise at least every input the shell veto recognises.** Under that condition the copies can only agree or abstain, never contradict — a shell veto that abstains is still caught downstream by the probe. Both currently test the literal `"1"` and must continue to test the same input set; widening one alone is the defect this rule exists to prevent. The direction is asymmetric and only one way is safe. A *narrower* shell predicate is harmless. A *broader* one — shell accepting `true`/`yes` while Python does not — makes the gate report `disabled-via-env` while a direct CLI call transmits, which is BUG-209's failure reintroduced through this very exemption. Subject to that, the duplication preserves today's zero-fork emergency stop and is defence in depth, not divergence: BUG-209 is the proof that one copy is insufficient.
- [ ] BR-3: the probe reports **both** verdict and reason, because `ADLC_DELEGATE_GATE_REASON` is a documented contract with downstream consumers — `partials/delegate-gate.md:59` tabulates the values and `agents/delegate-pre-pass.md:34-35,122` requires `gateReason` **verbatim** in its structured output. Note what is *not* a consumer: `tools/delegate/check-delegation.sh` aggregates the telemetry **`mode`** column (`:76-79`), not `reason`, and the telemetry `reason` field is a skill-level outcome vocabulary distinct from the gate's — over all 212 telemetry rows it carries `no-flag` (27) and `api-error` (24), which are not gate reasons, and carries `disabled-via-env` **zero** times. The two must not be conflated. A verdict-only probe would force the gate to re-derive the reason from the config it was just told not to read, reintroducing the duplication in a second form. The existing `--print-enabled` contract (prints `1`/nothing) is **preserved unchanged**; the reason-bearing form is additive.
- [ ] BR-4: all six gate reason strings and the 0/1/2 return-code shape are byte-identical to today's, **with one named exception** (architecture ADR-4, ratified 2026-09-01): a config carrying an explicit `enabled: false` **with no legacy key exported** reports `disabled-via-config`, where today it reports `not-opted-in`. That divergence is a correction, not a regression. `_adlc_delegate_disabled_by_config` never reads `enabled` — it returns `disabled-via-config` only when a config file exists **and** a legacy key happens to be exported — so the same written instruction produces two different labels depending on an unrelated variable. `disabled-via-config` is the honest label in both cases, and `resolve_gate_verdict()` has the three-state config needed to say so. The **return code is unchanged** (`1` either way), so no caller's control flow moves; only the label improves. Every other reason, on every other input, stays byte-identical. This REQ otherwise changes *where* the answer is computed, never *what* it is. Any change to the reason vocabulary is a separate REQ — telemetry rows already in `~/Library/Logs/adlc-skill-telemetry.log` must stay comparable across the upgrade.
- [ ] BR-5: `no-binary` (return 2) is decided in shell, before any probe, because it is the one question the probe cannot answer. This is not an exception to BR-1: binary resolution is not an authorizing arm — it can only withhold delegation, never grant it. **It is resolved before BR-2's veto**, preserving today's order: with the binary unresolvable and `ADLC_DISABLE_DELEGATE=1` both true, the gate returns `2 no-binary`, not `1 disabled-via-env`. Both are pre-probe, so the order would otherwise be ambiguous, and inverting it would silently break BR-4's return-code guarantee on a path neither rule otherwise covers.
- [ ] BR-6: the gate fails **closed**. A probe that exits non-zero, prints nothing, prints an unparseable verdict, or names a reason outside the enum yields *not delegated*. Preserves the rule that a gate which cannot establish consent must not assume it, and keeps the `_probe_rc=$?`-immediately-after-substitution discipline BUG-205's fix introduced.
- [ ] BR-7: **at most one** probe invocation per gate call. The gate must not fork once for the verdict and again for the reason — two invocations could straddle an env change and report an incoherent pair. Zero invocations is correct and expected on the BR-2 veto path and the BR-5 no-binary path.
- [ ] BR-8: `partials/tests/delegate-gate.test.sh` asserts the gate's **own** responsibilities and stops re-asserting the cascade. Its cases are: (a) the gate returns what the probe said, for each verdict/reason pair; (b) the gate fails closed on a broken probe; (c) the gate returns 2 without probing when the binary is missing; (d) **the veto short-circuits — `ADLC_DISABLE_DELEGATE=1` yields `1 disabled-via-env` with zero probe invocations.** Case (d) is retained deliberately and is not a cascade assertion: under BR-2 the veto is the gate's own behavior, so this suite is its correct home. Cases asserting which *authorizing* arm wins move to the Python suite.
- [ ] BR-9: the Python suite gains every cascade case the shell suite gives up, so total coverage does not decrease. Verified by the BUG-209 method — revert an arm, confirm the Python suite fails (informed by LESSON-602 on vacuous exclusion tests).
- [ ] BR-10: the probe must not be self-gated. `--print-enabled` and the reason-bearing form run the full predicate and **report** `disabled`; they must never route through `require_delegation_enabled()` and refuse. A refusing probe exits non-zero, the gate applies BR-6, and a machine whose true state is `disabled-via-env` is recorded as `not-opted-in` — breaking BR-4 silently.
- [ ] BR-11: all shell stays BSD- and zsh-safe: no `\b` in `grep -E` (LESSON-013), no bare `$<digit>`, no `status` variable, no unquoted word-splitting (LESSON-329, LESSON-335).
- [ ] BR-12: no new skill directory. This touches `partials/delegate-gate.sh`, `partials/delegate-gate.md`, `tools/delegate/_common.py`, the two CLIs' flag surface, and both test suites (conventions: don't create skills casually).
- [ ] BR-13: `/template-drift` must flag a vendored `.adlc/partials/delegate-gate.sh` that still carries the removed authorizing arms. The justification is **future-conditional, not present-tense**: an old vendored gate paired with current Python agrees on every input today (its shell arms remain individually correct), so nothing diverges immediately — it simply fails to gain the single-source property. The hazard is the next arm: the moment a later REQ adds an authorizing arm to Python, a stale gate that short-circuits on `ADLC_DELEGATE_ENABLED` bypasses it, silently. The partial is already reported `stale` on drift; this rule is that the check must not be satisfiable by a copy predating this REQ.

## Acceptance Criteria

- [ ] `delegate-gate.sh` contains no `if` or `case` construct whose condition references `ADLC_DELEGATE_ENABLED`, `MOONSHOT_API_KEY`, or `KIMI_API_KEY`, and no read of the config file path. Mechanically decidable by grep over the file's conditionals; mentions in comments or documentation do not count. (BR-1)
- [ ] `delegate-gate.sh` **does** contain the `ADLC_DISABLE_DELEGATE` veto, positioned after binary resolution and before any probe invocation. (BR-2, BR-5)
- [ ] **Both veto layers agree over a shared input vector.** For each of `1`, `0`, `` (empty), `true`, `yes`, `2`, `01`, and unset, the shell veto and `delegation_enabled()` reach the same disabled/not-disabled conclusion — asserted by a single test driving both layers over the same list, so that widening one alone fails. This is the cross-layer check whose absence makes BR-2's exemption unsafe; a per-layer test cannot substitute, because each passes in isolation while they diverge. (BR-2)
- [ ] With `ADLC_DISABLE_DELEGATE=1` and every authorizing signal set (`ADLC_DELEGATE_ENABLED=1`, `delegate.enabled: true`, a legacy key exported), the gate returns `1 disabled-via-env`, **zero probe invocations occur**, and both CLIs refuse. (BR-2, BR-7)
- [ ] Removing the `ADLC_DELEGATE_ENABLED` arm from `delegation_enabled()` changes the gate's verdict for an install whose only opt-in signal is that variable — proving the gate no longer decides it. (BR-1)
- [ ] Removing the `ADLC_DISABLE_DELEGATE` arm from `delegation_enabled()` causes the **Python** suite to fail and `require_delegation_enabled()` to **stop refusing** on the direct-CLI path, while the gate's veto still holds — the BUG-209 regression, with each layer's responsibility asserted in its own suite. The criterion is the guard's refusal, not an actual transmission: verifying this must never require sending file contents to the endpoint, which would put the governance violation inside the suite that exists to prevent it, and would break the hermetic-test posture besides. (BR-2, BR-9)
- [ ] With `delegate.enabled: false` and a legacy key exported, the gate returns `1 disabled-via-config` — BUG-205's case, unchanged. (BR-4)
- [ ] With no config file and a legacy key exported, the gate returns `0 ok` — REQ-515 BR-11 continuity, unchanged. (BR-4)
- [ ] With the binary unresolvable, the gate returns `2 no-binary` and **zero probe invocations occur**, including when `ADLC_DISABLE_DELEGATE=1` is also set. (BR-5, BR-7)
- [ ] A probe that exits 0 but prints garbage, a probe that prints a valid verdict then exits non-zero, and a probe naming a reason outside the enum all yield not-delegated. (BR-6)
- [ ] Every gate call performs at most one probe invocation, counted with an instrumented `ADLC_READ_BIN` across all four fork-profile paths in the Description. (BR-7)
- [ ] With `ADLC_DISABLE_DELEGATE=1`, the probe invoked directly **exits 0 and reports disabled** rather than exiting non-zero with a refusal message. (BR-10)
- [ ] `adlc-read --print-enabled` with no arguments still prints `1`/nothing exactly as before, verified against a **frozen fixture copy of the pre-REQ `_adlc_delegate_opted_in`** — the only in-repo caller of that flag today — rather than against the rewritten gate, which will have moved to the reason-bearing form and so cannot witness the old contract. (BR-3)
- [ ] Coverage did not decrease, measured by the BR-9 method rather than asserted: for **each** arm in `delegation_enabled()` — veto, env opt-in, config, legacy key — reverting that arm alone causes at least one Python test to fail. Enumerate the four results. (BR-9)
- [ ] `delegate-gate.test.sh` contains a case for each of BR-8's four classes (a) probe pass-through, (b) fail-closed, (c) no-binary without probing, (d) veto short-circuit — and contains **no** case whose setup asserts which *authorizing* arm wins. Decidable by inspecting the suite's case list: a case that sets `ADLC_DELEGATE_ENABLED` or a legacy key without also setting the veto is a cascade assertion and must have moved to the Python suite. (BR-8)
- [ ] `git diff --name-only main...HEAD` adds no `*/SKILL.md` path — no new skill directory was created. (BR-12)
- [ ] `sh partials/tests/run.sh` passes under bash and zsh; the full Python suite passes. (BR-11)
- [ ] `/template-drift` reports a vendored `delegate-gate.sh` predating this REQ as stale, verified with a fixture copy carrying the old authorizing arms. (BR-13)
- [ ] For each of the six gate reasons, the value exported in `ADLC_DELEGATE_GATE_REASON` after the change is byte-identical to the value exported before, under the same conditions. Asserted against the gate's own output, **not** against the telemetry `reason` column, which is a different vocabulary (BR-3). (BR-4)
- [ ] `agents/delegate-pre-pass.md` continues to receive `gateReason` verbatim, with no value outside the frozen six. (BR-3, BR-4)
- [ ] **The ADR-4 correction, and only it, diverges.** A config with `enabled: false` and **no** legacy key exported reports `1 disabled-via-config`, where the pre-REQ gate reported `1 not-opted-in`. The return code is unchanged. Every other (input, reason) pair in the six-reason matrix is byte-identical to the pre-REQ gate, asserted exhaustively rather than spot-checked — a single corrected row is only defensible if nothing else moved with it. (BR-4)

## Out of Scope

- **Changing the gate's reason vocabulary.** BR-4 freezes all six values; adding, renaming, or splitting one is a separate REQ.
- **Changing the telemetry `reason` field.** A different vocabulary in a different layer (BR-3). Splitting `api-error`, which BUG-208 noted is overloaded, is out of scope here and belongs to whatever REQ takes up telemetry.
- **Changing which skills delegate, or what they delegate.** The delegating call sites are REQ-417's territory; this REQ changes only how the gate reaches its verdict.
- **Caching the verdict.** Considered and rejected on measurement: at 1–2 gate calls per skill run, a cache saves at most one 21 ms fork, while adding a window in which a governance decision is stale.
- **Reducing probe cost.** ~10 ms of the 21 ms is CPython startup and the module imports five stdlib modules. Optimizing 0.04% of a step into 0.02% is not a requirement.
- **New drift-detection tooling.** BR-13 asserts a property of the existing `/template-drift`; building new machinery for it is out of scope.
- **Moving `no-binary` resolution into Python.** BR-5 keeps it in shell permanently; it is not a deferred cleanup.

## External Dependencies

- None. No new packages; the probe seam and the `~/bin` wrapper already exist.

## Assumptions

- **The measured costs are representative.** 21 ms per probe and a 104-second median step were measured on this machine (macOS, Python 3.9, warm filesystem; 50 iterations; telemetry n=181 of 212 rows, the remainder being fallback rows with no numeric duration). A cold cache or slower disk will differ. The conclusion is robust to a large error — the argument needs the probe to be ≪ the step, and it is by ~5000×.
- **Gate-call frequency is 1–2 per skill run, plus one per repo per REQ under `/sprint`.** The first figure counts `adlc_delegate_gate_check` call sites in `proceed` (1), `wrapup` (1), `spec` (2), and `analyze` (2). It is not the whole picture: `agents/delegate-pre-pass.md` also runs the gate and is dispatched **per repo** for the `/sprint --workflow` Phase-5 panel, so a sprint's gate calls scale with repos × REQs rather than staying constant. The cost conclusion survives that fan-out with room to spare — even 50 pre-pass invocations add ~1.05 s across a batch whose individual steps median 104 s — but any re-derivation must count the agent call site, not just the four skills.
- **No caller depends on `ADLC_DELEGATE_GATE_REASON` values outside the documented enum.** `check-delegation.sh` aggregates them and `agents/delegate-pre-pass.md` passes `gateReason` through verbatim. Untested outside this repo.
- **The gate is always sourced, never re-implemented inline by a skill.** `partials/delegate-gate.md:140` documents a lint check for skills mentioning `ADLC_DISABLE_DELEGATE` without sourcing the partial, which suggests inline copies have occurred. If a skill open-codes the cascade this REQ does not reach it — `tools/lint-skills` is the enforcement surface, BR-13's drift check the detection one.
- **A veto arm cannot be made to authorize by a future change.** BR-2's safety argument depends on `ADLC_DISABLE_DELEGATE` remaining strictly disabling. If anyone ever gives it an "off means force-on" reading, the duplication becomes a divergence risk and BR-2 must be revisited.

## Open Questions

- **OQ-1: probe flag shape.** A new `--print-gate` emitting `<enabled> <reason>` on one line, versus extending `--print-enabled` with a second field behind a flag. One line keeps BR-7's single fork trivial; a second flag risks callers combining them and forking twice. Leaning to a new flag, with `--print-enabled` frozen for compatibility (BR-3).
- **OQ-2: whether `_legacy_key_present()`'s shell copy is removed in the same change or deprecated across one release.** It is an authorizing arm, so BR-1 requires its removal; the question is sequencing for consumer repos whose vendored gate lags. Leaning to remove in one change and rely on BR-13's drift signal, since a half-migrated gate is the state this REQ is trying to end.
