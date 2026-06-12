---
id: LESSON-393
title: "Escape-hatch validators must enforce every documented constraint — a half-enforced rule silently degrades a fail-loud guarantee"
component: "adlc/agents"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "configurability"]
tags: ["escape-hatch", "validation", "fail-loud", "model-aliases", "agents-render"]
req: REQ-516
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

REQ-516's tier render validates model values against a known-good alias set
(`opus`/`sonnet`/`haiku`/`inherit`), with a documented escape hatch for full
model ids defined as "hyphenated AND containing a version digit". The initial
regex enforced only the hyphen — so digitless typos like `claude-opus` or
`foo-bar` passed as "full model ids" instead of failing loud with the allowed
set. The Phase-5 verify caught it; the fix requires the version digit.

## Lesson

The escape hatch is exactly where a validator gets lenient, because its
purpose is to admit things outside the strict set — which makes it the spot
where every documented constraint must be enforced, not just the cheapest
half. When architecture or README states a two-part rule ("hyphenated AND
versioned"), the validator's test fixtures must include inputs that satisfy
one part but not the other; that's the case the regex author skips.

## Why It Matters

BR-7-style fail-loud guarantees ("a typo'd alias fails with the allowed set")
are only as strong as their weakest acceptance path. A half-enforced escape
hatch converts the most common user error — a typo that resembles a real
model name — into silent acceptance of a nonexistent model, the precise
failure mode the rule existed to prevent.
