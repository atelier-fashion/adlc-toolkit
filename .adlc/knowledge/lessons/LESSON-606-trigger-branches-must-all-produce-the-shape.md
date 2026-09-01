---
id: LESSON-606
title: "A multi-condition trigger is only as good as its weakest branch — check that EVERY condition produces the artifact downstream steps require"
component: "adlc/spec"
domain: "adlc"
stack: ["markdown", "bash", "claude-skills"]
concerns: ["correctness", "requirements", "review"]
tags: ["business-rules", "trigger-conditions", "enum-coverage", "dead-branch", "spec-review"]
req: REQ-594
created: 2026-08-31
updated: 2026-08-31
---

## What Happened

REQ-594's BR-1 activates intake on **any of three** conditions: (a) an explicit
`--intake` flag, (b) the argument resolving to a readable file path, or (c) the argument
exceeding 25 lines.

Every step after activation — segmentation, the budget check, the delegated read,
re-reading a segment the delegate omitted — takes a **file path**. Conditions (a) and (b)
hand one over. Condition (c), text pasted directly into the prompt, does not.

So the whole of trigger (c) died one step after it fired:

```
detect  rc=0  reason=lines  path=[]
segment rc=2  "source not readable: <empty>"
```

Nothing in the spec was self-contradictory. BR-1 was a coherent rule, BR-12 was a
coherent rule, and both were implemented faithfully. The defect lived in the seam: the
set of things that can *start* the process was wider than the set of things that can
*survive* it. Both the spec's own review and the architecture validation missed it,
because each rule reads correctly on its own.

## Lesson

When a rule enumerates alternative trigger conditions — an `any of` list, an enum, a
union type, a set of accepted input shapes — do not stop at "is each condition
well-defined?" Ask the harder question:

> For **each** branch independently, does it produce the exact artifact the next step
> consumes?

Trace one branch at a time, end to end, and treat a branch that reaches a different
data shape than its siblings as a defect until proven otherwise. The fix here was to
normalize at the boundary: `adlc_intake_detect` now materializes pasted text to a real
file, so `ADLC_INTAKE_PATH` is always a file on the intake path and every later step is
uniformly file-based. Normalizing once at the entry point is almost always cheaper than
teaching every downstream step to handle two shapes.

## Why It Matters

This class of gap is invisible to the reviews most likely to be run. Rule-by-rule
review passes, because each rule is fine. Happy-path testing passes, because the
example everyone reaches for is the file case. It surfaces only when someone exercises
the *least convenient* branch — which, for a trigger list, is usually the last one
written.

The acceptance criteria did not catch it either: they covered the negative case (a
one-line request must not trigger intake) and the file case, but no AC exercised
trigger (c) end to end. An enumerated trigger deserves an AC per branch.

## Applies When

- Reviewing a spec or BR that says "activates when ANY of" / "accepts one of".
- Implementing a dispatcher, parser, or gate with several accepted input shapes.
- Writing acceptance criteria for a rule with alternative conditions — one AC per
  branch, not one AC for the convenient branch.
