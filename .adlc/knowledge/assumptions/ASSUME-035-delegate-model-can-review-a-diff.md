---
id: ASSUME-035
title: "The delegate endpoint's model is capable enough to review a diff against a spec in the cross-family line grammar"
status: unresolved
req: REQ-722
created: 2026-11-25
resolved:
---

## Assumption

The model behind the delegate endpoint, `kimi-k2.6` by default, can read a redacted diff
with 25 lines of context, the changed-files list and a spec's numbered BRs and ACs. It can
answer in REQ-722's tab-separated grammar (`FINDING` and `RULE` lines), with findings that
survive `cross_family.py validate` often enough to be worth the call.

## Context

REQ-722 adds a reviewer from a different model family to `/proceed` Phase 5 and relies on
that model for every cross-family finding. The only evidence before the REQ was the REQ-417
pre-pass, whose output is a looser candidate list. BR-13's run-outcome counts (`crossFamily`
status, findings, drops, declines) exist to measure this, rather than assume it.

## Resolution

Unresolved at close-out. In REQ-722's own run the review never reached the model. This
machine's delegate config declares no `family`, so the dogfood run skipped with
`family-unknown`. Every delegate call in the session (the pre-pass, two `/spec` reads and the
`/wrapup` draft) returned 429 (rate limit or quota). To resolve it, set
`delegate.family: moonshot` in `~/.claude/adlc/config.yml`. Then read the `crossFamily` counts
on the run-outcome lines of the next few full-lane REQs: findings kept against dropped, and
how many survived consolidation.
