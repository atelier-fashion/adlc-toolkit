---
id: BUG-256
title: "tools/adlc tests write to the real reservation ledger"
status: resolved
severity: low
created: 2026-10-30
updated: 2026-10-30
component: "adlc/tools/adlc/tests"
domain: "adlc"
stack: ["python", "pytest", "sh"]
concerns: ["testing", "test-isolation"]
tags: ["sandbox", "home-directory", "ledger", "reservations", "autouse-fixture"]
introduced_by: ["REQ-546"]
attribution: derived
---

## Description

`tools/adlc/tests/test_renumber.py::test_reserve_new_id_won_pushes_ref` calls
`renumber.reserve_new_id`, which runs `adlc_reserve_id` from `partials/id-alloc.sh` and
records a won reservation in `$ADLC_HOME/.adlc-own-reservations`. The suite never moved
`HOME`, so every full run appended a fake `req 700` line to the real ledger.

## Reproduction Steps

1. Run `python3 -m pytest tools/adlc/tests/test_renumber.py` on a machine with `~/.claude/`.
2. Compare `grep -c '^req 700 ' ~/.claude/.adlc-own-reservations` before and after.

## Expected Behavior

A test run leaves the real home directory untouched.

## Actual Behavior

The count rises with each run: 504 of the ledger's 1,070 lines were fake on 2026-10-30.

## Environment

macOS, Python 3 with PyYAML in the user site, the symlink install.

## Root Cause

Prior lessons consulted:
- LESSON-758 — A suite sandboxed by convention leaks through the one test that forgot — diff the real home around a run instead of trusting the fixture (score 16)
- LESSON-745 — A test of a command that reads the caller's repository must run outside the checkout — a committed result the command reads flips it (score 12)
- LESSON-754 — A harness that runs a skill's fence must substitute its argument placeholders and copy every directory the fence reads, or a fence that skips bad input passes while doing nothing (score 6)
- LESSON-752 — Before moving text out of a SKILL.md, list every harness that reads it by path — the readers you may not edit decide what stays (score 6)
- LESSON-619 — A harness that executes lines extracted from markdown is an execution surface — gate on a token allowlist, and never cite the lint as the control (score 6)

`test_reserve_new_id_won_pushes_ref` (REQ-546) wins a real reservation against a sandbox
remote, and `adlc_reserve_id` then records it through `adlc_id_own_ledger`, which resolves
`$ADLC_HOME`, or `~/.claude` when that is unset. `conftest.py` already unset `ADLC_HOME` but
left `HOME` alone, so the path was the runner's real ledger. Sandboxing was a per-test
convention, which is the failure LESSON-758 describes; this fix applies its remedy.

## Resolution

`tools/adlc/tests/conftest.py` gains an autouse `_sandbox_home` fixture, so every test in the
suite gets its own throwaway `HOME`. It also keeps `PYTHONUSERBASE` at the runner's value,
because moving `HOME` otherwise hides a PyYAML installed in the user site from child
`python3` processes. A test that sets `HOME` itself still wins. The renumber test now asserts
that the won reservation lands in the sandbox ledger.

Verified by running every suite under a throwaway outer `HOME` containing `~/.claude`:
`pytest tools` (2930 passed, 4 skipped) and `partials/tests/run.sh` left no files there, so
no other suite leaks. As a control, unfixed `origin/main` left two `req 700` lines under the
same probe. A first probe with an empty outer `HOME` also read clean, but could not see the
leak (LESSON-762).

The 504 existing `req 700` lines in the real ledger were left alone. They are advisory, keyed
on exact shas, and a stale line can only ever fail to match.

## Files Changed

- `tools/adlc/tests/conftest.py` — autouse `_sandbox_home` fixture.
- `tools/adlc/tests/test_renumber.py` — asserts the sandbox ledger received the reservation.
- `.adlc/knowledge/lessons/` — LESSON-762.

## Deployment

None: test-only, and the toolkit has no deploy targets.
