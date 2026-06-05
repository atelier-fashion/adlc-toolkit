---
id: LESSON-331
title: "Closed output schemas silently rot when a new code path adds payload fields — extend the schema + add a pure structural test in the same change"
component: "adlc/sprint"
domain: "adlc"
stack: ["javascript", "claude-skills", "node-test"]
concerns: ["testing", "correctness", "schema", "maintainability"]
tags: ["closed-schema", "additionalProperties", "terminal-contract", "pure-test-gap", "workflow", "blocked-terminal"]
req: REQ-485
created: 2026-06-05
updated: 2026-06-05
---

## What Happened

REQ-485 added BlockHold fields (`conflictFiles`, `holdState`, `rebaseAttempts`, `resolvedBlocker`) to the `blocked()` terminal's `detail` payload in `workflows/adlc-sprint.workflow.js`. But the exported `TERMINAL.detail` schema is `additionalProperties:false` and only declared `{questions, reason, detail}`. Any consumer validating a returned terminal against the exported `TERMINAL` contract would have **rejected every self-healing rebase halt** the new code path emits. Nothing caught it during implementation: the emitting code lives in the runtime (non-pure) section of the script, which the `node:test` pure-loader (`_load-pure.js`) deliberately does not exercise — so the behavioral tests never ran that path. The Phase-5 review found it via the LESSON-330 BR→diff coverage cross-check; the fix extended the closed schema (with `holdState` as a closed enum) and added a pure structural regression test pinning schema↔payload.

## Lesson

A closed schema (`additionalProperties:false`) only protects you if **every emitting site is covered**. When a new code path returns a `blocked()`/`failed()` terminal — or any schema-validated object — with a **richer payload** than the original, you MUST, in the same change:

1. **Extend the closed schema** to declare the new fields (and constrain them — e.g. a closed enum for a state field).
2. **Add a pure structural test** that pins the payload against the schema (a declared-keys / sample-payload-validates check). The emitting code often lives in a runtime/non-pure layer that the pure-test loader skips, so behavioral tests won't exercise it — only a structural test that validates a representative payload against the exported schema will.

## Why It Matters

Closed schemas are a correctness tool, but they create an invisible maintenance coupling: every new payload field must be mirrored in the schema, or the object is silently rejected **at the consumer**, far from the emit site — fail-closed, no error at the source. Pairing "extend the schema" with "add a declared-keys structural test in the pure layer" converts that coupling from *remembered* to *enforced*. This is the schema analogue of LESSON-330 (omitted requirements caught by coverage cross-check) and LESSON-012 (structural enforcement over prose): make the invariant mechanical, because the author who added the field is exactly the one who won't notice the schema drifted.
