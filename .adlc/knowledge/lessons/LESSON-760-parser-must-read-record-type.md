---
id: LESSON-760
title: "A transcript parser must allow record types, not sniff for message shape: Claude Code's api-request-blob records looked like Human turns"
component: "adlc/tools/delegate"
domain: "adlc"
stack: ["python", "jsonl", "claude-code"]
concerns: ["privacy", "correctness", "security"]
tags: ["extract-chat", "transcript", "api-request-blob", "delegation", "fixtures", "redaction", "email"]
req: REQ-660
created: 2026-10-30
updated: 2026-10-30
kind: domain
evidence: "REQ-660 ADR-6 and TASK-203: on one real session transcript the merge-base extract-chat produced 224,326 bytes with 18 system-reminder lines and 1 line holding an email address; after the type filter in tools/delegate/extract-chat it produced 105,016 bytes, 3 and 0. Pinned by the record-type tests in tools/delegate/tests/test_extract_chat.py."
confidence: high
enforcement: test:tools/delegate/tests/test_extract_chat.py
generalizes: [LESSON-746]
supersedes: []
---

## What Happened

`extract-chat` kept any record with a `message.role` of `user` or `assistant`. Newer Claude
Code versions write `api-request-blob` records whose `message` has role `user` and holds
injected context: CLAUDE.md text and the user's email. They came out as `## Human`
sections and went to the delegate. Hand-written tests never had such a record, because
their author only knew the shapes the parser already handled. Inspecting a real captured
session is what exposed it.

## Lesson

Parse a third party's log by an allowlist of record types, read before the payload, and
keep the path for records with no type at all so older transcripts still parse. Sniffing
for a useful-looking field accepts every future record that happens to share it. Build a
parser's fixture from a real capture, and read every record type in that capture, not just
the ones the fixture keeps.

## Why It Matters

The format is undocumented and changes between versions, and this output crosses a trust
boundary to a third-party endpoint. Redaction only catches credential shapes, so the
parser's filter is the real privacy control.

## Applies When

Writing or changing a parser over a harness transcript or any other undocumented
append-only log, especially when its output leaves the machine.
