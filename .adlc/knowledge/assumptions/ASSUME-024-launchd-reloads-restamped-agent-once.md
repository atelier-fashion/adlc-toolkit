---
id: ASSUME-024
title: "`bootout` then `bootstrap` reloads the real agent from the re-stamped plist, once"
status: unresolved
req: REQ-663
created: 2026-11-01
resolved:
---

## Assumption

The migration re-stamps the plist and reloads it with `launchctl bootout gui/<uid> <plist>`, then
`launchctl bootstrap`, assuming the real agent ends up loaded exactly once, running the helper from
the new home.

## Context

AC-2 asks for this, and `launchctl` loads agents only in a real login session, so a sandbox `HOME`
cannot show it. The tests use a stub, which proves the order of the calls and that the plist is
stamped and passes `plutil -lint`. If the reload fails on a real machine, the migration warns and
carries on, as `tools/delegate/install.sh` does, and doctor's `launchctl` check reports it.

## Resolution

Open. Owed to a real run on a real machine, in REQ-663's `## Owed` (AC-2).
