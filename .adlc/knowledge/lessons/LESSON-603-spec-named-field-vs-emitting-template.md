---
id: LESSON-603
title: "A spec that names a frontmatter field is stating a belief, not a fact — check it against the template that actually emits the field"
component: "adlc/bugfix"
domain: "adlc"
stack: ["markdown", "bash", "claude-skills"]
concerns: ["correctness", "maintainability", "silent-failure"]
tags: ["frontmatter", "spec-accuracy", "task-template", "parser", "attribution", "measure-dont-assume", "test-fixtures"]
req: REQ-593
created: 2026-08-31
updated: 2026-08-31
---

## What Happened

REQ-593 built a derivation that resolves a `TASK-yyy` id to its parent REQ by reading the
task file's frontmatter. Both the requirement and the adversary report that attacked it
stated the same thing: *"each TASK file carries a `req:` frontmatter field."* The spec said
it twice; an acceptance criterion was written around it.

It is not true. The canonical `templates/task-template.md` emits `parent:`, not `req:`.
Measured across the repo at implementation time:

| frontmatter field | task files |
|---|---|
| `parent:` | **157** |
| `req:` | 6 |

An implementation faithful to the spec's wording would have resolved 6 of 163 task files
and silently returned `attribution: none` for the other 96% — the exact benign-looking
failure the feature exists to eliminate.

The parser happened to read both spellings, but the **test fixture used `req:` only**. So
the dominant real-world case was unexercised, and a later "simplification" that dropped
the `parent:` arm would have gone green. The gap was found in Phase 5 by checking the
spec's premise against the filesystem rather than re-reading the spec.

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

An adversary pass repeating the spec's own claim is not corroboration. Both were written
from the same reading of the same document — a shared premise inherited, not independently
checked.

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
