---
id: LESSON-013
title: "POSIX mkdir-locks need a symlink pre-check to defend against TOCTOU swap"
component: "adlc/locking"
domain: "adlc"
stack: ["bash", "posix"]
concerns: ["security", "concurrency"]
tags: ["mkdir-lock", "toctou", "symlink", "counter", "race-condition"]
req: REQ-416
created: 2026-05-15
updated: 2026-05-15
---

## What Happened

The toolkit guards the global `~/.claude/.global-next-req` counter with a POSIX
`mkdir`-based lock at `~/.claude/.global-next-req.lock.d`. Two issues surfaced
during REQ-416 ADR-4 review:

1. **TOCTOU vulnerability.** If an attacker (or a misconfigured tool) replaces
   the lock directory path with a symlink between checks, `mkdir` follows the
   symlink and `rmdir` later operates on the redirected target. On a shared
   `/tmp`-style attack surface this could be used to delete an arbitrary
   directory the user has write access to.
2. **Two unguarded counters.** `.adlc/.next-lesson` and `.adlc/.next-assume`
   were doing read-modify-write with no lock at all. Concurrent `/sprint`
   pipelines, or a `/wrapup` and `/bugfix` running in parallel, could allocate
   the same id and overwrite each other's lesson/assumption files.

## Lesson

Every `mkdir`-lock site MUST pre-check `[ -L "$LOCK" ]` and refuse to operate
when the path is a symlink. The release path must also `[ ! -L "$LOCK" ]` guard
the `rmdir` so a swap mid-critical-section can't redirect the cleanup.

Every read-modify-write against a shared counter file MUST be wrapped in a
lock. When two skills mutate the same counter (e.g. `/wrapup` and `/bugfix`
both allocate from `.adlc/.next-lesson`), they MUST share the SAME lock path
so they mutually exclude.

Canonical idiom:

```bash
NUM=$(
  LOCK=path/to/.counter.lock.d
  if [ -L "$LOCK" ]; then
    echo "ERROR: $LOCK is a symlink — refusing (TOCTOU risk). Inspect manually." >&2
    exit 1
  fi
  for _ in $(seq 50); do mkdir "$LOCK" 2>/dev/null && break; sleep 0.1; done
  N=$(cat path/to/.counter)
  echo $((N + 1)) > path/to/.counter
  if [ ! -L "$LOCK" ]; then rmdir "$LOCK" 2>/dev/null; fi
  echo $N
)
```

## Why It Matters

Without the symlink pre-check, an attacker with write access to the lock's
parent directory can redirect the lock cleanup to any directory the user owns.
Without a lock on `.next-lesson`/`.next-assume`, parallel pipelines silently
double-allocate ids, producing two LESSON files with the same number — the
second overwrites the first on commit.

Residual risk: an attacker with write access to `~/.claude/` or the project's
`.adlc/` directory already controls the user's pipeline. The symlink pre-check
defends against accidental misconfiguration and against shared-tmp attack
patterns that don't apply here, not against full local-account compromise.
Migrating off `mkdir`-locks (e.g. to `flock` or `python-filelock`) was rejected
in REQ-416 OQ-4 because it introduces a Python runtime dependency.

## Applies When

- Adding any new shared counter or sequence file under `~/.claude/` or `.adlc/`.
- Adding any new POSIX `mkdir`-based lock anywhere in the toolkit.
- Reviewing skills that do read-modify-write on a file shared across concurrent
  pipelines (`/sprint`, parallel `/proceed`, simultaneous `/wrapup`+`/bugfix`).

## Verification Tests

Both tests run against the canonical idiom above and pass on macOS (Darwin
25.4.0, POSIX `sh`). They are reproducible by any future skill that adopts the
pattern.

**Concurrent counter test (no lost update):**

```bash
mkdir /tmp/locktest && cd /tmp/locktest && echo "100" > counter
incr() {
  LOCK="./counter.lock.d"
  if [ -L "$LOCK" ]; then echo "ERROR sym" >&2; exit 1; fi
  for _ in $(seq 50); do mkdir "$LOCK" 2>/dev/null && break; sleep 0.1; done
  NUM=$(cat counter); sleep 0.2
  echo $((NUM + 1)) > counter
  if [ ! -L "$LOCK" ]; then rmdir "$LOCK" 2>/dev/null; fi
}
incr & incr & wait
cat counter   # expect 102 (start 100 + 2 increments) — confirmed
```

The injected `sleep 0.2` between the read and the write maximises the race
window so an unlocked implementation would fail loudly. Result observed: `102`.

**Symlink-swap test (refusal + counter unchanged):**

```bash
echo "200" > counter2
ln -s /tmp/locktest/somewhere ./counter2.lock.d
(
  LOCK="./counter2.lock.d"
  if [ -L "$LOCK" ]; then echo "ERROR: $LOCK is a symlink — refusing (TOCTOU risk). Inspect manually." >&2; exit 1; fi
  mkdir "$LOCK"
  NUM=$(cat counter2); echo $((NUM + 1)) > counter2
  rmdir "$LOCK"
)
echo $?       # expect non-zero — confirmed (1)
cat counter2  # expect 200 (unchanged) — confirmed
```

The pre-existing symlink causes the locked block to abort before any read or
write touches the counter. Stderr matches the canonical error message exactly.
