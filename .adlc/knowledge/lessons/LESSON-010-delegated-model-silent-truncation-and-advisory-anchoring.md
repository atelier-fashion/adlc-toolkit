---
id: LESSON-010
title: "When you delegate bulk reading to a cheaper model, you also delegate the risk that it silently truncates or paraphrases away exactly the facts you needed — reconcile coverage, sanitize every column, and offer a single-item escape hatch"
component: "adlc/skills"
domain: "adlc"
stack: ["markdown"]
concerns: ["correctness", "security", "anchoring-bias", "skill-design"]
tags: ["kimi", "delegation", "truncation", "coverage-reconciliation", "advisory-candidates", "anchoring", "citation-fidelity"]
req: REQ-417
created: 2026-05-14
updated: 2026-05-14
---

## What Happened

REQ-417 added Kimi delegation to three more ADLC skills (`/spec` Step 1.6 retrieval,
`/analyze` Step 2 audit pre-pass, `/proceed` Phase 5 verify pre-pass). The 6-agent verify
pass uncovered four classes of failure that the REQ-414/415 pattern hadn't surfaced
before, because none of the earlier delegations consumed the model's output as
*structured-by-id content* the way `/spec`'s retrieval does, or as an *advisory list given
to other agents* the way `/analyze` and `/proceed` do:

1. **Silent truncation by word budget.** `/spec`'s prompt told Kimi to return per-doc
   summaries for the top-15 retrieved documents within "1200 words max total." If Kimi
   hit the budget mid-stream, it would just stop emitting `<doc id="…">` blocks. The
   orchestrator had no way to know whether doc 13, 14, 15 were genuinely covered or just
   silently dropped. Step 3 ("write business rules with inline citations") would then
   either under-cite (if Claude noticed the gap) or, worse, cite an id whose body the
   orchestrator never actually saw.

2. **Lossy summary vs verbatim-rule fidelity.** Even within budget, a 80-word per-doc
   summary cannot preserve every exact-quote constraint a load-bearing lesson contains.
   A LESSON saying "field X must never exceed 2048 bytes" reduces in Kimi's summary to
   "imposes a size limit on field X" — usable for context, but not for an inline
   citation that needs the exact number.

3. **Advisory-list anchoring.** `/analyze` and `/proceed`'s pre-pass produced a
   per-dimension candidate-findings list passed to the actual audit/review agents as
   "advisory, confirm or refute." Research on LLM prompt sensitivity shows labeled
   candidate lists materially shift output distribution even when explicitly labeled
   untrusted. A prose caveat is necessary but probably not sufficient.

4. **Non-citation column injection.** The candidate list's *description* column (the
   `<file path> | <one-line description>` shape) is free-text from Kimi. The citation
   sanitization (strict regex + on-disk existence) protects the path token but does
   nothing for the description, which then survives verbatim into a downstream agent's
   prompt. Shell metacharacters, imperative sentences, or even fabricated "context
   notes" inside a description can quietly influence the agent that consumes it.

## Lesson

1. **Reconcile coverage against an expected set.** When a delegated model is asked to
   summarize N inputs, check that the response contains N (or some explicit minimum)
   distinct outputs. For each input that didn't get an output, **read it directly** as
   a fallback rather than treating absence as "nothing notable to say about it."

2. **Offer a single-item escape hatch.** Bulk delegation is the default; allow a
   targeted single-item *re-read* when downstream work hits a fidelity ceiling. For
   `/spec` that's "if Step 3 authoring needs an exact rule, you may read that one doc's
   full body — single-doc fallback, not all-docs fallback." Preserves most of the
   bulk-saving while protecting the exact case where bulk falls down.

3. **Sanitize every column, not just the citation.** The structured-output paradigm
   wants you to think about the cited identifier, but Kimi (or any delegated model)
   emits multiple fields per row. Each field needs its own sanitization rule. For
   free-text columns going into another LLM's prompt: strip characters outside a tight
   allowlist (`[A-Za-z0-9 .,:;()/_'"-]` works) before forwarding. The
   `<untrusted-data>` wrapping mitigates prompt injection at the meta level; per-column
   sanitization mitigates at the data level.

4. **Treat "advisory" with skepticism.** A pure-prose "these are advisory, confirm
   them" caveat next to a structured candidate list is weaker than its words suggest. If
   independence really matters, **enforce it structurally**: have the consuming agent
   produce its own findings first, then show it the advisory list for reconciliation.
   The current REQ-417 implementation ships with the prose-only caveat as a known
   limitation; a follow-up structural fix is on the backlog.

5. **In a numbered sequence of steps, do not skip numbers.** `### Step 1.5` followed
   by `### Step 1.7` is a debt the next maintainer pays. Either the new step is `1.6`
   (filling the slot) or it lives elsewhere in the document. Pure cosmetic — but
   accruing.

## Why It Matters

Every delegation point widens the trust boundary. The REQ-412 → REQ-414 → REQ-417 arc
keeps generating new variants of "Kimi's output is one step closer to influencing a
load-bearing decision." For `/spec`, Kimi's summary feeds the orchestrator's authoring
of business rules. For `/analyze` and `/proceed`, the advisory list feeds another LLM's
prompt directly. The further from the original "Claude reads, Claude reasons" pipeline,
the more these silent-failure modes matter — and the cheaper it is to add coverage
reconciliation and per-column sanitization at the boundary than to debug a corrupted
spec or biased audit report after the fact.

## Applies When

Designing any skill that delegates a "read N inputs, summarize each" operation to an
external model; designing any pipeline where a model's structured output is fed into
another model's prompt; reviewing the verify pass of any REQ that crosses the
delegation boundary in a new direction.
