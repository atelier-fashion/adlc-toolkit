---
id: ASSUME-022
title: "A multi-statement skill fence matches an allow entry under `claude -p`"
status: invalidated
req: REQ-659
created: 2026-11-01
resolved: 2026-11-02
---

## Assumption

The exec adapter's allow set carries `Bash(ADLC_TOOLKIT_ROOT=:*)` and the rendered
`Bash(if [ -f .adlc/partials/:*)`, assuming one of them lets a partial-sourcing fence run.

## Context

Since REQ-669 a fence opens with the ToolkitRoot line and holds several statements, so
`fence_broad_spelling` in `harness/claude.yml` still spells an opening no fence has. Whether
Claude matches a compound command as one string or statement by statement decides whether any
prefix entry can cover it. `fence-vs-allowlist` reads `unknown`. If neither matches, the first
fence ends the run `denied`, and the fix may need a broader shell entry than AC-26's reading of
REQ-659 allows.

## Resolution

False. Row `fence`: a multi-statement partial-sourcing fence was denied. Neither `Bash(ADLC_TOOLKIT_ROOT=:*)` nor `Bash(if [ -f .adlc/partials/:*)` admits it, so every skill fence halts `denied` under `--exec` until the engine allows them or runs them another way.
