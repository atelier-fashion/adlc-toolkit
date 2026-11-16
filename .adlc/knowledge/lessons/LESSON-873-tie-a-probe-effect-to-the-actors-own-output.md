---
id: LESSON-873
title: "A probe effect built from two side effects can be met by two separate commands: tie it to the admitted command's own output, and never read a refusal from a step the shell runs before the command"
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python", "sh"]
concerns: ["correctness", "security", "testing"]
tags: ["harness-probe", "runner-prefix", "redirect", "sandbox", "codex", "oracle", "false-pass"]
req: REQ-707
created: 2026-11-16
updated: 2026-11-16
kind: domain
evidence: "REQ-707 amendment, Phase 5: the first draft's runner-redirect effect (runner sentinel and target both present) was shown by the correctness reviewer to be met by a sandboxed refusal plus a fallback stub run, and by the security reviewer to read refused when a directory sat at the target; fixed before merge, squash-merged as 02fb265 (the stub prints a marker once its sentinel is written, the effect is the target holding it, an unopenable target reads ask-split), confirmed by re-verify. test_fallback_stub_run_is_not_a_redirect_admission and test_redirect_runner_without_target_is_partial fail on the first draft."
confidence: high
enforcement: test:tools/adlc/tests/test_harness_probe_unit.py
generalizes: [LESSON-847]
supersedes: []
---

## What Happened

REQ-707's amendment moved `runner-redirect`'s target into the working copy so that codex's model would write it. The first draft judged admission by two files being present together: the runner's sentinel and the target. On codex, a refused line still runs inside the sandbox, and the shell creates the target there. A model that then runs the allowed stub on its own writes the sentinel. Two separate commands produced the pair, and a refusal read as an admission.

The draft also had the opposite flaw. It read "runner present, target absent, line on record" as a refusal. But the shell opens a redirect before the command starts. A directory placed at the target, or a target deleted afterwards, stops or hides an admitted line, and that would have read as a pass.

## Lesson

**An effect assembled from independent side effects proves only that each one happened, not that one command did both.** Tie the effect to the admitted command's own output. Here the stub prints a marker once its sentinel is written, and the redirect carries that marker into the target. A forged marker can only push the reading toward admission, the safe side.

**Before reading a refusal from an absent artifact, list what the shell does before the command runs.** Redirects, a missing directory, and a non-file at the path all fail before the command starts. Absence there is not a refusal: read it as `unknown`, and only read refused when no target exists or the target is an empty regular file.

## Applies When

Writing or reviewing a probe or test oracle that decides "admitted or refused" from files a command leaves behind. This matters most when a sandbox or a retry can run part of the line, or when the model can run related commands of its own.
