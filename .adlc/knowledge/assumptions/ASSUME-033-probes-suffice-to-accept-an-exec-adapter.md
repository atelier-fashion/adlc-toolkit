---
id: ASSUME-033
title: "The REQ-664 probes are enough to accept an exec adapter, so the adapter requirement needs no runs of its own"
status: invalidated
req: REQ-662
created: 2026-11-18
resolved: 2026-11-18
---

## Assumption

REQ-662 assumed that every fact an exec adapter rests on is measured by `adlc harness probe <name>` (REQ-664), and stated that the requirement "runs no experiment of its own".

## Context

BR-11 makes the probe result the acceptance gate, recomputed at every launch. Stage 1 (Codex) was designed on the committed `codex.json`, which read acceptable on every required probe under `context_delivery: prompt`.

## Resolution

Invalidated on codex-cli 0.166.0 by the stage's real launches (`.adlc/research/harness-probes/codex-exec-manual.md`). The probes stayed green while two things they do not measure broke or changed the design: the runner line the prompt prints did not match Codex's prefix allow (a bare `#`; fact 1), and `codex exec` writes a lasting trust entry by itself (fact 2). Resume from another working copy, the main checkout's `.codex/` and the absence of an approval flag were also settled only by real runs (facts 5 to 7).

The gate stays the probe result. What changes is that each stage also owes a recorded real run with the engine's own argv, environment and rendered files, and a rerunnable script for it (`tools/adlc/tests/e2e/codex-exec-live.py` is the first). REQ-664 has an open item for a `runner-prefix` variant whose command holds a `#`.
