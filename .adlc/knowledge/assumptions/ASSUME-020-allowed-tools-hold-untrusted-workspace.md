---
id: ASSUME-020
title: "`claude -p --allowedTools` holds in a workspace Claude has not trusted"
status: validated
req: REQ-659
created: 2026-11-01
resolved: 2026-11-02
---

## Assumption

The exec engine puts both tiers on the command line and writes no trust entry
(`exec.trust_grant: none`), assuming `--allowedTools` applies in an untrusted workspace.

## Context

ASSUME-010 was invalidated for a project's `permissions.allow`. A linked worktree resolves
Claude's trust at the main repo root, so a per-working-copy entry changes nothing, and an entry
on the root would be a repo-wide grant shared with the operator's sessions. The notice Claude
prints names only `.claude/settings.json`, even with `--allowedTools` passed. That is consistent
with the assumption and does not prove it, because no logged-out run reaches a tool call. If it
is false, the first tool call in a run in an untrusted repo is denied and the run halts `denied`.

## Resolution

Holds. On 2026-11-02 (`claude` 2.1.258, logged in) `tools/adlc/tests/e2e/claude-exec-live.sh` row `allow-engine-only` ran `git config user.name`, an allow only the engine's tier carries, in a never-trusted folder.
