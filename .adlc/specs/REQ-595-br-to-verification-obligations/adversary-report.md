# Adversary Report — REQ-595

Target: `.adlc/specs/REQ-595-br-to-verification-obligations/requirement.md` (spec)
Date: 2026-08-27
Venue: single-context (agents not dispatched — see Coverage)
Verdict: **found problems**

## F7 — the recorded Open-Question resolution contradicts BR-2 (major, high)

**Break scenario.** BR-2 states `/validate` **fails** when a numbered BR has no verification
obligation, and AC-2 confirms it ("causes `/validate` to fail"). The Open Question resolved
2026-08-27 states the coverage gate ships **advisory** for one epoch, mirroring REQ-425. An
implementer reading BR-2 builds a blocking gate; one reading the resolution builds an advisory
notice. The resolution is currently inert prose contradicting the rule it was written to settle
— and it was introduced by the same pass that was supposed to reduce ambiguity.

**Refutation attempt.** I argued "fails" could mean "emits a failure finding" without blocking
advancement. BR-2 sits under `/validate`, whose entire contract is pass/fail phase advancement,
so "fails" there means blocks.

## F8 — BR-3 resolves from a file this repo does not have (major, high)

**Break scenario.** BR-3 derives obligation `kind` from `.adlc/config.yml` `stack:`. There is no
`.adlc/config.yml` in adlc-toolkit. AC-3 nonetheless requires that "for a SKILL.md-only REQ **in
this repo**, obligations resolve to `structural-check`" — which BR-3 cannot do here. Every other
skill touching that file reads only the `repos:` block and declares an explicit single-repo
fallback (`architect/SKILL.md:71`, `validate/SKILL.md:67`); no skill reads `stack:` at all, and
BR-3 defines no absent-config branch. The dogfooding repo is the one repo where the rule cannot
execute.

**Refutation attempt.** I argued the README's "every skill falls back to legacy single-repo
behavior" covers it. That fallback concerns `repos:`, not `stack:`. There is no legacy behavior
for `stack:` to fall back to, because nothing has ever read it.

## F9 — the gate closes the BR omission hole and leaves the AC hole open (major, medium)

**Break scenario.** BR-1 requires each task to list "every BR **and AC** that task discharges",
but BR-2 gates only on "any numbered **BR**". A REQ whose acceptance criterion is implemented as
zero passes the gate cleanly, because no rule ever checks AC coverage. LESSON-330's omission
class — the thing this REQ exists to close — stays half-open.

**Refutation attempt.** I argued ACs always derive from their BRs, making BR coverage sufficient.
REQ-593 in this same set disproves it: three of its ACs (the two cross-repo cases and the
`/status` case) have no one-to-one BR.

## F10 — "executed-case count" does not map onto `structural-check` (minor, medium)

**Break scenario.** BR-5 requires every obligation kind to report a count of executed cases. A
`structural-check` obligation resolves to a `tools/lint-skills` check, which runs once per repo
and reports findings, not per-obligation case counts. Ten obligations mapping onto one lint
invocation cannot each report a count, so BR-5 is unsatisfiable for the kind this repo uses
exclusively.

**Refutation attempt.** Files-scanned could serve as the count, following REQ-435's vacuous-scan
precedent. That partially works — which is why this is minor rather than major — but BR-5 says
"cases", and a per-kind definition of the count is undefined.

## Coverage

Lenses run: omissions, untestable rules, contradictory BRs/ACs, unstated assumptions, scope holes.
Lenses skipped: none applicable (spec target).

Execution venue: single-context. The `adversary` agent was not dispatched: this session carries a
standing operator instruction not to use the Agent tool unless explicitly requested. The skill's
documented degradation path (same lenses, inline) was used, and this is stated rather than
silently skipped.

BR enumeration — BR-1 attacked (F9), BR-2 attacked (F7, F9), BR-3 attacked (F8), BR-4 attacked
(mechanism gap already surfaced as /validate W4 and consciously deferred to `/architect`; not
re-raised here), BR-5 attacked (F10), BR-6 attacked, BR-7 attacked, BR-8 attacked, BR-9 attacked
(F8), BR-10 attacked. None skipped.

AC enumeration — all 10 attacked; AC-2 (F7), AC-3 (F8), AC-10 (F8). None skipped.
