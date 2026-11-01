---
id: LESSON-786
title: "A refusal whose precondition the tool can itself remove is a one-way door: check at validation that every refusal leaves a remedy the operator can still run"
component: "adlc/validate"
domain: "adlc"
stack: ["markdown"]
concerns: ["reversibility", "developer-experience"]
tags: ["spec-validation", "refusal", "remediation", "preflight", "one-way-door"]
req: REQ-663
created: 2026-11-01
updated: 2026-11-01
kind: process
evidence: "REQ-663 spec Amendments, BR-9: --back refused when the backup was gone, and --prune-backup removes the backup, so a pruned machine could only go back by hand, in a feature named reversible. --back never read the backup, so nothing depended on the check. Amended at Phase 1; test_back_works_after_prune in tools/adlc/tests/test_migrate_back.py holds the amended rule."
confidence: low
enforcement: none
generalizes: [LESSON-572]
supersedes: []
---

## What Happened

REQ-663's spec had `--back` refuse unless the backup existed, as a parenthetical beside its real
point. Another rule let `--prune-backup` delete that backup, and BR-3 required every refusal to print
a copy-pasteable fix. Put together, the refusal had no fix to print.

## Lesson

When validating a spec, walk each refusal and ask two things: what the operator runs to clear it,
and whether another command in the same spec can remove what it checks for. A refusal with no
remedy is a one-way door, however safe it reads. Then ask what the check protects. Here nothing read
the backup, so the safe-sounding check protected nothing and removing it lost nothing.

## Why It Matters

A safety check that strands the operator is worse than none, because it fires only on a machine
already in trouble, when nobody can reach the author.

## Applies When

Validating or writing a spec with preflight refusals, a backup or prune command, or anything
described as reversible.
