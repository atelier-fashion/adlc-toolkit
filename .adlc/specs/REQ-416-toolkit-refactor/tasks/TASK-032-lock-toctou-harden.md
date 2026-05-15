---
id: TASK-032
title: "Lock-symlink TOCTOU review and harden all counter sites"
status: draft
parent: REQ-416
created: 2026-05-15
updated: 2026-05-15
dependencies: []
---

## Description

Resolve REQ-416 BR-5 (ADR-4). Three lock/counter sites exist in the toolkit;
only one currently uses a lock at all, and that lock is vulnerable to a
symlink swap. Harden all three.

## Files to Create/Modify

- `spec/SKILL.md` — Step 2 (lines ~157–177). Add a symlink pre-check before
  `mkdir`-ing the lock directory: if `[ -L "$LOCK" ]`, refuse to operate and
  exit non-zero with a clear stderr error. Same idiom for the lock-release
  path (no rmdir if lock is a symlink).
- `wrapup/SKILL.md` — Step ~94 (`.adlc/.next-assume` RMW) and Step ~167
  (`.adlc/.next-lesson` RMW). Wrap each read-modify-write in the same
  mkdir-lock pattern as the global counter, with the same symlink pre-check.
  Lock paths: `.adlc/.next-assume.lock.d` and `.adlc/.next-lesson.lock.d`.
- `bugfix/SKILL.md` — Step ~174 (`.adlc/.next-lesson` RMW). Same wrap.
  Reuses the same `.adlc/.next-lesson.lock.d` lock path as wrapup so a
  /bugfix and a /wrapup running concurrently don't double-allocate.
- `.adlc/context/architecture.md` — update the "Atomic REQ counter" bullet
  (line 86) to mention the symlink pre-check, and add a parallel bullet for
  the per-project `.next-lesson` and `.next-assume` counters now that they
  are locked.
- `.adlc/knowledge/lessons/LESSON-xxx-lock-symlink-toctou.md` — NEW lesson
  capturing the pattern. Use the next available LESSON ID via the standard
  `.adlc/.next-lesson` counter (after this task ships, that counter is now
  itself locked — bootstrap by running the lesson allocation BEFORE applying
  the lock change, or after the lock change using the new locked path).

## Acceptance Criteria

- [ ] All three lock acquisitions check `[ -L "$LOCK" ]` and refuse to
      operate when the lock path is a symlink.
- [ ] The two unguarded counters (`.next-lesson`, `.next-assume`) are wrapped
      in `mkdir`-locks at `.adlc/.next-lesson.lock.d` and `.adlc/.next-assume.lock.d`.
- [ ] `bugfix` and `wrapup` use the SAME `.next-lesson.lock.d` path so they
      mutually exclude.
- [ ] Concurrent invocation test: run two background `bash -c "<lock-acquire-and-increment>"`
      against the same counter, confirm the result is exactly N+2 (no lost
      update). Document this test in the new LESSON.
- [ ] Symlink-swap test: pre-create the lock path as a symlink to `/tmp/foo`,
      run the counter-increment, confirm it exits non-zero with the expected
      stderr message and the counter is unchanged.
- [ ] `.adlc/context/architecture.md` reflects the new lock topology.
- [ ] New LESSON entry exists describing the pattern, ready for future skills
      to reference instead of re-inventing.

## Technical Notes

- POSIX-only. Do not use `flock`. Do not use `python-filelock`. The
  `mkdir` + symlink-pre-check pattern is the convention.
- Symlink pre-check idiom (copy-paste):
  ```bash
  if [ -L "$LOCK" ]; then
    echo "ERROR: $LOCK is a symlink — refusing (TOCTOU risk). Inspect manually." >&2
    exit 1
  fi
  ```
- The retry loop already used at the global counter (50 iterations × 0.1s)
  is the right shape for the per-project counters too — `/sprint` rarely
  produces more than a handful of concurrent writers.
- Residual risk (documented in the new LESSON): an attacker with write access
  to `~/.claude/` or to `.adlc/` already controls the user's pipeline. The
  symlink pre-check defends against accidental misconfiguration and against
  shared `/tmp`-style attack vectors that don't apply here, not against a
  full local-account compromise.
- Out of scope: migrating off mkdir-locks entirely. That's an OQ-4 alternative
  the architecture explicitly rejected (introduces a Python runtime dep).
