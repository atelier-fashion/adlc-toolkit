---
id: BUG-194
title: "/spec Step 1.6 spec-corpus status filter admits no status the pipeline ever writes — spec retrieval silently returns zero"
status: open
severity: high
created: 2026-08-27
updated: 2026-08-27
component: "adlc/spec"
domain: "adlc"
stack: ["markdown", "claude-skills", "python"]
concerns: ["retrieval", "silent-failure", "knowledge-compounding", "structural-enforcement", "verify-quality"]
tags: ["retrieval", "status-enum", "frontmatter", "read-write-contract", "step-1.6", "cold-start-masking"]
---

## Description

`/spec` Step 1.6 sub-step 1 filters the spec corpus to frontmatter `status` in
`approved` | `in-progress` | `deployed`. No toolkit skill writes `in-progress`
or `deployed`. The write-side lifecycle is:

| Writer | Status written | Site |
|---|---|---|
| `/architect` | `approved` | `architect/SKILL.md:223` |
| `/wrapup` | `complete` | `wrapup/SKILL.md:77` |
| `/proceed` Phase 6-8 | `complete` | `proceed/phases-6-8-ship.md:24` |

The read filter and the write vocabulary overlap on exactly one value —
`approved` — which is a *transient* state occupied only between `/architect`
and `/wrapup`. The terminal state every shipped REQ lands in, `complete`, is
excluded. Retrieval therefore returns approximately zero specs at steady state,
and degrades to lessons + bugs with no error raised.

This is the silent-failure class of LESSON-019 (a guard coupled to a shape that
moved) and LESSON-012 (prose-only correctness with no structural check). The
degradation is indistinguishable from the legitimate cold-start path: Step 1.6
sub-step 8 writes "No prior context retrieved" either way.

## Reproduction Steps

1. In `adlc-toolkit` (42 specs, all `status: complete`), run `/spec` with any
   feature request whose query tags overlap the spec corpus — e.g. a retrieval
   topic that should surface REQ-258 (`component: adlc/spec`, `domain: adlc`,
   `concerns: [retrieval, ...]`, score 12).
2. Observe Step 1.6 sub-step 1's status filter is applied to
   `.adlc/specs/*/requirement.md`.
3. Observe the `## Retrieved Context` section of the emitted spec.

Measured status distribution at time of report:

| Repo | complete | done | deployed | approved | superseded | cancelled | draft | completed | admitted by current filter |
|---|---|---|---|---|---|---|---|---|---|
| adlc-toolkit | 42 | – | – | – | – | – | – | – | **0 / 42** |
| atelier-fashion | 244 | – | 6 | 1 | 31 | – | – | 1 | 7 / 283 |
| atelier-web | 76 | 12 | – | 1 | – | – | – | – | 1 / 89 |
| admin-api | 59 | 4 | – | 1 | – | 1 | – | – | 1 / 65 |
| infrastructure | 57 | – | – | 2 | 3 | 1 | 1 | – | 2 / 64 |
| **total** | **478** | **16** | **6** | **5** | **34** | **2** | **1** | **1** | **11 / 543 (2.0%)** |

## Expected Behavior

Spec retrieval admits shipped and in-flight prior art — the `complete` /
`deployed` / `done` terminal states and the `approved` / `in-progress` active
states — and excludes only unvalidated (`draft`) and withdrawn
(`superseded`, `cancelled`, `rejected`) specs. When a status filter removes
100% of a non-empty corpus, that is surfaced, not silently absorbed into the
cold-start path.

## Actual Behavior

The filter admits 0 of 42 specs in `adlc-toolkit` and 11 of 543 (2.0%)
ecosystem-wide. `/spec` reports "No prior context retrieved" — the same output
as a genuinely empty corpus. No warning, no error, no telemetry signal.

## Environment

- Platform: adlc-toolkit @ 229e6b9, symlink install
- Version: filter introduced by REQ-258 (2026-04-19), unchanged since
- Affected repos: adlc-toolkit + all 4 consumer repos with `.adlc/specs/`

## Root Cause

**A read/write contract mismatch inside the toolkit, not data drift.**

REQ-258 ("Unified Tag-Based Retrieval for /spec (Pilot)") adopted the scoring
shape and the corpus-filter vocabulary from atelier-fashion's style RAG. Its
Description names the spec corpus as "prior specs (approved / in-progress /
deployed)". That phrase was written as a design-time description of what
*counts as* usable prior art; it was never reconciled against the status values
the toolkit's own pipeline emits. `in-progress` and `deployed` are atelier
vocabulary — `deployed` appears on exactly 6 files in one repo, `in-progress`
on zero files anywhere.

REQ-262 subsequently backfilled the five *tag* dimensions (`component`,
`domain`, `stack`, `concerns`, `tags`) across 468 consumer-repo artifacts to
make the retriever productive. It deliberately did not touch `status` — status
was pre-existing lifecycle data, not part of the tag schema. So the tag side
was made consistent and the status side was left mismatched, which is why the
retriever scores correctly and then discards everything it scored.

The defect is therefore **(b), a gap in the skill's status enum** — with a
small, secondary **(a)** tail that is consumer-side only:

- `done` (16, atelier-web + admin-api) — a legacy pre-toolkit synonym for `complete`
- `completed` (1, atelier-fashion) — a typo variant
- `deployed` (6, atelier-fashion) — the one place the REQ-258 vocabulary is real

`adlc-toolkit`'s own 42 specs are **not** drifted: `complete` is precisely what
`/wrapup` and `/proceed` write. A data-side backfill in the REQ-262 style would
be actively wrong here — it would migrate 478 files toward a value no skill
emits, and the next `/wrapup` would write `complete` again and re-break
retrieval. **The fix must be skill-side.** The consumer-repo `done` /
`completed` values are handled by admitting them in the filter, not by
rewriting 17 files.

**Why it stayed invisible.** Three independent maskers:

1. Sub-step 8's cold-start message is identical for "corpus empty" and "filter
   ate the corpus" — the failure has no distinct output.
2. Lessons carry a `+1` foundational floor (sub-step 3) and no status filter, so
   retrieval always returns *something*. A non-empty result set reads as success.
3. The REQ-424 delegation telemetry records whether `adlc-read` was invoked, not
   what it was invoked *on* — a body-read of 4 lessons and 0 specs emits a
   healthy `delegated` record.

**Secondary finding (same class, same step).** The bug corpus filter admits
`resolved` only. Observed bug statuses: `resolved` (147), `open` (10),
`in-review` (1), `closed` (1). `closed` is an atelier-fashion synonym for
`resolved` and is silently dropped. One file, but the identical failure mode.

## Resolution

Skill-side, three parts. No data backfill — `complete` is the correct value the
pipeline writes, so migrating the corpus would have been migrating away from the
canonical status (see Root Cause).

**1. Allowlist → exclusion list (`spec/SKILL.md` Step 1.6 sub-step 1).** The spec
corpus now admits every status EXCEPT `draft`, `superseded`, `cancelled`,
`rejected`. This admits `complete` (478 files), `done` (16), `completed` (1) and
`deployed` (6) without needing to enumerate them, and fails toward recall: a
future or unrecognized status value is retrieved rather than silently dropped.
The bug corpus filter gains `closed` alongside `resolved`.

Measured effect (identical scoring, only the status filter changed):

| Repo | candidates | admitted before | admitted after |
|---|---|---|---|
| adlc-toolkit | 42 | 0 | 42 |
| atelier-fashion | 283 | 7 | 252 |
| atelier-web | 89 | 1 | 89 |
| admin-api | 65 | 1 | 64 |
| infrastructure | 64 | 2 | 59 |
| **total** | **543** | **11 (2.0%)** | **506 (93.2%)** |

The 37 still excluded are exactly the withdrawn (`superseded` 34, `cancelled` 2)
and unvalidated (`draft` 1) specs — the intended exclusions.

Re-scoring the toolkit corpus against a retrieval-shaped query with the fixed
filter ranks REQ-258 first, and 40 of 42 specs now score above zero.

**2. Status-filter shrink diagnostic (`spec/SKILL.md` Step 1.6 sub-step 1a, new).**
If the spec directory holds one or more `requirement.md` files and zero survive
the status filter, `/spec` emits a stderr warning naming the distinct statuses it
saw, and Step 3 writes `Spec corpus suppressed by status filter` into
`## Retrieved Context` instead of the cold-start line. This part addresses the
*class* of failure rather than this instance: the two conditions previously
produced byte-identical output, which is why the defect survived four months and
a dedicated retrieval-enablement REQ (REQ-262). It also covers consumer-repo
data drift that no toolkit-side filter can anticipate.

**3. Structural recurrence guard (`tools/lint-skills`, new
`retrieval-status-parity` per-root check).** `/spec`'s exclusion list and the
statuses written by `/architect`, `/wrapup`, and `/proceed` Phase 6-8 are now
declared in `<!-- retrieval-status: ... -->` marker blocks and mechanically
compared. Any status a lifecycle skill writes that appears in the reader's
exclusion list is a lint finding. Modeled on `check_sync_surface_parity`
(REQ-525) and, per LESSON-019 #1, written so the guard cannot rot quietly: a
write site that loses its declaration, moves, or declares an empty block is a
finding, not a silent pass. The check degrades to zero findings outside the
toolkit checkout and on pre-fix copies.

Prose alone would have been insufficient here — the original filter *was* prose,
and it was wrong from the day it shipped (LESSON-012).

## Verification

- `python3 -m pytest tools/` — 484 passed (66 in `tools/lint-skills/tests`,
  19 of them new).
- `python3 tools/lint-skills/check.py --root .` — exit 0.
- `test_pre_bug194_allowlist_shape_is_caught` reconstructs the original filter as
  its exclusion complement and asserts the new check flags it — the guard is
  proven against the real defect, not only against its own fixtures (LESSON-019 #2).
- Empirical re-scoring across all 5 repos (table above).

## Files Changed

- `spec/SKILL.md` — Step 1.6 sub-step 1: allowlist → exclusion list, bug corpus gains `closed`, added the `retrieval-status: spec-exclude` marker block; new sub-step 1a shrink diagnostic; sub-step 9 and Step 3's `## Retrieved Context` instruction updated so a status-filter suppression is never reported as a cold start
- `architect/SKILL.md` — Step 6: `retrieval-status: lifecycle-write` declaration (`approved`)
- `wrapup/SKILL.md` — Step 3: `retrieval-status: lifecycle-write` declaration (`complete`)
- `proceed/phases-6-8-ship.md` — Phase 6 step 2: `retrieval-status: lifecycle-write` declaration (`complete`)
- `tools/lint-skills/check.py` — `parse_retrieval_status_block`, `check_retrieval_status_parity`, the `LIFECYCLE_WRITE_SITES` / `RETRIEVAL_READER_SITE` registry and marker regexes; wired into `run()`
- `tools/lint-skills/tests/test_retrieval_status_parity.py` — 19 tests: parser, graceful degradation, the BUG-194 invariant, anti-rot rules, and regression assertions against the real toolkit tree
