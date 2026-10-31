---
id: ASSUME-018
title: "A hard `permissions.deny` beats an overlapping allow in `agy`, in the TUI as well as under `-p`"
status: unresolved
req: REQ-658
created: 2026-10-31
resolved:
---

## Assumption

REQ-658 renders the deny tier as a hard `permissions.deny` and assumes it holds wherever a
routine allow overlaps it, in an interactive session as well as under `agy -p`.

## Context

`deny_tier_render: {user: deny}` rests on two launches: `lone-deny`, and `deny-under-allow`,
where the target stayed absent under a matching `command(touch)` allow. The probe itself
reads `ask-tier-deny` `unknown`, because its `allow-only` controls ended early, so every
`deny_under_allow` record stays `unverified`. The omissions do not depend on this, because
`never_restore` keeps `git push`, `git branch` and `git -C` out of the allow set whatever the
record reads. The README's statement of the deny tier does.

## Resolution

Open. Owed by the 17-launch probe re-run and one deny-tier prompt in the TUI, both listed in
REQ-658's `## Deferred`.
