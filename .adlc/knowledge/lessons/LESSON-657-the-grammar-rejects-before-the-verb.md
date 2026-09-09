---
id: LESSON-657
title: "A static shell classifier rejects on characters before it reads the verb, and a reader with no file scans the root"
component: "adlc/skills"
domain: "skills"
stack: ["markdown", "sh"]
concerns: ["privacy", "developer-experience"]
tags: ["preamble", "provenance", "teton-code", "quoting", "redirection", "glob", "root-scan", "bug-220", "lesson-655"]
req: BUG-220
created: 2026-09-09
updated: 2026-09-09
---

## What Happened

LESSON-655 taught that Teton Code judges a preamble on every branch it could
take, and BUG-218 rewrote the ethos line to `test`/`cat`/`echo`. The line still
pinned the session, and so did every `## Context` preamble in every skill: the
REQ-614 grammar refuses the whole command, before looking at any verb, when it
contains one of `' " ` $ \ > < { } ! * ? [`. The quoted fallback message, the
`2>/dev/null`, the `*/requirement.md` glob and a `--format="…"` were each
enough on their own. Two more rules bit while rewriting: a content-reading verb
with no file argument (`| head -20`, `| grep -c .`) — or with a file that does
not exist — is scored as a read of the whole root, and that scan is bounded at
100k entries with no `target/` skip, which a built Rust repo exhausts.

## Lesson

Write a preamble against the classifier's grammar, not against a shell.
Unquoted `echo` messages, no redirects, no globs, no `~/`, no pipes into
readers, directory-scoped `grep` with `--include` spelled with a space. Then
prove each shape against the real classifier — a unit test in teton-code holds
every rewritten line and every old one — instead of reasoning about the
grammar from its docs. Fix the whole surface at once: one clean line in a
block of five gains nothing.

## Why It Matters

Every toolkit skill starts by pinning the session to the local tier, which on
a machine whose local tier is unavailable means every skill fails, and the
message names a cause the user cannot act on. The rewrite is mechanical once
the rules are stated; the cost is in not knowing them.

## Applies When

Adding or editing any `!`…`` preamble; a session pins with "shell syntax this
classifier does not model" or "reads the root"; choosing between `cat` and a
`test -s`/`ls` probe for an optional file; any consumer of a provenance
classifier whose rules are a denylist of characters rather than a lexer.
