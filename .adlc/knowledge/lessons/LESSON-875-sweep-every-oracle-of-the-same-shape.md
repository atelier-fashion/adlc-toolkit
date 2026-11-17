---
id: LESSON-875
title: "When one oracle gets a proof-of-submission rule, sweep every oracle of the same shape in the same change: each one left out fails later, one live run at a time"
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "testing"]
tags: ["harness-probe", "proof-of-submission", "oracle", "codex", "retry", "sweep"]
req: BUG-281
created: 2026-11-17
updated: 2026-11-17
kind: process
evidence: "REQ-707 (LESSON-847) required proof of submission for runner-prefix only. BUG-280 (46a64bc) found codex's ask-tier-deny pass in #269 came from a model that never submitted the command. BUG-281 (d354f9e) found the trust gate's allowlist-loaded read fail the same way and voided the full codex run on fc62320. Each was a separate live run; test_refusal_rows_need_proof_of_submission and test_trust_gate_skip_is_not_a_failed_allowlist fail before d354f9e."
confidence: high
enforcement: test:tools/adlc/tests/test_harness_probe_unit.py
generalizes: [LESSON-847]
supersedes: []
---

## What Happened

LESSON-847 added a rule for `runner-prefix`: a refusal counts only with proof the command was submitted. The probe had other rows whose negative reading meant "the harness refused": `ask-tier-deny`, the trust gate's `allowlist-loaded`, `git-write-*` and the older fence variants. None of them got the rule.

Codex's model, which often skips commands it expects to be blocked, then found each gap in turn:
- an `ask-tier-deny` pass recorded on `main` that measured nothing (BUG-280);
- a trust gate whose skip voided a whole run (BUG-281).

Each cost a live run, a bug and a PR.

## Lesson

**A rule about what counts as evidence is a property of the oracle's shape, not of the one row where the failure showed up.** When adding it, list every decision site whose reading has that shape and apply the rule to all of them in the same change.

Here the shape was "a negative reading from an absent effect, meaning the command was refused". Sort each site by what its negative means:
- **Refused:** needs proof of submission.
- **Ran with the wrong result:** needs no submission proof, but must not be confused with refused.
- **Asked nothing:** unaffected.

## Applies When

Fixing a probe, test oracle or validator after a false reading, in a module with several decision sites. It matters most when the failure came from the model's behaviour rather than the harness's, because the same behaviour will reach every row it can.
