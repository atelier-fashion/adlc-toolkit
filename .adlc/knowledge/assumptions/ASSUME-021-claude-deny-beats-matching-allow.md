---
id: ASSUME-021
title: "`--disallowedTools` beats a matching `--allowedTools`, and a tool in neither tier is denied under `claude -p`"
status: validated
req: REQ-659
created: 2026-11-01
resolved: 2026-11-02
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

Holds. Row `deny-over-allow`: an added deny matching the same command as an allow won, and the origin did not move. Row `outside-tier`: `chmod`, in neither tier, was denied under `-p`, not prompted for. BUG-260 found the tiers themselves leaking: a prefix allow admitted `<branch> main` and `<branch> --force`, and the operator's settings file widened them; both are fixed.
