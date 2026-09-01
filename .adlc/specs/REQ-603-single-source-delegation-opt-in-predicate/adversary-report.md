# /adversary — REQ-603 (pass 2, against revision dcde8e8)

Target: `REQ-603` requirement.md as revised. Type: **spec**. Read at full fidelity;
target unmodified by this pass.

Venue: single-context degradation (lenses run inline, no agent dispatch), as in pass 1.

Verdict: **found problems** — 4 findings survived refutation.

Pass-1 findings F1–F5 were all addressed by the revision and are **not** re-litigated
here. This pass attacks the *new* material, principally the veto/authorization asymmetry
that pass 1 caused to be written and that is now the REQ's load-bearing argument.

---

## F1 — The asymmetry holds only if both veto predicates match, and nothing requires it

- **severity**: major
- **confidence**: high

BR-2 permits the one deliberate duplication on this reasoning: *"a veto arm cannot return
enabled on any input — the copies can only agree or abstain, never contradict."*

That is true only while the two implementations recognise the **same input set**. Today
they do — shell tests `[ "${ADLC_DISABLE_DELEGATE:-0}" = "1" ]`, Python tests
`os.environ.get(...) == "1"` — but **no rule in this REQ requires it**, and no test asserts
cross-layer agreement. BR-4 freezes the reason *vocabulary*, not the predicates. The
Assumptions section covers a veto "made to authorize", which is a different mutation.

**break_scenario**: someone later makes the shell veto more permissive — accepting `true`
and `yes` alongside `1`, which reads as a usability fix. Now with `ADLC_DISABLE_DELEGATE=true`:
the gate vetoes and returns `1 disabled-via-env`, so every skill reports delegation
disabled; meanwhile `delegation_enabled()` does not veto, so a **direct CLI call
transmits**. The operator sees "disabled" everywhere they look and file contents leave the
machine anyway. That is BUG-209's failure — the gate saying one thing while the CLI does
another — reintroduced through the door BR-2 deliberately opens.

Note the direction matters and only one is safe: a *narrower* shell predicate is harmless
(shell abstains, the probe still vetoes). A *broader* shell predicate is the defect. The
asymmetry argument is therefore not "vetoes are safe to duplicate" but the narrower "vetoes
are safe to duplicate **when the downstream copy is at least as broad**" — a claim the REQ
does not state and does not test.

**refutation_attempt**: tried to kill it with BR-9's coverage method — revert an arm,
confirm the Python suite fails. That catches *deletion*, not *narrowing*: a Python veto
that still matches `"1"` passes every existing test, including
`test_disable_requires_exactly_one`, while the shell copy drifts wider. Also tried reading
BR-2's "checked before any probe" as implying a shared implementation — it constrains
position, not predicate. Neither saves it. **Fix**: state the equal-breadth requirement in
BR-2 and add an AC asserting both layers agree over a shared input vector
(`1`, `0`, ``, `true`, `yes`, `2`).

---

## F2 — BR-3's named consumer does not consume what BR-3 says it does

- **severity**: major
- **confidence**: high (verified)

BR-3 justifies the reason-bearing probe by asserting that `ADLC_DELEGATE_GATE_REASON` is a
documented contract because "`tools/delegate/check-delegation.sh` aggregates the telemetry
`reason` column". It does not. `check-delegation.sh:76-79` extracts and groups by **`mode`**
(`delegated` / `fallback` / `ghost_skip`); the string `reason` appears in that script only
in comments.

Worse, the two vocabularies are **different sets that happen to share three tokens**. Over
181 telemetry rows:

| | |
|---|---|
| gate reasons | `ok`, `no-binary`, `not-opted-in`, `disabled-via-env`, `disabled-via-config`, `unset` |
| telemetry `reason` values observed | `ok` 124, `no-flag` 27, `no-binary` 25, `api-error` 24, `not-opted-in` 4, `not-invoked` 4, + 4 singletons |

`no-flag` and `api-error` are not gate reasons at all. `disabled-via-env` and
`disabled-via-config` appear **zero times in 181 rows** despite being gate reasons. The
telemetry `reason` field is a skill-level outcome field with its own vocabulary, not the
gate reason passed through.

**break_scenario**: `/architect` reads BR-3, treats the telemetry `reason` column as the
gate contract, and either (a) changes the telemetry emitter to carry gate reasons —
silently altering a column with 181 rows of history that BR-4 promises to preserve — or (b)
implements the final AC ("telemetry rows carry the same `reason` values as before") as the
verification for BR-4's byte-identical guarantee, which it cannot be: that column is only
loosely coupled to the gate and would stay green through a total regression of the gate's
own reason strings.

The same confusion appears in Out of Scope, which places `api-error` under "changing the
reason vocabulary" that BR-4 scopes to gate reasons — two different fields conflated in a
scope boundary.

**refutation_attempt**: looked for a real consumer to rescue the rule. Found one —
`agents/delegate-pre-pass.md:34-35,122` requires `gateReason` "verbatim" — so
`ADLC_DELEGATE_GATE_REASON` **is** a genuine contract and BR-3's conclusion stands. Only
its stated evidence is false. The rule survives with the wrong reason attached, which is
exactly the F4 shape from pass 1 recurring in a different rule. **Fix**: cite
`delegate-pre-pass` as the consumer, drop the `check-delegation.sh` claim, and re-scope the
final AC to the gate's reason output rather than the telemetry column.

---

## F3 — The gate-call frequency count omits the call site that multiplies

- **severity**: minor
- **confidence**: high (verified)

The Assumptions section states frequency as 1–2 per skill run, "counted from
`adlc_delegate_gate_check` call sites in `proceed`, `wrapup`, `spec`, and `analyze`". That
count grepped `SKILL.md` files only and missed **`agents/delegate-pre-pass.md`**, which
runs the gate and is dispatched **per repo** for the `/sprint --workflow` Phase-5 panel.

**break_scenario**: the assumption invites re-opening the caching question "if a future
skill calls the gate in a loop" — while the existing fan-out call site is already unbounded
in the dimension that matters (repos × REQs in a sprint). Someone auditing the cost later
checks the four named skills, finds 1–2 calls, and concludes the assumption holds while a
20-REQ sprint is issuing an order of magnitude more.

**refutation_attempt**: tried to kill it on materiality, and the *conclusion* does survive —
even 50 pre-pass invocations add ~1.05 s across a sprint whose individual steps median
104 s. But the assumption is written as a measured claim with a named method, and the method
is wrong; a future reader re-deriving from it gets a wrong number. The finding is about the
evidence, not the verdict.

---

## F4 — BR-2 and BR-5 do not specify their relative order

- **severity**: minor
- **confidence**: medium

BR-2 says the veto is "checked before any probe". BR-5 says `no-binary` is "decided in
shell, before any probe". Both are pre-probe; **which comes first is unstated**. Today's
gate resolves the binary first (`adlc_delegate_gate_check` returns `2 no-binary` before
reaching the veto), so binary-missing + veto-set yields `2 no-binary`.

**break_scenario**: an architect implementing from the Business Rules puts the veto first —
defensible, since it is the emergency stop — and binary-missing + veto-set now returns
`1 disabled-via-env` where today it returns `2`. That silently violates BR-4's
byte-identical return-code guarantee on a path no BR covers.

**refutation_attempt**: AC-8 does pin the order, requiring `2 no-binary` "including when
`ADLC_DISABLE_DELEGATE=1` is also set", and acceptance criteria are binding. That
substantially mitigates the finding and is why it is minor rather than major. It does not
kill it: BRs are what an implementer builds from and ACs are what catches them afterwards,
and a rule ordering that exists only in a test is the honour-system shape BUG-207 is open
about. One clause in BR-5 would remove the ambiguity at no cost.

---

## Coverage

**Lenses run**: omissions; untestable rules; contradictory BRs/ACs; unstated assumptions;
scope holes. Emphasis on the new asymmetry argument and the newly added Out of Scope
section, since those carry the revision's weight.

**Lenses skipped**: plan/architecture (no `architecture.md`); diff/PR + BR→diff cross-check
(spec phase, nothing implemented); prose-claim counterexample search (subsumed by the spec
lenses).

**Per-rule enumeration** — all 13 BRs and all 18 ACs attacked, none skipped.

| Rule | Attacked | Outcome |
|---|---|---|
| BR-1 | yes | clean |
| BR-2 | yes | **F1** (equal-breadth unstated), F4 (ordering) |
| BR-3 | yes | **F2** (false evidence) |
| BR-4 | yes | F2 (telemetry column conflated) |
| BR-5 | yes | F4 (ordering) |
| BR-6 | yes | clean |
| BR-7 | yes | clean |
| BR-8 | yes | clean — pass-1 F2 resolved; the veto case is correctly justified as gate-owned |
| BR-9 | yes | clean as a rule; cannot detect F1's narrowing (noted in F1) |
| BR-10 | yes | clean — closes pass-1's highest-consequence gap |
| BR-11 | yes | clean |
| BR-12 | yes | clean |
| BR-13 | yes | clean — pass-1 F4 rationale corrected to future-conditional |
| AC-1 → AC-18 | yes | AC-3/AC-8/AC-10 clean and load-bearing; final telemetry AC implicated in F2; no AC covers F1's cross-layer agreement |

**Coverage regression check**: all 13 BRs are cited by at least one AC (verified
programmatically). Pass-1 F3 is resolved.
