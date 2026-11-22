---
id: LESSON-902
title: "An agent's account of why it stopped is a guess when the harness refused its line: show the harness's own record beside the account, whatever the agent claims"
component: "adlc/tools/adlc/sprint-exec"
domain: "adlc"
stack: ["python", "codex"]
concerns: ["reliability", "unattended", "developer-experience"]
tags: ["exec-engine", "exec-prompt", "deny-tier", "refusal", "compound-command", "stderr", "dashboard", "codex"]
bug: BUG-290
created: 2026-11-21
updated: 2026-11-21
kind: process
evidence: "BUG-290; .adlc/research/harness-probes/codex-exec-manual.md launch 9, fact 11 (codex-cli 0.166.0, engine f53f322): `rm -f /tmp/… && git add … && git commit …` was refused whole for `rm -f`, the refusal was on stderr only, and the session reported `blocked` / `git-commit-blocked` (index.lock outside the writable roots) without running the commit alone; the engine recorded blocked / other, class ok. tools/adlc/tests/test_bug290_refused_chained_line.py failed on 2aa844a and passes on 79ff3a7. No real launch has run against the fix: what a session does after reading the new note is not measured"
confidence: medium
enforcement: test:tools/adlc/tests/test_bug290_refused_chained_line.py
generalizes: []
supersedes: []
---

## What Happened

A real Codex exec session finished its REQ, tests passing, and put a forced delete of two
scratch files on the same line as its commit. `rm -f` is in the exec deny tier, so the harness
refused the line before any of it ran. The refusal left no item in the session's event stream.
The session's explanation was a sandbox one: Git could not create `index.lock` outside the
writable roots. It had been told that chained lines can run sandboxed, it had not been told
what a refusal is, and it did not try the commit on a line of its own, where it is allowed.

The engine had the truth in the session's stderr log and did not show it. It read the
harness's refusal only for a run that claimed no terminal state. This session claimed
`blocked`, so the operator saw the session's account alone. Where the line was shown at all,
it was cut at 300 characters from the left: the line quotes the whole command first, and the
harness's own words began at character 336.

## Lesson

When the harness refuses a line, nothing runs, so the agent has no observation to explain and
supplies a plausible cause from what it was told. Its report is then wrong in a way that reads
as right.

- Do not gate the harness's record on the agent's silence. A run that ends on the agent's own
  account is the case where the record matters most. Show both, and let the terminal stay the
  agent's: the supervisor cannot tell cause from coincidence, so it informs and does not
  reclassify.
- Tell the agent what a refusal is before it meets one: the line ran nothing, the refusal says
  nothing about the other commands, run those again alone, and report a blocker only for what
  fails that way. Say also that the refused command is not retried under another spelling, or
  "not a blocker" reads as "work around it".
- Remove the reason for the bad line as well as explaining it. Here that was a place for
  scratch files and a way to remove them that no rule refuses.
- Cut a quoted log line around what the pattern matched. A harness line that echoes the
  command puts its own words last, and a cut from the left keeps the echo and drops the words.
- An instruction not to chain was already in the prompt for another case and was not followed
  in four of six launches (LESSON-893). Where no tool of yours runs on the refused line, the
  only check left is afterwards, in what the operator is shown.

## Applies When

Classifying how an unattended agent run ended; deciding which of the harness's records reach
a dashboard or a blocker; writing the prompt rule for a deny tier that refuses instead of
asking; truncating a log line for display; reading a `blocked` whose stated cause was never
measured.
