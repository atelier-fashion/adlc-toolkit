---
id: ASSUME-017
title: "Codex loads `~/.codex/rules/adlc.rules` alongside a project's `.codex/rules/adlc.rules`"
status: unresolved
req: REQ-655
created: 2026-10-31
resolved:
---

## Assumption

REQ-655 renders the three delegation `allow` rules into the user-level rules file and the
routine and deny tiers into the project's, under the same file name, and assumes that a
trusted project loads both, with neither shadowing the other.

## Context

`adlc harness install --harness codex` writes the user-level file only with delegation
installed, and the doctor's `codex-rules` row compares it with a fresh render. Every live
run in REQ-655 loaded project rules only, and `codex execpolicy check` takes the files it is
given, so it says nothing about which layers a session loads. If the two files shadow each
other, the delegation rules move to the project file and the doctor row follows.

## Resolution

Open. Owed by the live run listed in REQ-655's `## Deferred`.
