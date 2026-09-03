---
id: BUG-212
title: "A conflict resolved during a pipeline run leaves no machine-readable trace — the only record is the runner's closing narrative"
status: open
severity: medium
created: 2026-09-03
updated: 2026-09-03
component: "adlc/proceed"
domain: "adlc"
stack: ["bash", "git", "markdown", "claude-skills"]
concerns: ["observability", "auditability", "process-compliance"]
tags: ["rebase", "merge-conflict", "audit-trail", "pipeline-state", "phase-8", "sprint", "unattended", "silent-degradation"]
introduced_by: []
attribution: none
---

<!--
attribution: none. This is an absent audit field, not a behavior a specific merge
introduced — there is no commit whose lines could be blamed for the omission.
REQ-483/485 built the surrounding machinery; naming them would be a false
attribution (REQ-593 BR-3: refuse rather than guess).

Split out of BUG-207 on 2026-09-03. BUG-207 carried two independent items; this
is the second. It is deliberately filed as its own artifact because it is
shippable WITHOUT deciding BUG-207's scope question, and because shipping it is
what makes that decision measurable.
-->

## Description

When a pipeline run encounters a merge or rebase conflict and resolves it, nothing durable
records that it happened. Not `pipeline-state.json`, not the PR, not the merge record. The
only trace is the runner's closing narrative — prose, written at the runner's discretion,
which no consumer parses and no later reader can query.

Observed on the `/sprint` batch of three REQs on 2026-08-31: REQ-593 resolved a
`CHANGELOG.md` conflict against the freshly-merged REQ-595, and REQ-594 resolved two against
REQ-593 and REQ-595. All three resolutions were verified correct after the fact. Both runners
*volunteered* the deviation in their final report — **a runner that said nothing would have
left no trace at all**, and the batch would have looked identical to one that hit no
conflicts.

This is a gap regardless of how BUG-207's scope question is decided:

- If runner resolution turns out to be **permitted** in an unattended batch, then it is a
  routine operation performing unreviewed content merges on shared append-point files, and
  it should be as auditable as any other pipeline mutation.
- If it turns out to be **prohibited**, there is currently no way to detect a violation
  except by reading narrative prose — so the rule would be unenforceable and, worse,
  unmeasurable: nobody could say how often it was breached.

The absence is also what makes the risk hard to size. The reason to care is not that these
three resolutions were wrong — they were checked and correct — but that the failure mode is
silent. One of REQ-594's conflicts was a both-sides-append on `partials/tests/run.sh`'s
harness list. Had the resolution taken one side instead of merging them, `attribution.test.sh`
or `intake.test.sh` would have stopped running with every downstream check still green: **a
harness that is no longer enumerated does not fail, it ceases to exist.** With no recorded
conflict event, there is nothing to go back and re-examine when a harness quietly disappears
three sprints later.

That list is now six harnesses (`id-alloc`, `forge`, `attribution`, `intake`,
`delegate-gate`, `source-guard`), still hardcoded positionally with no count assertion and no
discovery — so the exposure has grown since the observation.

## Reproduction Steps

1. Launch `/sprint` with two or more REQs whose diffs touch a common append-point file
   (`CHANGELOG.md` and `partials/tests/run.sh` are the reliable ones).
2. Let one REQ merge while another is between Phase 4 and Phase 8.
3. Observe the second runner hit and resolve a textual conflict in its Phase 7/8 rebase.
4. Read `pipeline-state.json` for that REQ. Observe that nothing indicates a conflict
   occurred, which files were involved, or how it was resolved.
5. `grep -r conflictsResolved .` — confirm the field exists nowhere in the toolkit.

## Expected Behavior

A conflict encountered and resolved during a pipeline run is recorded in
`pipeline-state.json`, so it is auditable without relying on the runner having chosen to
mention it.

## Actual Behavior

Nothing is recorded. The event is recoverable only from the runner's closing narrative, if
the runner wrote one.

## Environment

- Platform: macOS (darwin 25.6.0), zsh executor
- Version: adlc-toolkit 5.0.0. Verified 2026-09-03: `conflictsResolved` appears nowhere in
  the repository outside BUG-207's original proposal text.

## Root Cause

(filled during investigation — hypothesis below)

`pipeline-state.json`'s schema grew to record phase progress, merge order, and blocker
relationships — the things the orchestrator needs to *make decisions*. A conflict resolution
is not an input to any subsequent decision, so it was never added. Nothing rejected the idea;
the field was simply never needed by the machinery, and no consumer asked for it. Observation
that isn't load-bearing for control flow tends not to get built unless someone builds it
deliberately.

## Proposed Direction

Add a `conflictsResolved` entry to `pipeline-state.json` recording, per event: the phase, the
conflicting paths, the resolution strategy, and whether the resolution was verified. Written
by the runner at the point of resolution, not reconstructed afterwards.

Two properties matter more than the exact shape:

1. **Additive and optional**, like `introduced_by`/`attribution` on the bug template — a
   state file carrying no such entry must parse and process unchanged, and absent must read
   as "no conflicts", not as a missing value.
2. **Written before continuing, not at the end.** A runner that crashes after resolving but
   before finishing should still leave the record. An entry written in a closing step is the
   same discretionary narrative in JSON clothing.

Worth surfacing once recorded: `/status` is the natural place to report conflict events per
run, alongside the Incident Attribution section REQ-593 added.

**Deliberately not in scope:** any gate that blocks or reverses a runner's resolution. That
would presume an answer to BUG-207, which is exactly what this artifact avoids doing.

## Resolution

`pipeline-state.json` gains `conflictsResolved: []` — additive, optional, absent reads as
"none resolved". One entry per resolution: `phase`, `files`, `resolvedBy` (`runner` |
`user` | `orchestrator`), `strategy` (`both-sides-append` when literally true, else
described), `verified` + `verifiedHow`, `resolvedAt`, optional `note`. The two properties
the Proposed Direction named are the contract:

1. **Additive and optional** — mirrors `introduced_by`/`attribution` on the bug template.
2. **Written at the moment of resolution, before continuing** — stated in every place a
   resolution can happen: the runner's own Phase 7/8 (`agents/pipeline-runner.md`, the
   `/proceed` Error Handling line), and the post-halt resume where a human resolved a
   materialized conflict (`proceed/phases-6-8-ship.md` clear-on-resolve write,
   `sprint/SKILL.md` step 6). The `/sprint` unblock pass appends nothing, because it never
   resolves (REQ-485 BR-4); a clean auto-rebase is not a resolution.

`/status` gains a **Conflict Resolutions** section reading every spec's state file,
printing `No recorded conflict resolutions.` when none. `verified: no` is surfaced as the
honest value it is, not an error. `.adlc/context/architecture.md` records the layer.

Deliberately **not** done, as filed: any gate on whether a runner may resolve. That is
BUG-207's question; this guarantees that if it did, the record exists — which is what
makes BUG-207's eventual bound measurable.

Verification is structural (markdown-only surface, per conventions): `tools/lint-skills`
clean over the changed skills, and the field name present in each of the six surfaces.

## Files Changed

- `proceed/SKILL.md` — schema gains `conflictsResolved`; paragraph defining it; Error
  Handling "Merge conflicts" requires the write before continuing
- `agents/pipeline-runner.md` — "Conflict resolution record (BUG-212)": entry schema table
  and the write-at-resolution rule
- `proceed/phases-6-8-ship.md` — clear-on-resolve write appends the entry after a
  human-resolved re-halt; a runner's own resolution appends at that moment
- `sprint/SKILL.md` — step 6 and the Scope paragraph name the record; the pass itself
  never writes it
- `status/SKILL.md` — new Conflict Resolutions section
- `.adlc/context/architecture.md` — one sentence on the audit layer
- `CHANGELOG.md` — Fixed entry; also carries the LESSON-625 Knowledge line that #161
  missed (anchor mismatch)

## Related

- **BUG-207** — the scope question this was split from on 2026-09-03. That artifact decides
  *whether* a runner may resolve; this one records *that it did*, either way.
