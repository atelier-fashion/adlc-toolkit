---
id: LESSON-001
title: "Mitigate /proceed per-phase gating via Claude settings allowlist + softened skill language"
component: "adlc/proceed"
domain: "adlc"
stack: ["claude-code", "bash", "gh-cli"]
concerns: ["developer-experience", "automation"]
tags: ["permissions", "pipeline", "auto-mode", "allowlist"]
req: ""
created: 2026-04-21
updated: 2026-04-21
---

## What Happened

Running `/proceed` end-to-end was prompting for permission at nearly every step — every git, gh, npm, Write, Edit, and Agent dispatch triggered Claude Code's default permission prompt. The pipeline's ~50+ tool calls across 8 phases made it feel like the user was gating every step of the ADLC loop. The skill itself also contributed: eight `**Status update**: Report "X" before continuing` blocks and a handful of explicit "surface to the user" instructions made the model read routine reporting as pause points.

## Lesson

Per-phase gating in long-running Claude Code skills has **two** root causes that must be addressed together:

1. **Missing `permissions.allow` in `~/.claude/settings.json` and per-repo `.claude/settings.json`**. Without an allowlist, every routine operation fires a prompt. Ship a repo-level `.claude/settings.json` that pre-approves git / gh / npm / test / agent-dispatch operations and keeps only destructive or production-impact operations (force-push to `main`, `rm -rf`, `gh pr merge`, `./deploy.sh`, `terraform apply/destroy`, `git reset --hard`) on the `ask` list. `defaultMode: "acceptEdits"` handles Write/Edit without explicit enumeration.

2. **Skill language that reads as pause points**. Wording like "Report X before continuing" or "Surface to the user" invites the model to stop. Rewrite these as explicit **End-of-phase log** blocks — single status lines emitted in-flight — and declare an explicit **Autonomous Execution Contract** at the top of any multi-phase skill enumerating the exact conditions that warrant halting. Everything else is a log.

Both fixes ship together. The allowlist alone doesn't stop the model from pausing voluntarily; the wording change alone doesn't stop the Claude Code harness from prompting.

## Why It Matters

A 15-prompt /proceed loop becomes a 0–3 prompt loop after both mitigations land. That difference is the practical gap between "I can run this unattended" and "I have to babysit every phase." For sprint orchestration (`/sprint`), this is the difference between viable parallel pipelines and serialized attention-tax.

## Applies When

- Designing any multi-phase Claude Code skill that runs end-to-end.
- Bootstrapping a new ADLC consumer repo via `/init` (the scaffolded `.claude/settings.json` is the retroactive fix).
- Debugging user reports of "Claude keeps stopping to ask me things" during pipeline runs.
- Writing new agent dispatches — frame multi-agent parallel blocks as a **single gate**, not N gates, to avoid inter-agent reporting.
