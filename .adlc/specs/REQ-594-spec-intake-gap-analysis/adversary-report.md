# Adversary Report — REQ-594

Target: `.adlc/specs/REQ-594-spec-intake-gap-analysis/requirement.md` (spec)
Date: 2026-08-27
Venue: single-context (agents not dispatched — see Coverage)
Verdict: **found problems**

## F4 — BR-4's pipeline mode describes a caller that does not exist (major, high)

**Break scenario.** BR-4 governs `/spec` "in non-interactive / pipeline mode", and its AC reads
"In pipeline mode (invoked from `/proceed`), the same source writes the spec…". Nothing invokes
`/spec`. `proceed/SKILL.md:41` says "If the spec doesn't exist, stop and tell the user to run
`/spec` first" and `:538` repeats "It does not create the initial spec". `/sprint` requires the
spec to already exist on the integration branch before a REQ is eligible. The AC is therefore
unconstructable — no implementer can build the scenario it describes — and BR-4's stated trigger
names a caller that will never call.

**Refutation attempt.** I tried to save it through the subagent case: `/spec` Step 1.5 already
lists "dispatched via the Agent tool" among its non-interactive conditions, and a user genuinely
can dispatch `/spec` into a subagent. That salvages the *rule* — it should be scoped to subagent
dispatch — but not the AC, whose `/proceed` scenario still cannot be constructed.

## F5 — no source-size bound and no truncation reconciliation (major, medium)

**Break scenario.** A three-hour meeting transcript is passed to intake. BR-5 makes delegating
the body read mandatory. The delegate returns a summary covering only part of the source and
exits 0. BR-2 classifies gaps against that partial view; BR-11's benign path then reports "zero
gaps" precisely because the unread remainder is invisible. The spec ships confident and
incomplete — the failure mode intake exists to prevent. `/spec` Step 1.6 already defends against
this with per-doc `<doc id="…">` coverage reconciliation, and REQ-423 bounds its reads with
`tail -n 200`. REQ-594 mirrors neither.

**Refutation attempt.** I argued the delegate would error rather than truncate silently. It did
not in this very session: the Step 1.6 body-read returned 10 of 15 requested docs with exit 0.
That is why the reconciliation step exists, and its absence here is the gap.

## F6 — an AC demands determinism from a nondeterministic process (minor, high)

**Break scenario.** AC-1 requires a one-line feature request to produce "byte-identical behavior
to today". `/spec` is an LLM-executed markdown skill; two runs over identical input are never
byte-identical. The AC can never be marked met, so an implementer either leaves it permanently
unchecked or quietly reinterprets it — and a reinterpreted AC is an ungated one.

**Refutation attempt.** Reading "byte-identical" as loose idiom for "behaviourally unchanged".
But an AC is exactly the artifact a gate checks, and this one names a property nothing can
satisfy.

## Coverage

Lenses run: omissions, untestable rules, contradictory BRs/ACs, unstated assumptions, scope holes.
Lenses skipped: none applicable (spec target).

Execution venue: single-context. The `adversary` agent was not dispatched: this session carries a
standing operator instruction not to use the Agent tool unless explicitly requested. The skill's
documented degradation path (same lenses, inline) was used, and this is stated rather than
silently skipped.

BR enumeration — BR-1 attacked, BR-2 attacked, BR-3 attacked, BR-4 attacked (F4), BR-5 attacked
(F5), BR-6 attacked, BR-7 attacked, BR-8 attacked, BR-9 attacked, BR-10 attacked, BR-11 attacked
(F5). None skipped.

AC enumeration — all 9 attacked; AC-1 (F6), AC-4 (F4). None skipped.
