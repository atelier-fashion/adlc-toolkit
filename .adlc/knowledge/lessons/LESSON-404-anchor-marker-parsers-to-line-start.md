<!--
Filename MUST be `LESSON-xxx-slug.md`.
-->
---
id: LESSON-404
title: "Anchor structural-marker parsers to line start — a marker token that is also mentioned in prose will trip an unanchored search"
component: "adlc/tools/lint-skills"
domain: "adlc"
stack: ["python", "markdown"]
concerns: ["correctness", "false-negative", "structural-enforcement"]
tags: ["marker-parser", "regex-anchoring", "prose-mention", "sync-surfaces", "lesson-019", "REQ-525"]
req: REQ-525
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

REQ-525 added a sync-surface parity check that parses `<!-- sync-surfaces:
… -->` marker blocks out of `init/SKILL.md` and `template-drift/SKILL.md`.
The first implementation located the block with an unanchored `re.search`.
But each shipped SKILL.md *also* mentions the marker token in backticked
prose (a cross-reference explaining the contract) — so the unanchored search
could latch onto the prose mention instead of the real column-0 block and
parse an empty or wrong surface list, making the parity check vacuously
pass. Caught in the pipeline's own Phase-5 verify (the one Major finding of
the sprint) and fixed by anchoring the open/close regexes to start-of-line
(`^\s*`, and rejecting a leading backtick) plus a regression test with a
prose decoy.

## Lesson

1. **When a structural marker can be *documented* in the same file it
   structures, the parser must distinguish marker-as-syntax from
   marker-as-mention.** Line-start anchoring (and rejecting inline-code
   contexts) is the cheap, robust discriminator. Write the decoy test first:
   a file containing ONLY the prose mention must parse as "no marker".
2. **This generalizes LESSON-019** (guards rot when indirection moves):
   a guard also rots when its anchor token gains a second, non-structural
   occurrence. Documentation of the guard is itself an adversarial input to
   the guard.
3. **Self-verification earns its keep on self-referential tooling** — the
   defect was invisible to the test fixtures (which had no prose mentions)
   and was caught only because the verify pass ran the parser against the
   real tree, where the docs-with-mentions case actually exists.

## Why It Matters

A parity check that silently parses the wrong block reports `clean` forever —
the exact silent-false-negative class structural enforcement exists to
prevent (LESSON-012). The failure is invisible until the drift it should
have caught bites a consumer project.

## Applies When

- Writing any parser that extracts marker-delimited blocks from
  human-edited files (SKILL.md contracts, config fences, doc anchors).
- Reviewing regexes that locate structural tokens: ask "can this token also
  appear as prose/code-span in the same file?"
- Building fixtures: include a decoy file where the token appears only as a
  mention.
