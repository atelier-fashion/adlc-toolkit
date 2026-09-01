# /adversary — REQ-603

Target: `REQ-603` (resolved from the literal argument `first`, which was an answer to a
prior either/or, not an artifact). Type: **spec**. Read at full fidelity; target unmodified.

Venue: **single-context degradation** — lenses run inline rather than via the `adversary`
agent, per a standing instruction not to spawn agents unrequested. Same lenses.

Verdict: **found problems** — 5 findings survived refutation.

---

## F1 — The cost argument, which is the REQ's load-bearing justification, is false for two populations

- **severity**: major
- **confidence**: high (verified empirically)

The Description claims a configured install pays "**zero additional forks**", with only the
no-config legacy population paying a new one. That is wrong. Two more populations pay:

1. **`ADLC_DELEGATE_ENABLED=1` exported.** `_adlc_delegate_opted_in` step 1 returns before
   reaching the probe at step 2.
2. **`ADLC_DISABLE_DELEGATE=1` set.** `adlc_delegate_gate_check` returns `1 disabled-via-env`
   before `_adlc_delegate_opted_in` is ever called.

Measured with an instrumented `ADLC_READ_BIN` on a fork-counting stub:

```
ADLC_DISABLE_DELEGATE=1 -> rc=1 reason=disabled-via-env forks=0
ADLC_DELEGATE_ENABLED=1 -> rc=0 reason=ok            forks=0
```

**break_scenario**: an operator sets `ADLC_DISABLE_DELEGATE=1` during an incident to stop
transmission now. Today that is the *cheapest* path in the gate — an immediate shell
return, zero forks. Under BR-1 it becomes a Python fork on every gate call, across every
delegating step of `/spec`, `/wrapup`, `/analyze`, `/architect`, `/proceed` Phase 5,
multiplied by REQs in flight under `/sprint` — purely to be told "disabled". The emergency
stop goes from the fastest path to the slowest, and it does so for the population that has
explicitly opted out of the feature they are now paying for.

**refutation_attempt**: tried to save it via BR-4 — binary resolution stays in shell, so
perhaps the kill switch may too. It cannot: BR-1 names `ADLC_DISABLE_DELEGATE` explicitly
among the tests the gate must not contain, and BR-4's carve-out is justified *only* by the
probe's inability to answer whether its own binary resolved, which does not extend here.
Also tried "a disabled install calls the gate rarely" — false, the gate fires per
delegating step regardless of its answer; that is its purpose. Neither saves it. The REQ
must either widen BR-4's carve-out to the kill switch (weakening BR-1 in the one place it
matters most) or restate the cost honestly and defend it.

---

## F2 — BR-7 forbids the test AC-2 requires

- **severity**: major
- **confidence**: medium-high

AC-2 requires that removing the `ADLC_DISABLE_DELEGATE` arm from `delegation_enabled()`
makes the **shell** suite fail. BR-7 rewrites that suite to assert delegation only — "the
gate returns what the probe said; fails closed on a broken probe; returns 2 without
probing" — and moves cascade semantics to Python, stating that keeping the current cases
"would preserve the exact condition this REQ removes". The current case is verbatim
`"ADLC_DISABLE_DELEGATE=1 beats everything"` — precisely the test AC-2 depends on.

**break_scenario**: `/architect` reads BR-7, deletes the kill-switch case from
`delegate-gate.test.sh`, and satisfies BR-7. AC-2 is then unsatisfiable, and the REQ's own
regression test for BUG-209's root cause does not exist. Alternatively the architect
honours AC-2, keeps the case, and a reviewer cites BR-7 to remove it later — the guarantee
silently lapses.

**refutation_attempt**: argued a single end-to-end case (set the var, assert `rc=1`) is
"the gate returns what the probe said" and so satisfies both. That reading is available but
not what BR-7 says — it names the current cases as the thing to remove, and the current
case *is* that assertion. The spec does not distinguish "assert the cascade" from "assert
one end-to-end pass-through", and an architect could reasonably go either way. Ambiguity in
the rule that carries the REQ's core guarantee survives as a finding.

---

## F3 — Three BRs have no acceptance criterion

- **severity**: major
- **confidence**: high

BR→AC mapping across all twelve rules leaves three uncovered:

| BR | Covered by | |
|---|---|---|
| BR-4 (`no-binary` decided in shell, before any probe) | — | **none** |
| BR-9 (probe must not be self-gated) | — | **none** |
| BR-12 (`/template-drift` flags a stale vendored gate) | — | **none** |

**break_scenario**: BR-9 is the dangerous one. If an implementer routes `--print-enabled`
through `require_delegation_enabled()` — an easy mistake, since BUG-206 just added that
guard to every other transmission path — the probe *refuses* instead of *reporting
disabled*. The gate then reads a non-zero exit, applies BR-5's fail-closed rule, and
returns `not-opted-in` for a machine whose actual state is `disabled-via-env`. Telemetry
records the wrong reason, BR-3's byte-identical guarantee is broken, and no acceptance
criterion catches it because none exists.

**refutation_attempt**: checked whether AC-9's blanket "full Python suite passes" covers
them. It does not — it asserts the suite is green, not that these behaviours are asserted
in it; a suite with no BR-9 case passes trivially. This is exactly REQ-595's
implemented-as-zero class, in the repo that just shipped the machinery to prevent it.

---

## F4 — BR-12's stated harm does not materialize

- **severity**: minor
- **confidence**: medium

BR-12 justifies itself by claiming a repo with a stale vendored gate "would keep resolving
opt-in locally ... while the toolkit believes the gate defers". Traced every arm of the
*old* gate against the *new* Python: DISABLE (shell, correct), `ADLC_DELEGATE_ENABLED`
(shell, correct), config (probes Python, correct), legacy key (shell, correct). They agree
on every input. Nothing diverges; the stale repo merely fails to *gain* the single-source
property.

**break_scenario**: a reviewer checks BR-12's rationale against the code, finds no
divergence, and concludes the rule is decorative — dropping a check that has real
*future-conditional* value: the moment a later REQ adds a fifth arm to Python, a stale gate
that short-circuits on `ADLC_DELEGATE_ENABLED` would bypass it. The rule is worth keeping;
the reason given for it is not the reason it is worth keeping.

**refutation_attempt**: looked for a present-tense divergence hard enough to save the
stated rationale — a reason string, a return code, an ordering difference. Found none. The
rule survives on a different argument than the one written.

---

## F5 — `GateVerdict`'s enum contradicts BR-3 and BR-4

- **severity**: minor
- **confidence**: medium

The System Model constrains `GateVerdict.reason` to four values: `ok`,
`disabled-via-env`, `disabled-via-config`, `not-opted-in`. The gate emits **six**:
`delegate-gate.sh:53` initialises `unset`, and `:160` emits `no-binary` — which BR-4
explicitly preserves. An entity named *Gate*Verdict that cannot represent two of the gate's
reasons is mis-modelled.

**break_scenario**: `/architect` implements the enum as specified and validates the gate's
reason against it. `no-binary` — a reason BR-4 requires the gate to keep emitting — fails
validation, or gets silently coerced, breaking BR-3's byte-identical guarantee on the one
path BR-4 carved out.

**refutation_attempt**: argued the entity models the *probe's* output, where four values is
correct since BR-4 keeps `no-binary` in shell. That defends the value set but not the name
or the constraint text, which says "the full cascade's answer" and is what an implementer
reads. Renaming to `ProbeVerdict`, or listing all six with provenance, resolves it.

---

## Coverage

**Lenses run** (spec set): omissions; untestable rules; contradictory BRs/ACs; unstated
assumptions; scope holes.

**Lenses skipped**: plan/architecture (no `architecture.md`); diff/PR + BR→diff
cross-check (no diff — spec phase, nothing implemented); prose-claim counterexample search
(subsumed by the spec lenses).

**Per-rule enumeration** — every numbered BR and AC attacked, none skipped:

| Rule | Attacked | Outcome |
|---|---|---|
| BR-1 | yes | F1 (cost consequence) |
| BR-2 | yes | clean |
| BR-3 | yes | F5 (enum contradiction) |
| BR-4 | yes | F3 (no AC), F5 |
| BR-5 | yes | clean |
| BR-6 | yes | clean |
| BR-7 | yes | F2 (contradicts AC-2) |
| BR-8 | yes | clean |
| BR-9 | yes | F3 (no AC — highest-consequence gap) |
| BR-10 | yes | clean |
| BR-11 | yes | clean as a rule; id collision already filed by `/validate` as B-2 |
| BR-12 | yes | F3 (no AC), F4 (rationale unsupported) |
| AC-1 | yes | not mechanically decidable — already filed by `/validate` as W-1 |
| AC-2 | yes | F2 |
| AC-3 | yes | clean |
| AC-4 | yes | clean |
| AC-5 | yes | clean as a criterion; cites ambiguous `BR-11` (`/validate` B-2) |
| AC-6 | yes | clean |
| AC-7 | yes | clean |
| AC-8 | yes | clean |
| AC-9 | yes | measurement undefined — already filed by `/validate` as W-2 |
| AC-10 | yes | clean |

Findings already raised by `/validate` (missing `## Out of Scope`, the `BR-11` id
collision, AC-1/AC-9 weaknesses) are **not** re-reported here as adversary findings; they
are noted in the table for completeness.
