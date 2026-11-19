---
id: LESSON-893
title: "Codex runs a chained line outside the sandbox only when every command on it has an allow: a tool that needs to leave the sandbox must check that it has"
component: "adlc/tools/adlc/fence-run"
domain: "adlc"
stack: ["python", "codex"]
concerns: ["correctness", "sandbox", "unattended"]
tags: ["codex", "sandbox", "prefix-rule", "fence-run", "compound-command", "lane-check", "exec-engine"]
bug: BUG-287
created: 2026-11-19
updated: 2026-11-19
kind: domain
evidence: "BUG-287, codex-cli 0.166.0: in launch 3 of .adlc/research/harness-probes/codex-exec-manual.md `python3 … && fence-run run …` failed with `cannot open …/FETCH_HEAD: Operation not permitted` and the lane check read check-error, while `git add … && git commit … && fence-run run …` pushed in launch 2. After fence_run.sandboxed (15b5cbc) launches 5 and 6 answered fence_run_sandboxed and the session reran the call. tools/adlc/tests/test_fence_run.py::test_bug287_a_real_sandbox_is_detected_through_the_cli runs it under sandbox-exec."
confidence: high
enforcement: test:tools/adlc/tests/test_fence_run.py
generalizes: [LESSON-887]
supersedes: []
---

## What Happened

LESSON-887 recorded that on Codex an allowed command runs outside the sandbox. A session does not call tools one per line: it writes `cat > body.md <<EOF … EOF && fence-run run …`. Codex judges each part of such a line, and when one part has no allow the whole line runs sandboxed, the allowed runner included. Inside the sandbox the runner could not write the linked worktree's git directory, the forge mock's lock or a log under the home directory. Nothing said "sandboxed": the lane check reported a fetch error, which an unattended lite run treats as a failed check and escalates to the full lane.

## Lesson

On a harness whose sandbox contains whatever no rule matches, an allow covers a command only when the command is the whole line, or every other part of the line is allowed too. Telling the model to call the tool alone is not enough; it chained in four of six launches with that instruction present. So the tool checks for itself, before doing any work, that it has what it needs outside the sandbox, and says in one line that nothing ran and to call it again alone. `os.access(path, os.W_OK)` sees a macOS sandbox's denial, and a linked worktree's common git directory is a path every fence needs and the sandbox denies.

## Why It Matters

The failure presents as something else every time: a fetch error, a permission error on a lock, a missing log. One of those disguises changed the lane a REQ ran on.

## Applies When

Adding a tool or fence that pushes, fetches, calls a forge or writes outside the working copy under Codex or another sandboxing harness; reading a permission error from a command that "is on the allowlist"; writing an exec adapter for a harness with prefix rules.
