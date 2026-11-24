---
id: LESSON-908
title: "A regex copied from sed or grep into Python or JavaScript keeps its text and loses its cost: time the copy at two line lengths, and bound every repeat that can start anywhere in a long run"
component: "adlc/tools/adlc/credential-redact"
domain: "adlc"
stack: ["python", "javascript", "shell", "regex"]
concerns: ["performance", "security", "availability", "testing"]
tags: ["regex-portability", "backtracking", "quadratic", "redos", "posix-ere", "credential-redaction", "scaling-test", "parity-test", "bounded-repeat"]
req: BUG-295
created: 2026-11-24
updated: 2026-11-24
kind: domain
evidence: "BUG-295, fixed in 6ac492e: tools/adlc/tests/test_credential_redact.py::test_bug_295_chain_is_linear_in_line_length times each chain at 10,000 and 40,000 characters in a child process. On main at da5b465 its first failure read `INTAKE_PATTERN on capitals and underscores took 0.2664 s at 10000 characters and 4.2469 s at 40000: x15.9 for x4 the input`, and ten cases did not finish in 45 s. On the same lines macOS sed -E and grep -E, which run the same text, were linear before the fix: 0.011 s and 0.040 s at 80,000 characters. With the three repeats bounded every case passes. The parity test that holds the Python text equal to the shell text passed throughout."
confidence: high
enforcement: test:tools/adlc/tests/test_credential_redact.py
generalizes: [LESSON-735]
supersedes: []
---

## What Happened

The toolkit's credential chains were written as POSIX EREs for `sed -E` and `grep -E`. Three
later REQs copied them into engines that backtrack: Python's `re` for the dataset scrub and
the harness probe, and JavaScript for the Space. Each copy came with a parity test that holds
its text equal to the shell text, and LESSON-735 had already recorded that such a copy must
keep sed's matching rules as well as its syntax.

No test asked what a copy costs. Three arms have a repeat that can start at any character of
a long run and is followed by something a line usually lacks: the name before `_API_KEY`, the
identifier on each side of an assignment keyword, and a JWT's header. macOS `sed` and `grep`
read such a line once. Python and V8 re-read the run from every start. One line of 80,000
capitals and underscores took Python 17 seconds, a line of the word `token` repeated did not
finish at 5,000 characters, and the same lines took `sed` a hundredth of a second.

The first sign was a workaround, not a test: a later tool scanned long lines in 2,000-character
windows to stay fast, and so missed any credential longer than a window.

## Lesson

The text of a regular expression says what it matches. It does not say what it costs, and
the cost belongs to the engine. `sed -E` and `grep -E` on macOS run an automaton and are linear
in the line. Python's `re` and JavaScript's engines backtrack, and for them a repeat that can
start anywhere in a run, followed by something that is usually absent, is quadratic in the
run. Two such repeats around a fixed word are cubic.

So a regex that moves from one engine to another needs two tests, and a parity test is only
the first:

- **Same matches.** Hold the copy equal to its source, as LESSON-735 says.
- **Same growth.** Time the copy on one adversarial line per repeat at two lengths, and assert
  the ratio: four times the input may cost at most eight times the CPU. Linear gives 4 and
  quadratic 16, so the threshold has a factor of two on each side. Never assert a time. Run
  the timing in a child process with a limit, because the unfixed pattern may not return.

To build the adversarial line, take the characters the repeat accepts and leave out what must
follow it: for `[A-Z_]+_(API_KEY|TOKEN)`, a long run of capitals and underscores with no
assignment after it. Add the fixed word repeated (`token` over and over) when the repeat sits
beside a keyword.

To fix one, bound the repeat (`{1,64}`), so each start costs a constant. Do it in the source
and in every copy, so the parity test still holds. Three limits come with the bound:

- POSIX guarantees a repeat count only up to 255, and macOS `grep` refuses 256. Something
  longer than that (a JWT header) needs a second arm that reads its last 255 characters.
- An ERE has no lookbehind. An arm anchored on "not preceded by an identifier character"
  consumes that character and misses a match that sits straight after a letter. An exact
  count needs no anchor.
- A bounded repeat costs an automaton engine a constant factor on the adversarial line
  (macOS `grep`: 0.04 s to 1.3 s at 80,000 characters). Measure the engine that was already
  linear too, and bound only the copies a backtracking engine reads when the others are held
  byte-identical elsewhere.

## Why It Matters

A redaction chain reads text it does not control: a pasted log, a recording, a transcript.
One long line of ordinary identifier characters stops the tool that reads it, with no error
and no output, and the usual response is a workaround at the call site (a window, a length
cap) that makes the redaction miss what it was written to find. The parity test stays green
through all of it, which is why three separate copies shipped with the same cost.

## Applies When

Copying a regular expression between engines: sed, grep or awk into Python, JavaScript, Ruby,
Java or PCRE. Writing or reviewing a pattern with a repeat that is not anchored at a boundary
and is followed by a required literal. Reviewing a parity test between two copies of a regex,
which says nothing about time. Seeing a call site that chunks, windows or truncates its input
before a regex.
