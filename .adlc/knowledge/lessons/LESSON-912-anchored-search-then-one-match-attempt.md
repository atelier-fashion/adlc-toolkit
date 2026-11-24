---
id: LESSON-912
title: "An anchored search can replace finditer exactly, with no bound: after each match, try the old pattern with match() at the one position where the iteration could begin again inside the run"
component: "adlc/tools/dataset"
domain: "adlc"
stack: ["python", "regex"]
concerns: ["performance", "security", "correctness", "testing"]
tags: ["backtracking", "quadratic", "lookbehind", "anchored-repeat", "finditer", "resume-position", "email-pattern", "scaling-test", "equivalence-fuzz"]
req: BUG-298
created: 2026-11-24
updated: 2026-11-24
kind: domain
evidence: "BUG-298, fixed in b467fa0. tools/dataset/residue.py _emails and tools/dataset/detectors.py emails search with the address pattern anchored to the start of its run, and after each match call the unanchored rule's match() at one position. With the anchor alone, the matches differed from the rule's finditer on 30% (residue) and 7% (scrub) of 300,000 seeded random lines built from address fragments; with the one attempt added, on none, and on none of 597,871 exhaustively built strings. A first version that tried the scrub's rule one character past the match was wrong: the fuzz found an address, then percent, plus and underscore, then a second address. tools/dataset/tests/test_dataset_line_linear.py::test_bug_298_an_address_that_begins_where_the_last_one_ended_is_still_found and ::test_bug_298_the_rules_are_tried_at_one_position_never_searched hold both."
confidence: high
enforcement: test:tools/dataset/tests/test_dataset_line_linear.py
generalizes: [LESSON-911]
supersedes: []
---

## What Happened

The dataset export's two address patterns were quadratic on a long run with no `@` in it: the
residue pass's had no anchor at all, and the scrub's had a lookbehind that left out the
underscore its repeat reads. Both are iterated, one for an allow-list check on each match and
one to replace each match, so LESSON-911 applied: a lookbehind that anchors the repeat to the
start of its run loses the address that begins where the last match ended. Two addresses
joined by an underscore are the scrub's case. An allowed address with another glued to it is
the residue pass's, and there the lost match is the one that should have refused the export.

LESSON-911's remedy is a second, bounded alternative for a start that is not the start of a
run. A bound moves a match with a local part longer than the bound, and here no match was
allowed to move: the scrub replaces the span, and the residue pass compares the matched text.

The bound was not needed. `finditer` begins again at one known position, where the last match
ended, and inside the run it has just left there is one position at most where the old
pattern could match next:

- The residue pass's pattern has no lookbehind, so that position is where the match ended.
- The scrub's pattern has its own lookbehind, which refuses every start whose character in
  front is in its class. Inside a run the only character outside that class is the
  underscore, so the position is just past the next underscore of the run.

So the fix keeps both patterns' text, searches with the anchored copy, and after each match
tries the pattern itself with `match(line, pos)` at that position before searching on. One
attempt reads the rest of the run once. Nothing is bounded, so nothing moves at any length.

This rests on a property of the pattern: the repeat must end at the end of its run, because
the character that follows it (`@`) is not in the class. A run then matches from one start
if and only if it matches from every start, and the anchored search finds the same runs.

## Lesson

When an iterated pattern (`finditer`, `sub`) is made linear by anchoring its repeat to the
start of a run, and no match may move, do not add a bounded alternative. Keep the old pattern
and call it with `match` at the single position where the iteration could begin again
inside the run:

1. Work out that position from the old pattern, not from the anchor: where the last match
   ended, moved forward to the first start the old pattern's own lookbehind allows.
2. Check that the repeat must end at the end of its run. If the pattern can stop a repeat in
   the middle of a run, a start can match where another does not, and this does not hold.
3. Never `search` or `finditer` the old pattern again. A test that counts the calls on it
   keeps the slow path from coming back.
4. Fuzz old against new with lines built from fragments of matches glued together, and with
   every character the two classes disagree on. The first guess at the position was wrong
   here, and only that fuzz showed it.

## Why It Matters

The bounded alternative trades a quadratic for a pattern that silently matches something
else past the bound. In a redaction or a residue check, a match that moves is text left in
or a refusal not made. The exact form costs one function and one extra pattern, and its
equivalence can be tested at every length.

## Applies When

Making a `finditer` or `sub` pattern linear with a lookbehind anchor, where the matched
spans or the matched text are used and must stay what they were. Reviewing a fix that adds a
bounded alternative beside an anchored one. Any pattern whose repeat reads a character that
its own lookbehind leaves out.
