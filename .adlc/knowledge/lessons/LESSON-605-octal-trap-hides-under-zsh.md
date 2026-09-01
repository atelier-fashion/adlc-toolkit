---
id: LESSON-605
title: "The octal-arithmetic trap is shell-divergent — zsh accepts what bash rejects, so dogfooding under the executor shell alone certifies the bug"
component: "adlc/partials"
domain: "adlc"
stack: ["bash", "zsh", "sh"]
concerns: ["correctness", "portability", "testing"]
tags: ["octal", "shell-arithmetic", "zero-padding", "cross-shell", "dogfooding", "false-green"]
req: REQ-594
created: 2026-08-31
updated: 2026-08-31
---

## What Happened

REQ-594 added `adlc_intake_range <segment-number> <total-lines>`, which does arithmetic
on a segment number. Segments are labelled with zero padding — `S01`..`S40` — so the
natural call after reconciliation notices a missing `S08` is
`adlc_intake_range 08 4200`.

`$(( 08 ))` is an octal literal. That much is already LESSON-396. What LESSON-396 does
not say, and what this run found, is that **the two shells disagree about it**:

```
bash:  adlc_intake_range 08 4200  ->  "08: value too great for base (error token is \"08\")"
zsh:   adlc_intake_range 08 4200  ->  1401 1600        # silently accepted
```

zsh is the macOS Claude Code executor shell (LESSON-329). Every interactive smoke test
during implementation therefore passed. The defect was caught only because the Phase 5
reflection pass walked the lessons index, found LESSON-396, and probed the padded input
under *both* shells rather than the one the session happened to be running.

## Lesson

A cross-shell defect that only one shell reports is worse than one both shells report,
because the passing shell manufactures evidence of correctness. Two habits follow:

1. **Decimal-normalize any externally-shaped numeric token before arithmetic** — strip
   leading zeros with `sed -e 's/^0*//' -e 's/^$/0/'`, not `10#$n` (a bashism). This is
   LESSON-396's rule; the addition here is that its *symptom* is shell-dependent.
2. **When a value is formatted with zero padding anywhere in a feature, treat every
   consumer of that value as a suspect** and assert the padded form explicitly in tests
   under both shells. `partials/tests/run.sh` already runs each harness under bash and
   zsh; the gap was that the harness only ever passed unpadded integers, so the
   dual-shell runner had nothing divergent to disagree about.

## Why It Matters

The bug was invisible under the shell the work was being done in. Had it shipped, it
would have fired for the first time on a contributor's bash box, in a code path
(reconciliation of a delegate-omitted segment) that only runs when a delegate returns an
incomplete response — a rare, hard-to-reproduce branch. The cost of finding it there is
an order of magnitude above the cost of one probe during review.

The general shape — a formatter and a consumer that disagree, where the disagreement is
masked by the local environment — is not specific to octal.

## Applies When

- Any shell arithmetic on a value that was produced by `printf '%02d'`, read from a
  filename, parsed out of frontmatter, or otherwise externally shaped.
- Writing or reviewing a POSIX partial that must pass under both bash and zsh.
- Judging whether a passing local smoke test is evidence: ask which shell ran it, and
  whether the other one would agree.
