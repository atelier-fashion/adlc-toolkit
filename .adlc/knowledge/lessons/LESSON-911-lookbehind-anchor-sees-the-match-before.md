---
id: LESSON-911
title: "A lookbehind that anchors a repeat to the start of its run keeps a search's answer and can change a substitution's: the search resumes where the last match ended, and the lookbehind still sees it"
component: "adlc/tools/dataset"
domain: "adlc"
stack: ["python", "regex"]
concerns: ["performance", "security", "correctness", "testing"]
tags: ["backtracking", "quadratic", "lookbehind", "anchored-repeat", "bounded-repeat", "alternation", "substitution", "credential-redaction", "scaling-test"]
req: BUG-297
created: 2026-11-24
updated: 2026-11-24
kind: domain
evidence: "BUG-297, fixed in 46df645. The key-like assignment arm of tools/dataset/detectors.py EXTRA_CREDENTIAL was made linear by starting it only at the start of a run of name characters, behind a lookbehind. With that alternative alone, a hex run followed by an assignment (forty zeros, a, then _token= and a value) substitutes to one [REDACTED] and leaves _token= and its value in the text; with the bounded second alternative it substitutes to two, as the old pattern did. tools/dataset/tests/test_dataset_credential_linear.py::test_bug_297_what_the_bounds_change holds that line. The same anchor in tools/dataset/residue.py, where the patterns are only searched, gave no difference in 900,000 fuzzed lines. In the same file, the scaling case EXTRA_CREDENTIAL on a run, token, then blanks passed against the unfixed pattern while its run was the letter a, and failed at x15.8 once the run was the letter x."
confidence: high
enforcement: test:tools/dataset/tests/test_dataset_credential_linear.py
generalizes: [LESSON-908]
supersedes: []
---

## What Happened

BUG-295 made the shared credential chains linear by bounding each repeat that could start
anywhere in a long run (LESSON-908). The dataset export's own patterns had the same fault and
no shell original, so a lookbehind was available: let the repeat begin only where the
character in front is outside its class, and each run is read once, at any length, with no
bound to change what a long name or a long header matches.

For the residue pass that was the whole fix. Its patterns are only searched, and whether a
run matches does not depend on where in the run the engine starts.

For the scrub it was not. The scrub substitutes with one alternation of eight arms. After an
arm matches, the search goes on from the end of that match, and four of the arms can end in
the middle of a run of name characters: a hex run before a letter past `f`, a `bearer` value
before an underscore. The old assignment arm matched from that point. A lookbehind at that
point looks back into the match that has just been replaced, sees a name character, and
refuses. The assignment and its value stay in the text. The arm needed a second alternative
for a start that is not the start of a run, and that one has to be bounded.

One scaling test also passed against the unfixed pattern. Its line was a long run of the
letter `a`, then a keyword, then blanks, and `a` is a hex digit: the hex arm took the whole
run as one match before the slow arm could read it twice.

## Lesson

Where a pattern has no copy in an engine without lookbehind, anchoring a repeat to the start
of its run is better than bounding it: nothing past a bound stops matching. Whether the
anchor is safe depends on how the pattern is called.

- **Searched for a yes or no** (`search`, `any`): the anchor is exact when the answer for a
  run does not depend on the start. Put what the run must hold in a lookahead behind the
  lookbehind, then read the whole run. The match may begin earlier than it used to, which
  nothing reads.
- **Substituted or iterated** (`sub`, `subn`, `finditer`): a later match can begin where an
  earlier one ended. If any arm of the same pattern can end inside the anchored arm's run,
  the lookbehind refuses a start the old pattern took. List the arms that can end there. If
  there are any, keep a second, bounded alternative for a start that is not the start of a
  run. It runs at every other character, so it must cost a constant.

Fuzz the old pattern against the new with inputs that glue one match straight onto another.
Random lines of separate tokens do not reach this.

When a scaling test times a whole alternation, check that each of its lines fails against the
unfixed pattern. Another arm can take the run in one match and hide the arm under test. A
filler letter that is also a hex digit or a base64 character does this.

## Why It Matters

The failure is silent and in the unsafe direction. A redaction that used to replace two
things replaces one, the tests written from separate examples still pass, and what is left
in the text is the assignment the arm exists to remove.

## Applies When

Replacing an unbounded repeat with a lookbehind-anchored one in a pattern used with `sub`,
`subn`, `finditer` or `split`. Changing one arm of an alternation whose other arms end on a
character class that overlaps it. Writing a scaling or equivalence test for one arm of a
larger pattern.
