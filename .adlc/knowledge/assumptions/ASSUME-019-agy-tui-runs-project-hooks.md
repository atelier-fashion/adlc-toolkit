---
id: ASSUME-019
title: "`agy`'s TUI runs a project `.agents/hooks.json` as `agy -p` does"
status: unresolved
req: REQ-658
created: 2026-10-31
resolved:
---

## Assumption

REQ-658 declares `trust.mechanism: none` and assumes the rendered `SessionStart` hook reaches
an interactive session as it reached headless ones.

## Context

Every recorded run was `agy -p`, where a project hook ran with no trust record, in a
repository and in a linked worktree. The TUI has a trust dialog, and `trustedWorkspaces` is a
real setting, but the one attempt stopped at first-run onboarding, and finishing it writes
user settings. If the TUI gates the hook, ETHOS may not reach an interactive session until
the folder is trusted, and `trust` needs a mechanism and a README step. If it does not gate
it, the security follow-up in REQ-658's `## Deferred` applies to interactive sessions too.

## Resolution

Open. Owed by the `atelier-fashion` dogfood, which is the first interactive session on `agy`.
