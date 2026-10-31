---
id: LESSON-766
title: "Ask a harness's own inspection commands first — most capability questions about it need no model session"
component: "adlc/harness"
domain: "adlc"
stack: ["codex-cli"]
concerns: ["portability", "harness-agnostic", "cost"]
tags: ["multi-harness", "probe", "capability", "introspection", "evidence", "model-quota"]
req: REQ-655
created: 2026-10-31
updated: 2026-10-31
kind: domain
evidence: "REQ-655 commit b589039, requirement.md Assumptions: codex execpolicy check read git push origin --force as allow under allow [git, push]; codex debug prompt-input measured the 17-skill catalog in a throwaway HOME; codex app-server hooks/list showed trustStatus; the binary's embedded post-compact.command.output schema has no additionalContext. None took a model session, while three live runs spent on -c trust overrides showed only that the overrides do nothing."
confidence: low
enforcement: none
generalizes: [LESSON-755]
supersedes: []
---

## What Happened

Investigating Codex for REQ-655, the answers that decided the adapter came from the tool itself and cost nothing: its rule evaluator, its prompt renderer, its app server's hook inventory, the JSON schemas embedded in its binary. The sessions that cost quota mostly confirmed what those had shown, or tested a setup that a zero-cost check could have ruled out first.

## Lesson

Before spending a model session on a harness question, list what the harness can answer without one: `--help` on every subcommand, debug and doctor verbs, an app server or JSON-RPC surface and its generated schema, and `strings` over the binary. Use those to fix the question, then spend a live run only on what must be seen end to end, and check the setup with a zero-cost read first. A live run is still what proves a capability; inspection decides which run is worth making.

## Why It Matters

Each probe session is the operator's plan quota and a model's cooperation, which is why a probe can read `unknown` for reasons unrelated to the harness. An evaluator's answer is deterministic and repeatable, and it names the mechanism, which a model's narrated result does not.

## Applies When

Writing or amending a harness adapter, investigating a failed probe, or recording a harness capability, and before driving a TUI or starting a batch of live runs.
