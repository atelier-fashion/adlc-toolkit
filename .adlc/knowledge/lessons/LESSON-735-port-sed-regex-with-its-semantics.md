---
id: LESSON-735
title: "A sed regex ported to JavaScript must keep sed's matching rules, not just its syntax: one line at a time, and the longest match across alternatives"
component: "adlc/space"
domain: "adlc"
stack: ["javascript", "sh", "sed"]
concerns: ["security", "correctness", "redaction"]
tags: ["regex-portability", "posix-ere", "leftmost-longest", "credential-redaction", "parity-test"]
req: REQ-670
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "REQ-670 Phase 5: the build translated partials/intake.sh's redaction chain with [[:space:]] as \\s and ran it as one JS regex. The correctness review reproduced GITHUB_TOKEN: at a line end redacting the next line's first word (sed left it alone), and the security review reproduced AKIA..._API_KEY=secret leaving the secret unredacted (sed redacted the whole token). Fixed per line with longest-match across alternatives, pinned by space/tests/intake.test.js test 'redaction matches the real sed chain, line for line' against adlc_intake_redact, merged in 2724699."
confidence: high
enforcement: "test:space/tests/intake.test.js"
generalizes: [LESSON-716]
supersedes: []
---

## What Happened

REQ-670's Hugging Face Space runs `/spec` intake's credential-redaction chain in
the browser. The chain is a `sed -E` expression in `partials/intake.sh`, and the
build extracted it and translated its POSIX classes to JavaScript. The first
translation was syntactically right and semantically wrong in two ways. Every
single-line test passed.

- `[[:space:]]` became `\s`. sed reads one line at a time, so its class never sees a
  newline. A JS regex over the whole source does, so `GITHUB_TOKEN:` at the end of a
  line swallowed the next line's first token, and the line count drifted.
- One JS regex takes the **first** alternative that matches at a position. sed takes
  the **longest** match (POSIX leftmost-longest). For `AKIA…_API_KEY=secret`, the
  `AKIA` arm matched first and the `_API_KEY=` arm never ran, so the secret was sent.
  sed redacted all of it.

## Lesson

When you move a regex from sed, grep or awk into a JS-style engine, port the
**matching rules** as well as the syntax. Apply it per line, and when the pattern
has top-level alternatives, try each one at every position and keep the longest.
Translate POSIX classes to classes that exclude the newline, and fail the build on
any class the table does not cover. Then prove the port with a parity test that runs
the **original tool** on the same inputs, including multi-line input and inputs where
two alternatives overlap. Single-line fixtures cannot see either difference.

## Why It Matters

A redaction port that differs from the original fails silently. It over-redacts, which
corrupts the text, or it under-redacts, which leaks the secret it exists to remove.
Its own tests still pass, because they were written against the port.

## Applies When

You reuse a regex across engines or tools: a shell `sed`/`grep -E` pattern in JS or
Python, a POSIX ERE in a PCRE-style engine, or one canonical pattern read by several
readers. This applies especially when the pattern has alternatives, uses POSIX
classes, or guards secrets.
