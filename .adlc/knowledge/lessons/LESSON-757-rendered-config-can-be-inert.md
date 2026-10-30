---
id: LESSON-757
title: "A rendered config can parse, pass every gate and do nothing — read how the consumer treats unknown keys and output before you render for it"
component: "adlc/harness"
domain: "adlc"
stack: ["json", "yaml", "copilot-cli", "cursor"]
concerns: ["portability", "harness-agnostic", "security", "silent-failure"]
tags: ["multi-harness", "inert-config", "unknown-keys", "hook-output", "additional-context", "vendor-docs", "deny", "render"]
req: REQ-656
created: 2026-10-30
updated: 2026-10-30
kind: domain
evidence: "REQ-656 requirement.md Reconciliation, commit e0b0e7f: the spec had .cursor/permissions.json carry identical allow and deny content to cli.json, but that file's documented keys are terminalAllowlist, mcpAllowlist and autoRun and unknown keys are ignored, so the deny would have been inert and read as enforced; the hook set printed ETHOS as plain stdout, which Copilot's hook reference says is not injected. Both came from comparing the plan's survey with the vendor pages on 2026-10-30, not from a live run; no CLI was available."
confidence: medium
enforcement: none
generalizes: [LESSON-755, LESSON-716]
supersedes: []
---

## What Happened

A survey said two files were the Cursor allowlist, and the spec rendered one content into
both. It also rendered a plain-stdout hook for Copilot, because that is what Claude Code
accepts. Each output would have been valid JSON or a working command, and every local
check would have passed. The first would have shown a `deny` the consumer ignores, which
is worse than showing nothing: it reads as a control. The second would have delivered no
context at all, silently, in every session.

## Lesson

A local gate proves your output matches your model of the consumer, not that the consumer
reads it. Before writing a renderer for a format, read the consumer's own page for three
things: which keys it knows, what it does with one it does not, and how it takes output
(stdout, a JSON field, a return code). When a consumer ignores unknown keys, never copy a
security-relevant key into it on the strength of a sibling file. Render only what it reads,
and state the loss where the operator will see it.

## Why It Matters

Silent failure is the worst mode for a permission or an injected constitution: nothing
errors, and the file reads as though the control is in place.

## Applies When

Writing a renderer or adapter for another tool's config or hook format, or reusing one
tool's output contract for a tool that merely reads the same file.
