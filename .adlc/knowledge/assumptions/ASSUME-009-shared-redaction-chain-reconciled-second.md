---
id: ASSUME-009
title: "Two in-flight REQs carrying one regex can agree that whichever lands second drops its copy"
status: validated
req: REQ-648
created: 2026-10-29
resolved: 2026-10-29
---

## Assumption

REQ-648's spec assumed that REQ-671's `tools/adlc/credential_redact.py`
`INTAKE_PATTERN` is the same five-arm chain as `tools/delegate/emit-telemetry.sh`'s
`sed` line. It also assumed that the REQ landing second could switch to the other's
copy without a behavior change, so neither REQ had to wait for the other.

## Context

REQ-648's run-outcome emitter needs the credential chain in Python. REQ-671 was adding
the toolkit's one Python copy at the same time. Carrying two copies is the drift
LESSON-441 warns about. Blocking either REQ on the other would have serialized two
unrelated features.

## Resolution

Validated. REQ-671 merged first (#205). REQ-648, second, replaced its local copy with
a by-path load of `credential_redact.py` (commit 99de3fd, squashed into f3e8f05,
PR #211). `test_redaction_parity_with_emit_telemetry_sed_chain`, which runs the real
`sed` line, passed unchanged against the new source, and so did REQ-671's own
`test_credential_redact.py`. The agreement only worked because both specs and both
architecture documents named the reconciling actor ("whichever lands second") before
either branch merged.
