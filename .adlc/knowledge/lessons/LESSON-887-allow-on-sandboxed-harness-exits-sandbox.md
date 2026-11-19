---
id: LESSON-887
title: "On a sandboxed harness an allow rule is an exit from the sandbox, not a pre-approval: render only what has to leave"
component: "adlc/harness"
domain: "adlc"
stack: ["python", "yaml"]
concerns: ["security", "harness-agnostic", "unattended"]
tags: ["codex", "exec-engine", "sandbox", "allowlist", "fence-run", "declared-residual", "multi-harness"]
req: REQ-662
created: 2026-11-18
updated: 2026-11-18
kind: domain
evidence: "REQ-662: .adlc/research/harness-probes/codex-exec-manual.md:26 and :27 (an allowed `touch` wrote outside the working copy, an un-allowed write did not, on codex-cli 0.166.0), ASSUME-032, and the Phase-5 security and correctness findings on the merged branch, which rated the unsandboxed routine allows and the fence runner's git environment the main risk; merged in 81af28f as declared residuals."
confidence: high
enforcement: none
generalizes: [LESSON-796]
supersedes: []
---

## What Happened

REQ-662 rendered the whole routine tier of `templates/permissions.yml` as allows into Codex's exec rule file, as it does for Claude. On Claude an allow means "runs without a prompt". On Codex under `--sandbox workspace-write` a command no rule names already runs without a prompt, inside the sandbox, and a command an allow names runs outside it. So the allows for `ls`, `cat`, `git status`, `sed` and `cp` bought nothing and took those commands out of the sandbox, and the allows that execute their arguments (`git rebase -x`, `npx`, `find -exec`) became unsandboxed code. Two reviewers rated it the main risk. It shipped as a declared residual with a follow-up requirement.

## Lesson

Before rendering an allowlist for a harness, find out what an allow does there. Where the harness sandboxes what it does not recognise, an allow is the list of commands that leave the sandbox, so start from nothing and add only what must leave (network, a write outside the working copy). Design that at architecture time: a tier written for a harness with no sandbox carries the wrong meaning across.

## Why It Matters

The sandbox reads as containment while the rule file quietly removes it for sixty commands. The loss is invisible in tests, because an allowed command "working" is the expected result.

## Applies When

Adding or changing an exec adapter, a permissions render, or an allow entry for a harness that has a sandbox mode; reviewing a claim that a sandbox bounds what a model can do.
