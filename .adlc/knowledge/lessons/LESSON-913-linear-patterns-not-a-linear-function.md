---
id: LESSON-913
title: "Linear patterns do not make a linear function: whatever runs once for each hit and reads the line from its start is quadratic, so the scaling test has to time the whole call"
component: "adlc/tools/dataset"
domain: "adlc"
stack: ["python", "regex"]
concerns: ["performance", "testing", "correctness"]
tags: ["quadratic", "per-hit-work", "prefix-slice", "string-rebuild", "end-anchor", "final-newline", "scaling-test", "whole-function"]
req: BUG-298
created: 2026-11-24
updated: 2026-11-24
kind: domain
evidence: "BUG-298, fixed in b467fa0. After BUG-297 every credential pattern in tools/dataset was linear and tested one pattern at a time, and Scrubber.scrub_line was still quadratic on a line of DenyList names, where no pattern is slow: 1.4 s for 8,000 names in 40,000 characters. Three things ran once for each hit: a search for a pipe and blanks at the end of the line cut at the hit (is_prose in detectors.py, _named in residue.py), a sentence-start pattern over the line up to the hit (scrub.py), and _replace_spans building the line again for each span (x18.8 alone). tools/dataset/tests/test_dataset_line_linear.py::test_bug_298_line_is_linear_in_its_length times the whole of scrub_line and scan_line: 41 of its 119 cases fail without the fix, at x8.2 to x16.5, and all pass with it."
confidence: high
enforcement: test:tools/dataset/tests/test_dataset_line_linear.py
generalizes: []
supersedes: []
---

## What Happened

BUG-295 and BUG-297 made the credential patterns linear and added a scaling test for each
pattern: two sizes, a ratio. Those tests passed, and one long line could still take the
export seconds. BUG-298 was opened for two address patterns. Timing the two entry points
themselves, on every line family, showed a second cause that no pattern-level test could
see.

On a line with many hits, the code asked a question about each hit by reading the line from
its start:

- Is this name in a table cell? `re.search(r"\|[ \t]*$", line[:start])`. The slice copies
  the line up to the hit, and the search tries every pipe in it.
- Does this person's name begin a sentence? A pattern run over `line[:start]`.
- Replace the spans: for each span, build `line[:s] + replacement + line[e:]`.

Each is linear for one hit and each pattern is fast. With a number of hits that grows with
the line, each is quadratic. The measured cost of the whole function on such a line was the
same shape as the pattern bug's.

The fix answers each question by reading backwards from the hit and stopping at the first
character that settles it, and builds the replaced line once from a list. Both old patterns
ended in `$`, which also matches before a final newline (LESSON-898), so each backwards read
steps over one final newline first. Without that step the new code differs from the old on
the last hit of a line that still has its line ending.

## Lesson

A scaling test on each pattern shows the patterns are linear. It does not show the function
is. Time the entry point that callers use, on lines where the number of hits grows with the
length, and keep that test beside the pattern ones.

When reading code that loops over matches, look for work per match that depends on the
match's position and not on its size:

- a slice from the start of the line (`line[:start]`), or to its end;
- a `search` or `match` on such a slice, above all one anchored with `$` or `^`;
- a string rebuilt inside the loop;
- `count`, `index`, `lstrip` or a `sum` over the part before the match.

Replace each with a read that starts at the match and stops early, or with one pass that
carries the answer forward. When the read replaces a pattern, write down what the pattern's
anchors accepted (`$` before a final newline, `^` under MULTILINE) and compare old against
new at every position of real and random lines, not only at the hits.

## Why It Matters

The pattern tests gave a false all-clear twice. A fix that is scoped to "the slow patterns"
measures what the bug report names and stops, while the function the user waits on is still
quadratic on an input that is ordinary for it: a long table row, a line of names.

## Applies When

Fixing or reviewing a backtracking bug in code that also loops over the matches. Writing
scaling tests for a scrubber, a linter, a tokenizer or any line-by-line pass. Replacing a
pattern that ends in `$` with hand-written string code.
