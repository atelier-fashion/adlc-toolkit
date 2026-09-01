---
id: LESSON-604
title: "A spec's Retrieved Context is frozen at spec time — re-run retrieval at implementation time or you will rediscover a lesson captured in the gap"
component: "adlc/proceed"
domain: "adlc"
stack: ["markdown", "claude-skills"]
concerns: ["knowledge-capture", "retrieval", "developer-experience", "process"]
tags: ["retrieval", "lessons", "retrieved-context", "staleness", "knowledge-loop", "proceed", "phase-4"]
req: REQ-593
created: 2026-08-31
updated: 2026-08-31
---

## What Happened

REQ-593's spec was written on 2026-08-27 and carried a `## Retrieved Context` block listing
15 prior lessons and specs — the retrieval snapshot taken when `/spec` ran. Implementation
began on 2026-08-31.

During implementation, a `case` statement written inside a `$( )` command substitution
turned out to be a **syntax error in bash and `sh` that zsh accepts silently**. It was
caught by the dual-shell test harness, diagnosed, and fixed — perhaps twenty minutes of
work, most of it spent proving which shells were affected.

That work was entirely redundant. `LESSON-582-bash32-case-inside-command-substitution.md`
already existed, documented the failure in more depth than the rediscovery reached
(including the measured shell matrix and the reason macOS `/bin/bash` is still 3.2.57), and
prescribed three fixes. It was captured on **2026-08-28** — one day *after* REQ-593's spec
froze its Retrieved Context, and three days before implementation.

The retrieval was not broken. It was simply answering a question asked four days earlier.

## Lesson

**The Retrieved Context block is a snapshot with a timestamp, not a live view.** Any lesson
captured between spec authoring and implementation is invisible to a pipeline that reads
only the spec — and that window is exactly when the most relevant lessons appear, because
concurrent REQs in the same sprint are capturing lessons about the same surfaces.

Practical form: **before writing code, re-run retrieval for the surfaces you are about to
touch** — do not rely on the spec's block. It is cheap and narrowly scoped:

```sh
ls -t .adlc/knowledge/lessons/*.md | head -20        # what landed recently
grep -ril 'shell\|zsh\|bash' .adlc/knowledge/lessons/ # by surface, not by spec vintage
```

The heuristic that would have caught this: **sort the lessons directory by recency and
scan anything newer than the spec's `created` date.** Newer-than-the-spec is a small set,
and it is precisely the set the spec could not have seen.

## Why It Matters

The immediate cost is duplicated debugging — real but bounded. Two larger costs sit behind
it:

- **The knowledge loop silently fails to close.** ETHOS #2 says every implementation should
  leave the codebase smarter, and the payoff is that the *next* REQ does not repeat the
  mistake. If retrieval is only consulted at spec time, a lesson captured on Monday cannot
  protect work that specced on Sunday and builds on Thursday — the loop closes a cycle too
  late, and does so invisibly.
- **Near-misses look like successes.** Here the rediscovery was caught by a test. Had the
  harness been single-shell, the same gap would have shipped a file the project's own
  primary platform cannot parse — with a spec that looked diligently researched, because
  its Retrieved Context block was full.

The failure has no error mode. Nothing reports "a relevant lesson exists that you did not
read."

## Applies When

- Any pipeline phase separated from spec authoring by more than a day or two.
- Sprint runs where several REQs execute concurrently: sibling REQs are actively writing
  lessons about shared surfaces while you build.
- Resuming a paused, blocked, or long-running REQ — the older the spec, the staler its block.
- Reviewing a spec: a full Retrieved Context block is evidence retrieval *ran*, not evidence
  it is *current*. Check its date against the lessons directory.
