---
id: ASSUME-010
title: "Claude Code needs no workspace trust for project-local config"
status: invalidated
req: REQ-664
created: 2026-10-29
resolved: 2026-10-29
---

## Assumption

The multi-harness plan's §1 row "Project-local config needs a trusted path" reads
"no" for Claude Code, and REQ-657's trust enum gives Claude `none`. REQ-664 built
its claude profile on that: no trust entry, no flag.

## Context

`adlc harness probe` writes only the user-level files BR-4 lists (codex's and
gemini's trust entries, gemini's policy file), so it cannot trust a workspace for
Claude even if Claude needs it. REQ-655, REQ-656, REQ-657 and REQ-662 build their
Claude adapters and exec launches on the same assumption.

## Resolution

Invalidated for project `permissions.allow` on Claude Code 2.1.258. The first live
probe run (REQ-664 TASK-175, `.adlc/research/harness-probes/claude.json`) printed,
on every launch: "Ignoring 1 permissions.allow entry from .claude/settings.json:
this workspace has not been trusted … set projects[...].hasTrustDialogAccepted:
true in ~/.claude.json". Whether hooks and skills are also gated was not
observable, because the CLI was not logged in. Claude's trust is a
user-config-entry in `~/.claude.json`. Updating the plan and REQ-657's enum, and
deciding whether BR-4 may write that file, are follow-ups.
