---
id: LESSON-914
title: "A test that hands a fence its inputs cannot see that the fence never makes them: run an extracted fence with nothing but what its real predecessor leaves behind"
component: "adlc/partials/tests"
domain: "adlc"
stack: ["shell", "python"]
concerns: ["testing", "correctness"]
tags: ["fence-extraction", "test-prelude", "cross-fence-state", "tmpfile", "vacuous-test", "harness-fidelity", "delegate-pre-pass"]
req: BUG-299
created: 2026-11-24
updated: 2026-11-24
kind: process
evidence: "BUG-299, fixed in 2560fe9 (PR #341). proceed/SKILL.md Phase 5 step 4's fence redacted and delegated \"$TMPFILE\" but never created it; step 2's prose said to mktemp it. partials/tests/redact-fence.test.sh created TMPFILE in its proceed prelude, and tools/lint-skills/tests/test_read_bin_fences.py passed TMPFILE in the environment, so both ran the fence green. With the prelude emptied and the env entry removed, the same tests on the unfixed tree fail: redact-fence 16 of 60 checks, the first 'proceed_sed_fails: exactly one stderr line (... got cp: : No such file or directory', and test_command_prefix_defeats_an_absolute_path_function. Both pass once the fence makes its own temp file."
confidence: high
enforcement: test:partials/tests/redact-fence.test.sh
generalizes: []
supersedes: []
---

## What Happened

REQ-522 moved the credential redaction into step 4's fence of `/proceed` Phase 5, so a failed
`sed` could not reach the delegate, because fenced blocks share no shell state. The temp file,
`EXIT` trap and diff capture that step 2 describes were not moved with it: the fence used
`$TMPFILE` and nothing defined it. Two harnesses extract that fence and run it. Each supplied
`$TMPFILE` itself, one in a prelude and one in the environment, "so the fence can reach the
invocation". So each tested a fence that could only work with their help, and passed. Run as
written, the fence always fell through to the redaction-failure path and never delegated.

## Lesson

When a test extracts a fence and runs it, give it only what the fence's real predecessor
leaves behind. Fenced blocks share no shell state, so that is usually the files and sidecars
an earlier fence wrote, never a shell variable. Every variable the prelude or the environment
sets is a claim that something else defines it. Check that claim against the skill text before
writing it. If nothing does, the prelude is hiding the defect the test exists to find. Stub the
outside world instead: `git`, `adlc-read`, `sed`, a fixture repository.

## Why It Matters

The whole point of running an extracted fence is to execute the text the model reads. A prelude
that fills a gap in that text turns the test into a check of the harness. This one stayed green
through a pre-pass that could never delegate, and the defect surfaced only when a design review
read the prose beside the fence.

## Applies When

- Writing or reviewing a test that extracts a SKILL.md or agent fence and runs it.
- A harness prelude or test environment sets a variable the fence reads.
- Moving work from one fence into another to keep a check in the same shell. Whatever the
  moved code reads has to move with it.
