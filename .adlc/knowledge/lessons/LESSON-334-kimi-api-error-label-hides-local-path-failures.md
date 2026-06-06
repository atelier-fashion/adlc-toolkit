---
id: LESSON-334
title: "Kimi delegation 'api-error' is a catch-all that hides local path/budget failures — use duration_ms to discriminate"
component: "adlc/tools/kimi"
domain: "adlc/tools"
stack: ["python", "shell"]
concerns: ["observability", "cost", "debuggability"]
tags: ["ask-kimi", "telemetry", "api-error", "duration_ms", "batch-degradation", "delegation", "spec-step-1.6"]
req: BUG-080
created: 2026-06-06
updated: 2026-06-06
---

## What Happened

A user reported "an error running the ADLC when it comes to using Kimi" and
asked whether the connection was broken. The connection was fully healthy
(key, SDK, `kimi-k2.5`, live round-trip all fine). The real cause: `/spec`
Step-1.6 handed `ask-kimi` the top-15 knowledge-doc paths, one of which was
stale, and `ask-kimi` aborted the whole batch on the first unreadable path
(fixed in BUG-080). The skill caught the non-zero exit, fell back to a direct
Read, and emitted telemetry with `reason="api-error"` — which looked exactly
like an API/connection outage.

## Lesson

In the Kimi delegation skills (`/spec` Step-1.6, `/analyze` Step-1.5/1.6) the
telemetry resolver maps **every** non-zero `ask-kimi`/`kimi-write` exit to
`reason="api-error"` (`spec/SKILL.md:181-182`) and replaces the tool's real
stderr with a generic "ask-kimi failed" line. So `api-error` means only
"exited non-zero", not "the API failed". To find the true cause:

1. **Read `duration_ms` in `~/Library/Logs/adlc-skill-telemetry.log`** — it is
   the discriminator:
   - `0` (sub-second) → a pre-flight guard tripped: an unreadable/missing
     `--paths` entry, or a missing key. **Not** the API.
   - `2000`–`4000` → empty completion: the token budget (`--max-tokens`) was
     too small; `kimi-k2.5` spends output tokens on reasoning before emitting
     visible text.
   - `100000`–`250000` → a genuine slow/oversized-corpus API error or timeout.
2. **Run the failing `ask-kimi` invocation directly** to see its real stderr
   (`not a readable file: …`, `empty completion …`, an HTTP error) — the skill
   swallows it.

Design corollary (the BUG-080 fix): a batch CLI given many inputs should
**degrade — skip the bad input with a warning and proceed** — not abort
all-or-nothing on the first bad one. One stale path should never nullify 14
good ones.

## Why It Matters

Without this, a trivial local problem (one moved doc, one small token budget)
is misread as an external outage. You waste time checking the API, key, and
network — all healthy — while the delegation silently stops saving tokens
(every fallback re-reads full doc bodies into the main context at full cost).
The misleading label plus the discarded stderr is what makes it expensive to
diagnose.

## Applies When

- Debugging any ADLC Kimi delegation failure, or a `mode:"fallback"`,
  `reason:"api-error"` entry in the skill-telemetry log.
- Reviewing or building batch-style CLIs/tools that take many inputs: prefer
  skip-with-warning over abort-on-first-bad-input, and make telemetry preserve
  the underlying error rather than collapsing distinct failures into one label.
