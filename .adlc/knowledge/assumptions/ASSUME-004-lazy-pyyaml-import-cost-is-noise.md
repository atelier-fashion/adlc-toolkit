---
id: ASSUME-004
title: "A lazy PyYAML import adds roughly thirty milliseconds to the gate probe"
status: validated
req: REQ-609
created: 2026-09-01
resolved: 2026-09-02
---

## Assumption

Parsing the config with PyYAML instead of a hand-written reader would cost on
the order of thirty milliseconds per `adlc-read --print-gate`, which against
REQ-603's 104-second median delegated step is noise; and `--help` would pay
nothing because the import is lazy.

## Context

REQ-603 had measured the probe at 21 ms and had tightened its budget; REQ-609
BR-1 required the import to be lazy and AC-12 required the cost to be measured
rather than asserted.

## Resolution

Validated, smaller than assumed. Twenty runs each with the venv interpreter:
`--print-gate` median 21.2 ms on `main` (`e70a1f1`) → 25.5 ms on the branch,
+4.3 ms, 0.004% of one delegated step; `--help` unchanged at ~20 ms (a poisoned
`yaml` module on `PYTHONPATH` proves it is never imported there). Recorded in the
REQ's Assumptions with the command used.
