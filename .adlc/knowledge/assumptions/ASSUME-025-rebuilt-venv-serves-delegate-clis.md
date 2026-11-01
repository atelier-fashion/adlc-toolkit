---
id: ASSUME-025
title: "A venv rebuilt from `requirements.txt` serves the delegate CLIs as the old one did"
status: unresolved
req: REQ-663
created: 2026-11-01
resolved:
---

## Assumption

The venv is not relocatable, so the migration rebuilds it at the new home from the pinned
`tools/delegate/requirements.txt`, assuming the rebuilt venv is equivalent for the toolkit's
purposes, so `adlc-read --version` reports the same `enabled` and provider values.

## Context

The tests run `python3 -m venv` and `pip` for real, but from a local wheel holding one
`yaml/__init__.py`, so the probe passes and no real dependency is installed. The pins and the
network path have never run through this code. A failed `pip` refuses before the flip, so the risk
is a rebuilt venv that installs and misbehaves, not a half-migrated machine.

## Resolution

Open. Owed to the same real run as AC-2.
