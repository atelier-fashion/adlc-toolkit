---
id: ASSUME-021
title: "`--disallowedTools` beats a matching `--allowedTools`, and a tool in neither tier is denied under `claude -p`"
status: unresolved
req: REQ-659
created: 2026-11-01
resolved:
---

## Assumption

REQ-659 launches `claude -p` with the routine tier and the deny tier as flags, assuming a deny
takes precedence over any allow, and that a tool outside the allow tier is denied rather than
prompted for.

## Context

`.adlc/research/harness-probes/claude.json` reads `ask-tier-deny` `unknown`, because the CLI was
not logged in. The Claude adapter's one `deny_under_allow` record is the grandfathered `confirm`
one, which does not carry to a hard deny, so the exec-scope render drops every allow that would
wrap a deny and `exec.allow_extra` adds spellings that wrap none. The tiers are defense in depth
either way: the structural gates are the ledger, the pinned merge and the exit checks.

## Resolution

Open. Owed to a logged-in run, in REQ-659's `## Deferred`.
