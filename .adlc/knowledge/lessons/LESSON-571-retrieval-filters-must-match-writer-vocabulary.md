---
id: LESSON-571
title: "A retrieval filter is half of a read/write contract with whatever writes the field it filters on. Enumerate the writers, not the values you imagine; prefer an exclusion list over an allowlist; and give the empty result a distinct signal, because a filter that drops everything looks exactly like a corpus that holds nothing."
component: "adlc/spec"
domain: "adlc"
stack: ["markdown", "claude-skills", "python"]
concerns: ["retrieval", "silent-failure", "knowledge-compounding", "structural-enforcement", "verify-quality"]
tags: ["retrieval", "status-enum", "frontmatter", "read-write-contract", "allowlist-vs-denylist", "cold-start-masking", "fail-open"]
req: BUG-194
created: 2026-08-27
updated: 2026-08-27
---

## What Happened

REQ-258 shipped `/spec`'s unified tag-based retriever. Its spec-corpus filter
admitted frontmatter `status` in `approved` | `in-progress` | `deployed` — a
phrase carried over from atelier-fashion's style RAG, written as a design-time
description of "what counts as usable prior art."

Nobody enumerated what the toolkit's own skills actually write into that field:

| Writer | Writes |
|---|---|
| `/architect` Step 6 | `approved` |
| `/wrapup` Step 3 | `complete` |
| `/proceed` Phase 6-8 | `complete` |

Reader and writers overlapped on exactly one value — `approved`, a *transient*
state occupied only between `/architect` and `/wrapup`. `in-progress` and
`deployed` were vocabulary no toolkit skill has ever emitted (`deployed` existed
on 6 files in one consumer repo; `in-progress` on zero files anywhere).

So the filter admitted **0 of 42** specs in `adlc-toolkit` and **11 of 543
(2.0%)** across the five repos. Every `/spec` run for four months scored the
spec corpus correctly and then threw all of it away, including REQ-258 itself —
the retrieval pilot was invisible to retrieval.

It survived that long because three things masked it independently:

1. **The failure had no distinct output.** Step 1.6's cold-start message is
   byte-identical for "the corpus is empty" and "the filter removed the whole
   corpus." Both render `No prior context retrieved`.
2. **Results were never empty.** Lessons carry a `+1` foundational floor and no
   status filter, so something always came back. A non-empty result set reads as
   a working retriever.
3. **Telemetry measured the wrong thing.** REQ-424 records *whether* `adlc-read`
   was invoked, not what it was invoked on. A body-read of 4 lessons and 0 specs
   emits a perfectly healthy `delegated` record.

REQ-262 then backfilled the five *tag* dimensions across 468 consumer artifacts
specifically to make this retriever productive — and correctly left `status`
alone, since status was pre-existing lifecycle data and not part of the tag
schema. A dedicated retrieval-enablement REQ ran end to end over the broken
filter without anyone noticing, because it was measuring tag coverage, not
retrieved-corpus composition.

## Lesson

1. **A filter on a field is half of a contract with whatever writes that field.
   Enumerate the writers before you write the filter.** The question is never
   "what statuses mean *shipped*?" — that is a vocabulary question you can answer
   plausibly and still be wrong. It is "what values does the code on the other
   side of this field actually emit?", which is a `grep` and has one answer. Here
   the correct filter was derivable in one command; the incorrect one was
   derivable from good intentions.

2. **For a recall-oriented filter, prefer an exclusion list to an allowlist.** An
   allowlist must enumerate every synonym correctly or it silently discards the
   corpus; it fails *closed*, and closed failures in retrieval are invisible. An
   exclusion list fails *open*: an unrecognized or newly-invented status gets
   retrieved (cost: one extra scored candidate that probably loses on score)
   rather than dropped (cost: the whole corpus, silently). Match the failure
   direction to which error you can afford — and to which error you can *see*.

3. **"Nothing matched" and "everything was filtered out" must not render the same
   string.** If a legitimate empty state and a broken empty state produce
   identical output, the broken one is permanently invisible — it is not a bug
   that gets found late, it is a bug with no discovery path at all. Whenever you
   write a "no results" branch, ask which distinguishable conditions reach it,
   and give the pathological one its own message.

4. **When a data-side value and a skill-side expectation disagree, ask which side
   the pipeline writes.** The instinct is to reach for a backfill, as REQ-262
   did. Here that would have been backwards: `complete` is exactly what `/wrapup`
   emits, so migrating 478 files would have migrated *away* from the canonical
   value, and the next `/wrapup` would have written `complete` again and
   re-broken retrieval. The side that the pipeline writes is the side that is
   right. A backfill can only fix data that nothing is still producing.

5. **Corollary to LESSON-012.** The original filter *was* prose, and it was wrong
   the day it shipped. Restating it as better prose would leave nothing to detect
   the next drift, so the fix declares both sides in marker blocks and compares
   them in `tools/lint-skills` (`retrieval-status-parity`). And per LESSON-019 #1
   the guard is written so that deleting a declaration, relocating a write site,
   or emptying a block is a *finding* rather than a silent pass — a guard that
   can be disarmed by deletion is a guard with an expiry date.

## Why It Matters

Silent retrieval degradation is the most expensive kind of ADLC failure, because
it defeats the mechanism the whole toolkit exists to provide. Ethos #2 is
"Knowledge Compounds"; for four months it did not — every `/spec` run authored
without the prior art it had already computed and discarded. Nothing failed,
nothing was slow, no artifact looked wrong. The only symptom was specs that
didn't cite prior work, which is indistinguishable from a young corpus.

Concretely: 0% spec-corpus recall in the toolkit, 2.0% across five repos, and a
retrieval-enablement REQ (REQ-262, 468 files) that ran to completion over a
filter admitting 2% of what it had just prepared.

## Applies When

- Writing or reviewing any filter over a status/state/type enum — especially one
  that selects *what to retrieve* rather than *what to act on*
- Adopting a vocabulary or scoring shape from another codebase into a new one
  (the values are the part that does not transfer; the algorithm is the part that
  does)
- Writing a "no results" / cold-start / empty-set branch
- Choosing between allowlist and exclusion-list semantics
- Deciding between a data backfill and a code fix when the two sides disagree —
  identify which side is actively written before migrating anything
- Reviewing anything whose failure mode is "returns less than it should" rather
  than "throws"
