---
id: TASK-175
title: "Live probe run against the installed claude binary"
status: draft
parent: REQ-664
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-172]
repo: adlc-toolkit
---

## Description

AC-13: run `adlc harness probe claude` on this machine against the installed
`claude` binary, from the worktree, and commit the result file and the
transcript fixture it writes. Record the outcome, whatever it says, in the PR as
the first real §6.10 result.

## Files to Create/Modify

- `.adlc/research/harness-probes/claude.json` — new: the live result
- `.adlc/research/harness-probes/fixtures/claude.jsonl` — new: the redacted fixture

## Acceptance Criteria

- [ ] the run exits 0 or 1, never a traceback, and `arg-substitution` is decided
- [ ] `~/.claude` gains nothing but the harness's own session records under `projects/`, which the evidence lists
- [ ] the committed files contain no home path and no credential-shaped string

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| AC-13 | test-case | `tools/adlc/tests/test_harness_probe_docs.py::test_committed_claude_result_is_clean` | no |

## Technical Notes

Run with a login-shaped environment (`env -i HOME PATH USER SHELL TMPDIR LANG`)
so the parent Claude Code session's `CLAUDECODE`/`CLAUDE_CODE_*` variables do not
reach the child: the caller's environment is what the command inherits (BR-8),
and the caller here is a login shell. Take a listing of `~/.claude` before and
after and diff it.
