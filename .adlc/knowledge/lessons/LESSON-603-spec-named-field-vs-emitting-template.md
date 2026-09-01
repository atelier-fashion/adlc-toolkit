---
id: LESSON-603
title: "A spec that names a frontmatter field is stating a belief, not a fact — check it against the template that actually emits the field"
component: "adlc/bugfix"
domain: "adlc"
stack: ["markdown", "bash", "claude-skills"]
concerns: ["correctness", "maintainability", "silent-failure"]
tags: ["frontmatter", "spec-accuracy", "task-template", "parser", "attribution", "measure-dont-assume", "test-fixtures", "cross-reference-rot", "adversary-report", "stale-artifact"]
req: REQ-593
created: 2026-08-31
updated: 2026-08-31
---

## What Happened

REQ-593 built a derivation that resolves a `TASK-yyy` id to its parent REQ by reading the
task file's frontmatter. As drafted on 2026-08-27, the requirement stated *"each TASK file
carries a `req:` frontmatter field"* — in the Description and again in an acceptance
criterion. The adversary report written the same day attacked the spec on other grounds and
repeated the same claim.

It is not true. The canonical `templates/task-template.md` emits `parent:`, not `req:`.
Measured across the repo at implementation time:

| frontmatter field | task files |
|---|---|
| `parent:` | **157** |
| `req:` | 6 |

An implementation faithful to that wording would have resolved 6 of 163 task files and
silently returned `attribution: none` for the other 96% — the exact benign-looking failure
the feature exists to eliminate.

**The spec was corrected before implementation began.** A `/validate` pass on 2026-08-31
caught it as a blocker and landed the fix in PR #132 (`701de4c`): the Description, BR-10,
and AC-1 were changed to `parent:`, BR-10 gained an explicit `parent:`-first-then-`req:`
fallback rule for the six legacy REQ-258/REQ-380 files, and a new AC pinned that legacy
case to a named fixture file. The `/sprint` pipeline branched from a `main` containing that
commit, so **the spec it built against already said `parent:`.**

Two things still went wrong, and they are the durable part of this lesson.

**The stale sidecar outlived the correction.** `adversary-report.md` was not updated when
the requirement was — by design, since a report is a historical record of one pass. But it
sits in the same spec directory and is read alongside the requirement, so the corrected-away
premise stayed on disk in an authoritative-looking artifact. The implementing pipeline
rediscovered the `req:`/`parent:` problem independently, then attributed it to the
requirement — which by then said the opposite. The first version of this lesson recorded
that misattribution as fact.

**The test fixture used `req:` only.** The parser read both spellings as BR-10 required, but
no fixture exercised the dominant path. The 96% case was untested, and a later
"simplification" dropping the `parent:` arm would have gone green. This was found in Phase 5
by checking the premise against the filesystem rather than re-reading the spec — and it is
the one finding here that the `/validate` gate did **not** already catch.

## Lesson

**When a spec names a field, a status value, a filename, or a directory shape, treat it as
a claim to verify, not a fact to build on.** One `grep -c` against the artifacts that
actually exist settles it, and costs seconds:

```sh
grep -rl '^req:'    .adlc/specs/*/tasks/*.md | wc -l   # 6
grep -rl '^parent:' .adlc/specs/*/tasks/*.md | wc -l   # 157
```

Two corollaries that carry most of the value:

1. **Read the producer, not just the consumer.** The authority on what a file contains is
   the template or code that writes it. Checking `templates/task-template.md` would have
   settled this before a line of parser was written.
2. **Fixture the dominant case, not the documented one.** Accepting both spellings is only
   half a fix; until a fixture exercises the 96% path, the code that serves it is untested
   and one refactor from silently disappearing.
3. **A correction to a requirement does not propagate to the sidecars beside it.** The
   adversary report, the retrieved-context list, and any review notes in the spec directory
   are snapshots of one moment. When a gate corrects the requirement, those artifacts keep
   asserting the old premise in the same authoritative voice, from the same directory. Read
   the requirement as current and everything beside it as dated — and when reporting what a
   spec "said", cite the version you actually built against, not the neighbour you also read.

An adversary pass repeating the spec's own claim is not corroboration. Both were written
from the same reading of the same document — a shared premise inherited, not independently
checked. The converse bites too: once the requirement is fixed and the report is not, the
report becomes the sole surviving carrier of the very claim that was refuted.

## Why It Matters

This failure mode is quiet in the worst way. The derivation would not crash, log, or
return an error; it would return "no attribution found", which is a **legitimate,
expected outcome** for a bug whose cause predates the trailer convention. A benign-looking
result is indistinguishable from a broken one, so the feature could have shipped, been
used, and produced almost nothing — with no signal that anything was wrong.

The cost compounds with the corpus: every bug processed while the parser was wrong is a
permanently missing edge, because nothing re-derives attribution for already-closed bugs.

## Applies When

- A spec, ADR, or review comment asserts the *name* of a field, status, id format, or path.
- Writing a parser or extractor against artifacts a template generates — check the template.
- A rule's "not found" branch is a valid outcome rather than an error: it can absorb a
  wholesale parsing failure without ever looking wrong.
- Choosing test fixtures: pick the shape that dominates real data, and only then the shape
  the documentation describes. When they differ, fixture both and let the test record the
  discrepancy.
- Reading a spec directory that contains an `adversary-report.md`, a Retrieved Context list,
  or review notes alongside the requirement — especially when the requirement has been
  corrected at a gate since those were written (see [[LESSON-604]]).
- Writing up what a spec "said" after the fact: quote the revision you built against, and
  check whether a gate corrected it between drafting and implementation.
