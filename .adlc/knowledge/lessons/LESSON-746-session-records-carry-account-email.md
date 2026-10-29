---
id: LESSON-746
title: "Claude Code session records carry the account email — a credential redaction chain is not enough for a committed transcript"
component: "adlc/tools/adlc/harness_probe"
domain: "adlc"
stack: ["python", "claude-code", "jsonl"]
concerns: ["privacy", "security", "data-exposure"]
tags: ["redaction", "email", "transcript", "fixture", "session-context", "committed-artifact"]
req: REQ-664
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "REQ-664 TASK-175: the first live adlc harness probe claude run wrote .adlc/research/harness-probes/fixtures/claude.jsonl with the account email in a session_context attachment record, which the intake.sh chain (no email arm) let through; harness_probe.EMAIL_RE in scrub() removed it, and tools/adlc/tests/test_harness_probe_e2e.py::test_transcript_fixture_redacted now plants an email in the fake's session record and asserts none survives (PR #210, 62079e9)."
confidence: high
enforcement: test:tools/adlc/tests/test_harness_probe_e2e.py
generalizes: []
supersedes: []
---

## What Happened

REQ-664 copies the first records of a real harness session file into the repo as a
fixture for the P5 transcript parsers, redacted with the toolkit's five-pattern
credential chain. Claude Code 2.1.258 writes the user's email into its session
records, in an `attachment` of type `session_context`. The chain matches keys and
tokens, not addresses, so the first live fixture held the email.

## Lesson

Anything that commits harness-written records (transcripts, session files, hook
payloads, raw stdout) needs an identity pass, not just a credential pass. Redact
email addresses at minimum, and look at what the harness actually writes before
trusting a chain built for a different input. Keep the credential chain itself
unchanged and pinned; add the extra pass beside it.

## Why It Matters

The fixture is meant to be committed and the toolkit repo is shared, so the leak
would ship with the PR. Nothing in the existing chain or its parity tests would
ever flag it.

## Applies When

Writing a tool or a test fixture that persists a harness's own output (session
JSONL, transcripts, hook payloads) into a repository, or reusing a redaction chain
on a new kind of input.
