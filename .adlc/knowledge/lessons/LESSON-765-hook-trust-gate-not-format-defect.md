---
id: LESSON-765
title: "A hook can be well-formed and still never run — read the harness's own hook inventory before treating a failed hook probe as a format defect"
component: "adlc/harness"
domain: "adlc"
stack: ["codex-cli", "json", "toml"]
concerns: ["portability", "harness-agnostic", "silent-failure", "security"]
tags: ["hooks", "trust", "review", "multi-harness", "probe", "capability", "worktree"]
req: REQ-655
created: 2026-10-31
updated: 2026-10-31
kind: domain
evidence: "REQ-655 requirement.md Assumptions, Hook record, commit b589039: adlc harness probe codex read hooks-loaded fail and session-start-context fail; codex app-server hooks/list showed the same .codex/hooks.json discovered with trustStatus untrusted; a codex exec run with hooks.state.<key>.trusted_hash in the user config fired SessionStart and SubagentStart and both reached the model, and a run without it fired nothing and warned of nothing."
confidence: low
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

REQ-655's first full probe said Codex's `SessionStart` hook did not load and its output did not reach the model, with `hooks` listed stable and on. The file's location and shape were right. Codex keeps a second gate behind folder trust: each project hook reads `untrusted` until a person reviews it, the approval is pinned to the hook's absolute path and content hash, and `codex exec` skips an unreviewed hook without a word. Reviewed, the same hook worked.

## Lesson

When a hook does not fire, ask the harness what it thinks of the hook before changing the file: list its hooks and read each one's status. A harness can discover a hook and decline to run it, so "did not fire" is not evidence about format, and folder trust is not evidence about a hook. Where approval is keyed by absolute path, treat every clone and every linked worktree as unapproved, and keep any path that must work there free of the hook.

## Why It Matters

Reading the failure as a format defect would have sent the fix at a correct file. Reading the capability as absent would have told Codex users there is no ETHOS injection at all. And flipping `subagent_start_hook` on the strength of a reviewed run would have removed the one ETHOS path that survives `/proceed`'s own worktrees.

## Applies When

A hook, rule or config a harness should load has no visible effect, a probe of one reads `fail`, or an adapter is about to declare a capability that depends on a project-level file. Check it before writing the renderer and before declaring the capability.
