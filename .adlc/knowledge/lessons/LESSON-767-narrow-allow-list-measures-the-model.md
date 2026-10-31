---
id: LESSON-767
title: "Where a refused tool ends the run, a narrow allow list measures the model's habits, not the harness"
component: "adlc/harness"
domain: "adlc"
stack: ["antigravity-cli", "python"]
concerns: ["portability", "harness-agnostic", "testing", "cost"]
tags: ["multi-harness", "probe", "allowlist", "headless", "auto-deny", "model-quota", "control"]
req: REQ-658
created: 2026-10-31
updated: 2026-10-31
kind: domain
evidence: "REQ-658 commit 31bc467, tools/adlc/harness_probe.py prep_allow and .adlc/research/antigravity-compatibility.md: git-write-worktree read fail with command(git commit) and command(git push) allowed, because the model ran git status first and agy -p ended the run at that refusal; the same probe with read-only prep_allow read pass, and the bare remote's ref advanced. test_antigravity_prep_allow_is_not_a_tested_command holds the two apart."
confidence: low
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

REQ-658's first probe run allowed only the commands each probe tests, which was enough on the harnesses REQ-664 was built on. On `agy -p`, a tool that would need a prompt ends the whole run, with exit 0 and an empty response, and only a hard `deny` lets the model carry on. The model looked around first in most launches (`git status`, `ls -la`, `mkdir -p`), so 8 of the 18 launches ended before the command under test ran, and `ask-tier-deny` lost its controls that way.

## Lesson

Before a batch of probe launches, find out what the harness does at the first refused tool. Where a refusal ends the run, every launch must allow the read-only look-around a model does unprompted, and that set must be kept apart from what any probe tests, or a control stops being a control. Spend one launch on the riskiest probe before spending the batch: the same failure would have shown in the first launch.

## Why It Matters

The verdicts read as harness facts, and they were facts about the model's habits. The quota was spent before the flaw showed, so three probes stayed unreadable and a 17-launch re-run had to be recorded as owed. A required gate needed its own extra launch.

## Applies When

Writing a probe profile or a harness-specific allow list, adding a harness whose headless mode cannot prompt, or running any scripted batch where each launch is a model session.
