---
id: LESSON-016
title: "Substring-counted paren balance: project raw counts into orthogonal buckets, don't trust naive subtraction"
component: "adlc/tools/lint-skills"
domain: "adlc/lint"
stack: ["python"]
concerns: ["correctness", "false-positive", "verify"]
tags: ["lint", "shell", "substring-count", "balance", "verify"]
req: REQ-425
created: 2026-05-15
---

## Context

REQ-425 introduced a balance check that flags fenced shell blocks whose `$(`
opens exceed `)` closes (or `$((` opens exceed `))` closes). The original
attempt was a left-to-right paren matcher that decremented `single` on
every `)`. It worked on the unbalanced corruption fixture, then immediately
false-positived on the canonical REQ-424 telemetry literal:

```sh
duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))
```

That line contains: arithmetic `$((`, a literal `(...)` grouping, an inner
`$(date)`, then `* 1000` and `))`. A naive paren counter walking left to
right consumes the literal grouping's `)` as if it closed the `$(`, ending
the fence at single=-1 — a finding.

## Lesson

When you replace a stateful parser with a substring-count heuristic, the
buckets are NOT independent. `count('$(')` overcounts because `$((` contains
`$(` as a prefix. `count(')')` overcounts because `))` contains two `)`
characters. The fix is to project the raw counts:

```python
raw_single_open  = body.count('$(')
raw_single_close = body.count(')')
double_open      = body.count('$((')
double_close     = body.count('))')

single_open  = raw_single_open  - double_open
single_close = raw_single_close - 2 * double_close

single_deficit = max(0, single_open  - single_close)
double_deficit = max(0, double_open  - double_close)
```

The verify-pass review (correctness-reviewer + architecture-reviewer)
caught the original naive formula precisely because the test suite had
ONE happy-path fixture exercising a real telemetry block. Two takeaways:

1. **Substring counting is fine, but the projection matters.** A heuristic
   that "happens to work" by coincidental over-/under-count cancellation
   is a landmine.
2. **A regression-guard fixture for the failure mode you're DEFENDING is
   load-bearing.** The `kimi-gate-ok.md` fixture isn't an edge case — it's
   the canonical happy-path that any check on this pattern MUST tolerate.

## When this applies

- Any text-matching lint that counts opens/closes of constructs that share
  prefixes or suffixes.
- Whenever you replace a stateful parser with a simpler counter, write a
  fixture for the canonical happy path FIRST and assert clean output, then
  iterate on the corruption fixture.
- Whenever a reviewer claims "the math works out for the canonical case"
  but you haven't independently traced the arithmetic, trace it.

## See also

- REQ-424 — the corruption that motivated the lint.
- REQ-425 — this lint and its eventual fix.
- LESSON-012 — structural enforcement beats prose enforcement.
- LESSON-013 — BSD vs GNU silent grep failure (sibling class: a tool that
  "happens to work" on the inputs you tested).
