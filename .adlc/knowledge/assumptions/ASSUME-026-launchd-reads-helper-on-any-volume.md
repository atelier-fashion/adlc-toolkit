---
id: ASSUME-026
title: "launchd can run the helper from any `<dir>` an operator picks"
status: unresolved
req: REQ-663
created: 2026-11-01
resolved:
---

## Assumption

The plist points at `<dir>/delegate-launchctl-setenv.sh`, assuming launchd can read that path at
login wherever `<dir>` is.

## Context

Not tested on a removable volume, which may not be mounted at login, or under a TCC-protected
folder such as `~/Documents`, where launchd's access is unverified. A home that is simply missing
fails loud at the pointer, by design (BR-8), but a helper launchd cannot read would only fail in
its log, leaving delegation without its key after a reboot. BR-2 does not refuse either location.

## Resolution

Open. Named in REQ-663's `## Owed`. A real run on such a volume would settle it.
