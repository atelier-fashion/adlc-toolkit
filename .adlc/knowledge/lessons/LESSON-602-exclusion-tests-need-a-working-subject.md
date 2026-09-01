---
id: LESSON-602
title: "An exclusion test that asserts only 'nothing was reported' passes on a totally broken subject"
component: "adlc/lint-skills"
domain: "testing"
stack: [python, pytest]
concerns: [testing, correctness, verify]
tags: [vacuous-test, negative-assertion, exclusion, test-design, benign-path]
req: REQ-595
created: 2026-08-31
updated: 2026-08-31
---

## What Happened

REQ-595 added a vacuous-*run* guard to `tools/lint-skills`: a scan that walks zero
`SKILL.md` files now exits `255` instead of a confident `0`. Adding it broke two
tests that had been green since REQ-433/REQ-436:

```python
def test_skip_dirs_are_excluded(tmp_path):
    for skip in [".git", ".worktrees", "node_modules"]:
        sub = tmp_path / skip / "ignored"
        sub.mkdir(parents=True)
        shutil.copyfile(FIXTURES / "corrupt-sentinel.md", sub / "SKILL.md")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
```

The break was the *finding*, not the damage. Every `SKILL.md` in that root sits under
a skipped directory, so the walker yields nothing and the test's two assertions —
exit 0, empty stdout — are satisfied. But they are equally satisfied by a walker that
finds nothing **for any reason**: a broken `rglob`, an inverted skip predicate, a
`find_skill_files` that returns immediately. The test could not distinguish "the skip
list works" from "the scanner is dead." It had been passing for three REQs without
proving its own subject line.

The same file already contained the correct construction, in
`test_symlink_outside_root_is_excluded`: stage a real in-root skill *alongside* the
excluded one, assert the real one is found **and** the excluded one is not. The fix
was to port that shape to both tests, which now also pin `scanned 1 SKILL.md file(s)`.

## Lesson

**A test whose only assertions are negative ("X was not reported", "exit was clean",
"the list is empty") cannot tell success from total failure of the subject.** Absence
of a result is the expected output of both.

Every exclusion / filtering / skip test needs a **positive control in the same run**:
one input that MUST be processed, asserted present, next to the input that must be
excluded, asserted absent. If the positive control is missing, the test is a tautology
wearing a subject line.

Practical form:

- Staging only excluded inputs → the assertion is vacuous. Stage an included one too.
- Prefer asserting the *work count* (`scanned N`), not just the outcome. A count is a
  positive claim; "no output" is not.
- The tell is a test that would still pass if you replaced the function under test
  with `return []`. Try that substitution mentally on any all-negative test.

This is the test-design twin of LESSON-440 (a detector needs a benign-path case). That
lesson says: a detector tested only on adversarial input ships broken. This one is the
mirror: an *excluder* tested only on excluded input ships broken. Both failures are
invisible because the suite is green.

## Why It Matters

These tests are load-bearing — they guard REQ-433's ADR-4 skip list and REQ-436's
ADR-5 root-part fix, which exist because `/proceed` runs every phase inside
`.worktrees/` and a wrong skip predicate silently scans nothing. The guard protecting
against a vacuous scan was itself verified by vacuous tests. Had the skip predicate
regressed, the suite would have stayed green and the linter would have reported clean
on every `/proceed` run, which is precisely the REQ-435 false-green the whole line of
work exists to prevent.

The cost of the fix was three lines per test. The cost of not finding it is a linter
that reports clean forever, and a class of corruption that ships because the tool
meant to catch it was never actually running.

Note also *how* it was found: not by review of the tests, but as collateral of adding
a guard elsewhere. A vacuous-work guard on the subject is an effective way to flush out
vacuous tests of that subject — the guard fails exactly the tests that were relying on
zero work.

## Applies When

- Writing or reviewing any test for exclusion, filtering, skip lists, ignore patterns,
  allow/deny predicates, or `.gitignore`-style behavior.
- Reviewing a test whose assertions are all negative — `not in`, `== []`, `== ""`,
  `returncode == 0` with no positive claim about work performed.
- Adding a "did any work happen?" guard to a scanner, walker, or batch job: expect it
  to break existing tests, and read each break as a finding about the test rather than
  an obstacle to the guard.
- Designing a test for anything with a discovery/collection phase, where "found
  nothing" and "worked correctly" produce identical observable output.
