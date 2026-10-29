---
id: LESSON-744
title: "Credential redaction chains match inside ordinary identifiers — validate identifier fields by format instead of redacting them"
component: "adlc/tools/delegate"
domain: "adlc"
stack: ["python", "bash", "regex"]
concerns: ["correctness", "security", "observability"]
tags: ["redaction", "credential-regex", "false-positive", "telemetry", "class-slug", "kebab-case"]
req: REQ-648
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "tools/delegate/tests/test_run_outcome.py::test_class_slug_survives_redaction first asserted that redaction leaves its 29-character fixture class (it begins task-ordering-race) unchanged, and failed with ta[REDACTED]: the chain's sk- arm takes any sk- followed by 20 or more word characters, which the tail of task- supplies. REQ-648 BR-6 exempts finding classes from redaction and validates them by format instead (commit ad71d1e, squashed into f3e8f05, PR #211)."
confidence: high
enforcement: test:tools/delegate/tests/test_run_outcome.py
generalizes: []
supersedes: []
---

## What Happened

The run-outcome record redacts free-text values with the toolkit's five-arm credential chain before writing them. The `sk-[A-Za-z0-9_-]{20,}` arm matches any `sk-` followed by twenty or more of those characters. That includes the tail of ordinary kebab-case words: `ta` + `sk-ordering-race-in-fixture`, `ri` + `sk-…`, `di` + `sk-…`. A test written on the assumption that redaction leaves such a slug alone failed with `ta[REDACTED]`.

## Lesson

Redaction chains are tuned for recall over prose, so they over-match structured identifiers. A field whose format you control (an id, a class name, a slug, an enum) should be **validated by a regex that admits no credential shape** and then written as-is, never passed through redaction. Redact only free text you cannot constrain. Over a field you count or join on, a redaction false positive is not cosmetic: identical `[REDACTED]` values merge distinct things and manufacture a false recurrence.

## Why It Matters

`/sprint`'s Recurrence report counts exact class equality. Redacting classes would have turned unrelated defects into one `ta[REDACTED]` class "seen in k REQs", the opposite of the signal it exists to give.

## Applies When

- Running a credential-redaction regex over values that are later grouped, counted, joined or used as keys.
- Designing a telemetry or export record: decide per field whether it is free text (redact) or a constrained identifier (validate).
- A redaction test asserts a benign value is unchanged: check the chain's arms against kebab and snake identifiers first.
