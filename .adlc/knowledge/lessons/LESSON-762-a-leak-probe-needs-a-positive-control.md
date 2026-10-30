---
id: LESSON-762
title: "A leak probe needs a positive control — an empty sandbox can report clean because the write it hunts for skips silently"
component: "adlc/tools/adlc/tests"
domain: "adlc"
stack: ["python", "pytest", "sh"]
concerns: ["testing", "test-isolation", "silent-failure"]
tags: ["sandbox", "home-directory", "ledger", "leak-probe", "positive-control", "false-negative"]
req: REQ-546
created: 2026-10-30
updated: 2026-10-30
kind: domain
evidence: "BUG-256: pytest under an empty outer HOME left 0 files, but adlc_record_own_reservation skips when ~/.claude is missing, so the probe could not see the leak it was hunting. With ~/.claude present, unfixed origin/main left two req 700 lines in test_renumber.py and the fixed tree left none."
confidence: high
enforcement: none
generalizes: [LESSON-758]
supersedes: []
---

## What Happened

To check that no test suite wrote to the real home, a full run went under an empty outer
`HOME` and found no files left there. That result proved nothing: the reservation ledger
is written only when `~/.claude` already exists, so even the known leak stayed silent. The
probe had to be rerun with `~/.claude` in place, and with unfixed `main` as a control.

## Lesson

Before trusting a clean result from a leak probe, run it on the code known to leak and watch
it fire. Build the sandbox to look like the real thing: advisory writes often skip quietly
when their directory is missing, and an empty directory is the one state that hides them.

## Applies When

Claiming that a run left machine state untouched, or any check whose pass means "nothing
happened", where the same output would come from the check not being able to see anything.
