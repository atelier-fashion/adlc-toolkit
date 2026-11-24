---
id: LESSON-903
title: "A second attempt inherits what the first left behind: time it from its own start, and make a create ask the system of record, not a note the agent was to write"
component: "adlc/tools/adlc/sprint-exec"
domain: "adlc"
stack: ["python", "shell", "codex"]
concerns: ["reliability", "unattended", "resumability"]
tags: ["exec-engine", "relaunch", "answer", "resume", "stall", "idempotency", "draft-pr", "forge-mock", "fake-harness", "exec-prompt"]
bug: BUG-291
created: 2026-11-23
updated: 2026-11-24
kind: process
evidence: "BUG-291; .adlc/research/harness-probes/codex-exec-manual.md launch 11, facts 13 to 15 (codex-cli 0.166.0, engine 0d3a62b): a run blocked, was answered 109 minutes later, read `stalled: no state write for 109 minutes` on the relaunch's first poll, opened PR 102 beside PR 101 and ended failed / no-pr. tools/adlc/tests/test_bug291_exec_launch_11_gaps.py failed in eight of nine tests on 1d40f47 and passes on 5303ecf: test_bug291_a_relaunched_run_is_not_stalled_by_the_wait_for_its_operator printed the same stalled line before the fix, and test_bug291_the_draft_pr_fence_run_twice_opens_one_pr printed `url=…/pull/102`. One real launch has run against the fix, launch 12 of the same note, and it did not block: the stall after an answer and the fence run twice are measured by the double only"
confidence: high
enforcement: test:tools/adlc/tests/test_bug291_exec_launch_11_gaps.py
generalizes: []
supersedes: []
---

## What Happened

Launch 11 blocked at Phase 4, waited 109 minutes for its operator and was relaunched by
`answer`. One real run had been answered before it, launch 6, at Phase 7 with its PR already
recorded. So a long wait, and a relaunch from before the PR number was written, had only ever
met the fake harness. Three things went wrong, two of them on that path.

- The stall check read idleness from the working copy's state file. The file was last written
  when the run blocked, so the relaunched session was `stalled` on its first poll, with the
  operator's wait as its idle time. The relaunch recorded a pid, a prompt and a log, and no
  start time of its own.
- Step 0's draft-PR fence was "resume-safe" by a sentence: reuse `prNumber` if it is set. The
  first session wrote state before the fence and not after. The second read `null`, ran the
  fence again, and the mock forge opened a second PR, which GitHub would have refused.
- The session's first block was Git's `index.lock … Operation not permitted`, from a commit
  chained after a command with no allow. The prompt explained a refused line and a sandboxed
  fence call. It had no sentence for the line Git itself prints.

## Lesson

A second attempt starts in what the first one left: a heartbeat file with an old date, a
half-written record, an object already created. Whatever the supervisor measures or the step
decides from those leftovers is about the first attempt until something re-anchors it.

- Give every attempt its own start stamp, and measure liveness from the later of the last
  heartbeat and that stamp. A field named for the run's start is not the attempt's start.
- Do not make a create safe to repeat by asking the agent to write down what it created. Make
  the step ask the system that holds the object, on the key that system keeps unique (for a
  PR, head and base), and print what it finds in the same shape as what it would create, with
  one line that says which it was.
- Let that read fail open where the system refuses a duplicate itself, so the step is never
  worse than before. Then say beside the step what the refusal means, because its error class
  may read as transient.
- A mock of that system must refuse what the real one refuses. And check the fake actor for
  help the real one does not get: this fake listed before it created, so the missing check was
  invisible from inside the suite (LESSON-891).
- When a prompt explains one failure by saying what it is not ("a refusal is not a sandbox
  failure"), give the other failure its own sentence too: the line the tool prints, that it is
  not a blocker, the next action, and the bound (LESSON-899, LESSON-892).
- A run that is interrupted and continued tests a different program from one that runs
  straight through, and where it was interrupted matters: one answered run at a late phase
  had shown none of this. Say which interruption points a real run has covered, and that the
  others are measured by the double only.

## Why It Matters

Each defect alone cost the run or misled its operator: a dashboard that says `stalled` for a
session ten seconds old, a second PR that the gate then refuses, a wait of 109 minutes for an
answer that was two commands. None showed in a suite of over 2,800 tests, because every double
in it was written by someone who already knew the step.

## Applies When

Adding a relaunch, retry, resume or answer path to a supervisor; writing a liveness or timeout
check that reads a file's age; writing a step that creates something on a remote and may run
twice; relying on state an agent is told to write; extending a mock of a forge or API; writing
the prompt rule for a failure line a tool prints.
