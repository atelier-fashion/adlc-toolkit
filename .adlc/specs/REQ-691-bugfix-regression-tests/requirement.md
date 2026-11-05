---
id: REQ-691
title: "/bugfix writes a failing-first regression test for every bug, with a project opt-out"
status: approved
deployable: false
created: 2026-11-04
updated: 2026-11-04
component: "adlc/bugfix"
domain: "adlc"
stack: ["markdown", "python", "yaml", "sh"]
concerns: ["testing", "quality", "config"]
tags: ["regression-test", "regression", "bugfix", "opt-out", "config", "test-coverage", "failing-test", "bug-report", "waiver"]
lane: "full"
lane_reason: "adds fields to the bug template's frontmatter (a data model /status, /bugfix and consumers read) and a new .adlc/config.yml key, across the bugfix skill, two templates and a new CLI check: well over 3 files"
lane_forced: false
---

## Description

`/bugfix` does not require a regression test today. Phase 3 says only "Update related test files if the fix changes behavior", and Phase 4 runs the suite. A fix can land with no test that would fail if the bug came back, and nothing records whether one was written.

In practice some projects write one anyway. The Embolden platform pins all 15 of its bugs with a test that cites the bug id, but by habit, not by rule. Nothing checks that those tests still exist, so a refactor can drop one quietly.

This REQ makes the regression test part of the protocol. `/bugfix` writes a test that reproduces the bug, watches it fail without the fix and pass with it, and records the test in the bug report. A toolkit check then confirms that every resolved bug still has its test. Projects can wire that check into CI.

Not every project can or should do this. Some have no test suite: a docs repo, a design-system asset repo, an infrastructure repo. Others have one but don't want regression tests per bug. So the rule is a project setting in `.adlc/config.yml`, plus a per-bug waiver for the odd bug no test can reach in a project that otherwise requires them.

Upgrading the toolkit must not change what `/bugfix` does in an existing project, so a project that never sets the key gets `off`, and a project opts in by setting it to `required`. `/init` copies the config template into `.adlc/config.yml` only for a cross-repo project, so the template's `required` opts in those new configs; a single-repo project opts in by adding the key itself.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Project config (`.adlc/config.yml`) | `bugfix.regression_test` | enum string | `required` or `off`. Optional; absent means `off`. Any other value is an error, never a silent fallback |
| Bug report frontmatter | `regression_tests` | array of strings | Optional, additive. Each entry is a repo-relative path to a test file in the repo the fix landed in. Empty or absent means no test recorded |
| Bug report frontmatter | `regression_waiver` | string | Optional, additive. One line saying why no test can reproduce this bug. Empty or absent means no waiver |
| Bug report body | `## Regression Test` section | markdown | Written by `/bugfix`: each test path, the command run, the outcome without the fix and the outcome with it, or the waiver and its reason |

A bug report written before this REQ carries neither field. It parses and is processed unchanged, the same additive pattern as `introduced_by` (informed by REQ-593).

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| regression contrast observed | `/bugfix` Phase 4 runs the new test(s) without and then with the fix | test paths, command, pre-fix outcome (fail), post-fix outcome (pass) |
| regression check run | an operator, `/bugfix` Phase 6, or a project's CI runs the toolkit check | bugs checked, passed, waived, legacy, failed; exit status |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| Set `bugfix.regression_test` | Project maintainer, by committing `.adlc/config.yml` |
| Waive one bug's test | Whoever runs `/bugfix`; the waiver and its reason are visible in the bug report, the PR body and the Phase 6 summary |

## Business Rules

- [ ] BR-1: `/bugfix` reads `bugfix.regression_test` from `.adlc/config.yml` before Phase 1. Absent key, absent `bugfix` block or absent config file all mean `off`, so upgrading the toolkit changes nothing for a project that never set it. Any value other than `required` or `off` stops `/bugfix` at Phase 1 with a message naming the key, the value found, and the two allowed values.
- [ ] BR-2: In `required` mode, `/bugfix` writes at least one test that reproduces the bug: it exercises the root cause named in the bug report and asserts the expected behavior. Updating an existing test counts when the updated case reproduces the bug.
- [ ] BR-3: In `required` mode, `/bugfix` observes the contrast. It runs the regression test(s) against the tree with the fix's non-test changes absent, and they must fail. It then runs them with the fix in place, and they must pass. A test that passes without the fix does not reproduce the bug. `/bugfix` either rewrites it or records a waiver (BR-6); it never records that test as the regression test.
- [ ] BR-4: Each regression test cites the bug id (`BUG-nnn`) in its file, in a test name, a describe/suite title or a comment next to the case. The coverage check (BR-9) relies on this.
- [ ] BR-5: `/bugfix` records each regression test's repo-relative path in the bug report's `regression_tests` frontmatter field. It also fills a `## Regression Test` body section with each path, the command run, and the pre-fix and post-fix outcomes, including the first failing assertion line from the pre-fix run.
- [ ] BR-6: In `required` mode, a bug no test can reproduce may be waived. `/bugfix` writes a one-line reason to `regression_waiver` saying why a test cannot reach the defect, and leaves `regression_tests` empty. A waiver needs a reason; an empty or whitespace-only waiver is treated as no waiver. The waiver and its reason appear in the PR body and in the Phase 6 summary.
- [ ] BR-7: A bug report never carries both a non-empty `regression_tests` and a non-empty `regression_waiver`. `/bugfix` refuses to write both, and the coverage check fails a bug that has both.
- [ ] BR-8: In `off` mode, `/bugfix` neither writes a failing-first test nor asks for a waiver, and writes neither field. Its other test behavior is unchanged: it still updates related tests when the fix changes behavior and still runs the suite. The Phase 6 summary says regression tests are off for this project and, when the key is absent rather than set, names the key that turns them on.
- [ ] BR-9: The toolkit ships a regression check, runnable as a command from a project's root, that reads every bug report in `.adlc/bugs/` with status `resolved` or `closed` and sorts each into exactly one result:
  - **passed**: `regression_tests` is non-empty, and every listed path exists, is tracked by git, and contains the bug's id.
  - **waived**: `regression_waiver` is non-empty and `regression_tests` is empty.
  - **legacy**: neither field is present. It's reported, but doesn't fail the check.
  - **failed**: anything else, such as a listed path that is missing, untracked or doesn't contain the id, both fields set (BR-7), or a field that isn't the type the System Model gives it.

  The check can also be given one or more bug ids. It then checks exactly those bugs, whatever their status, with the same four results, and fails a named id that has no bug report.
- [ ] BR-10: The check exits 0 when no bug failed and non-zero when any did, and prints one line per failed bug naming the bug, the path and the reason. Every pass or fail run prints the passed, waived, legacy and failed counts; an `off` or `error` run prints its own reason line instead, because it counted nothing. A project with zero resolved bugs gets a 0 exit with all counts 0. That is a legitimate empty state, not a vacuous pass.
- [ ] BR-11: In an `off` project, whether set or absent, the check exits 0 without reading any bug report, and prints that regression tests are off for this project.
- [ ] BR-12: The check's verdict on a bug depends only on the working tree and git's index, never on a remote branch or a diff against one, so it gives the same answer on every branch (informed by LESSON-782). Two reads are not of the working tree, and neither is a diff. Policy: given `--base` with a full ref, the check reads the setting and `repos:` from `.adlc/config.yml` as committed at that ref, never from the tree, and `/bugfix`'s Phase 6 gate names the integration branch's remote-tracking ref, so a branch cannot loosen its own gate (LESSON-718). Commits: with `--require-recorded`, each listed test must also be committed, citing the bug id, in its repo's own `HEAD`. Bug reports are never read at a ref. *(Amended in the Phase 5 verify passes.)*
- [ ] BR-13: In `required` mode, `/bugfix` Phase 6 runs the check on this bug's id (BR-9), before setting its status to `resolved`; the bug is still open at that point, so a status-scoped run would skip it. If the check reports this bug as failed or legacy, `/bugfix` doesn't mark it resolved, and says why.
- [ ] BR-14: For a cross-repo bug (`repo:` or `touched_repos:` naming a sibling), a test lives in the repo whose fix it covers, and its `regression_tests` entry is prefixed with that repo's id from `.adlc/config.yml` (`<repo-id>:<path>`). The check resolves a prefixed path through that repo's `path:`. When the sibling isn't cloned at that path, the bug counts as failed and the line names the missing clone.
- [ ] BR-15: `templates/config-template.yml` sets `bugfix.regression_test: required`, not commented out, and documents both values, that an absent key means `off`, and when to choose `off`. A project whose config was copied from an older template has no key and keeps today's behavior.
- [ ] BR-16: The lesson-capture step in `/bugfix` Phase 6 treats a recorded pre-fix-fail / post-fix-pass run as the contrast its confidence rule asks for, and cites it as the lesson's evidence.
- [ ] BR-17: When `.adlc/config.yml` exists but the setting can't be read (the file doesn't parse, or the parser it needs isn't available), `/bugfix` and the check both stop with a message saying why. They never treat an unreadable setting as `off`. A missing config file isn't unreadable: it means `off` (BR-1). `templates/bug-template.md` documents `regression_tests` and `regression_waiver` as optional and additive, and adds the `## Regression Test` section. Existing bug reports and configs stay valid without migration.

## Acceptance Criteria

- [ ] AC-1: In a project whose config sets `bugfix.regression_test: required`, `/bugfix` on a reproducible bug produces a PR containing a test that cites the bug id, and a bug report whose `regression_tests` lists that test and whose `## Regression Test` section records a failing pre-fix run and a passing post-fix run.
- [ ] AC-2: With `bugfix.regression_test: off`, and separately with no config file at all, `/bugfix` produces no regression test requirement, writes neither field, and its Phase 6 summary says regression tests are off for this project. In the no-config run the summary also names the key that turns them on.
- [ ] AC-3: With `bugfix.regression_test: sometimes`, `/bugfix` stops at Phase 1 with a message naming the key, `sometimes`, and the allowed values `required` and `off`.
- [ ] AC-4: When the written test passes with the fix absent, `/bugfix` doesn't record it as the regression test. It rewrites the test until it fails pre-fix, or records a waiver with a reason.
- [ ] AC-5: The check, run over a fixture `.adlc/bugs/` holding one each of passed, waived, legacy and every failed cause from BR-9 (missing path, untracked path, path without the id, both fields set, a wrong field type), classifies each as BR-9 says and exits non-zero. It prints one line per failed bug and the four counts.
- [ ] AC-6: The same check over a fixture with only passed, waived and legacy bugs exits 0 (benign path).
- [ ] AC-7: The check over an empty `.adlc/bugs/`, and over a project with no `.adlc/bugs/` directory, exits 0 with all counts 0.
- [ ] AC-8: The check in a project whose config sets `off`, and in one with no key, exits 0, reads no bug report, and says regression tests are off.
- [ ] AC-9: The check gives the same verdict on two branches whose `.adlc/bugs/` and test files are identical, regardless of how either differs from the remote default branch.
- [ ] AC-10: A cross-repo bug whose prefixed path resolves in a cloned sibling passes. The same bug with the sibling missing fails, with a line naming the missing clone.
- [ ] AC-11: An existing bug report with neither new field, for example any toolkit bug resolved before this REQ, is reported as legacy and doesn't change the check's exit status.
- [ ] AC-12: In `required` mode, `/bugfix` Phase 6 leaves a bug's status unresolved when the check reports that bug as failed, and says why.
- [ ] AC-13: `templates/config-template.yml` and `templates/bug-template.md` carry the documentation BR-15 lists, and `/template-drift` reports the bug template as stale in a project that vendored the old one. (The config template isn't a vendored template: `/init` copies it once as `.adlc/config.yml`, so drift doesn't track it.)
- [ ] AC-14: `tools/lint-skills` and the full `partials/tests/run.sh` pass on the final tree, not only the tests named for this REQ (informed by LESSON-742, LESSON-752).
- [ ] AC-15: The check, given the id of an open bug whose fields are valid, reports it as passed or waived; given an id with no bug report, it fails and names the id.
- [ ] AC-16: With a `.adlc/config.yml` that names the setting (or a `bugfix:` block) and doesn't parse, `/bugfix` and the check both stop and say why; with no config file at all, both behave as `off` (benign path).

## External Dependencies

- No new package. The check runs on the toolkit's existing Python and git. Reading `.adlc/config.yml` goes through the toolkit's one config loader (REQ-609), which needs PyYAML; the lane check only parses the file when its key appears outside a comment, and how this check avoids needing PyYAML on a plugin install without the delegate venv is an architecture decision bounded by BR-17.

## Assumptions

- A bug resolved outside `/bugfix` (a report written and closed by hand) may carry neither field. The check reports it as legacy rather than failing it, so adopting this REQ never fails a project's existing history. The cost is that a hand-closed new bug also reads as legacy; the legacy count makes that visible.
- Writing a test that reproduces a bug may need some restructuring to make the code testable. That restructuring belongs to the fix, and BR-3's pre-fix run removes only the non-test changes. When the regression test can't even load without the fix (for example it imports a function the fix adds), the pre-fix run fails at load time, not on an assertion. `/bugfix` records it that way and the PR body flags it as a weak contrast. It is still accepted.
- The check confirms a regression test exists, is tracked and cites its bug. It doesn't confirm the project's test runner actually picks that file up. A test file outside the runner's include globs would pass the check without ever running.
- "No test suite" is not detected automatically. A project without one either sets `off` or records a waiver per bug. Detecting a suite reliably across stacks would make the opt-out implicit, and an implicit opt-out is how a required rule goes quiet.

## Open Questions

None. Answered by Brett on 2026-11-04:

- [x] Should an absent key mean `required`? No. Absent means `off`, so an upgrade changes nothing; the config template sets `required` for projects started from it (BR-1, BR-15).
- [x] Should the check have a strict mode that fails hand-closed bugs created after a date? No. Legacy bugs are counted and reported, never failed (BR-9).
- [x] Should wiring the check into Embolden's `gates` be a follow-up REQ in embolden-website? Yes, after this ships (Out of Scope).

## Out of Scope

- Wiring the check into any project's CI, including this toolkit's own CI. Embolden's `gates` gets it in a follow-up REQ in embolden-website once this ships; that runner has no toolkit installed, so the wiring is that REQ's design.
- A strict mode that fails legacy bugs.
- Turning the setting on in any existing project, the toolkit included.
- Changing `/init` so a single-repo project gets a config file or the setting.
- Back-filling `regression_tests` for bugs resolved before this REQ, in the toolkit or any consumer.
- Checking that a regression test is collected by the project's runner, or measuring coverage.
- Browser end-to-end or visual regression testing.
- Changing `/proceed`, `/review` or `/reflect`. Feature REQs keep their own verification obligations (REQ-595); this REQ covers bug fixes only.

## Retrieved Context

- LESSON-729 (lesson, score 7): Split parallel fix groups so a contract's writer and its readers land in the same group — file ownership alone separates them
- REQ-610 (spec, score 7): Guard the two-level partial-sourcing pattern so a missing repo-local partial is not fatal under POSIX sh
- LESSON-603 (lesson, score 7): A spec that names a frontmatter field is stating a belief, not a fact — check it against the template that actually emits the field
- REQ-593 (spec, score 7): Incident→REQ backlink: attribute a BUG to the REQ that shipped its cause
- LESSON-023 (lesson, score 7): When mirroring a hardened pattern to a sibling, port the rationale comments and type-discipline — not just the mechanism
- REQ-441 (spec, score 7): Global cross-repo BUG-ID counter (mirror the global REQ counter)
- LESSON-754 (lesson, score 6): A harness that runs a skill's fence must substitute its argument placeholders and copy every directory the fence reads, or a fence that skips bad input passes while doing nothing
- LESSON-742 (lesson, score 6): A skill-text edit is input to the harnesses that parse skill text — a clean lint is not the gate; run partials/tests/run.sh on the final tree
- LESSON-752 (lesson, score 6): Before moving text out of a SKILL.md, list every harness that reads it by path — the readers you may not edit decide what stays
- REQ-595 (spec, score 6): BR→verification obligations: /architect emits the tests, not just the tasks
- LESSON-780 (lesson, score 5): A mock returns the shape its author assumed: run each new forge field once, read-only, against the real CLI
- LESSON-782 (lesson, score 5): Do not commit a test that says a file is unchanged against origin/main: it passes on main and fails the next REQ that may edit it
- LESSON-785 (lesson, score 5): In a move, an absent source does not make the destination stale: the branch that tidies a leftover is the one that deletes someone's data
- LESSON-787 (lesson, score 5): A sandboxed HOME does not sandbox launchd: bootout finds its agent by the label inside the plist, so a test must replace the binary, not only the path
- LESSON-788 (lesson, score 5): A test that evaluates a script between two markers makes those markers a contract: code added above one runs in the slice, with none of the script's earlier setup
