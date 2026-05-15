---
id: LESSON-015
title: "`exit 1` inside `$(...)` only exits the subshell — guard the parent context"
component: "adlc/skills/locking"
domain: "adlc/shell"
stack: ["bash", "posix-sh"]
concerns: ["correctness", "fail-loud"]
tags: ["shell", "subshell", "lock", "fail-loud", "verify"]
req: REQ-416
created: 2026-05-15
---

## Context

REQ-416 hardened four atomic-counter sites (`spec/SKILL.md` global REQ counter,
`wrapup/SKILL.md` ASSUME + LESSON counters, `bugfix/SKILL.md` LESSON counter)
against lock-acquisition failure. Each site uses the same pattern:

```bash
REQ_NUM=$(
  LOCK=...
  for _ in $(seq 50); do mkdir "$LOCK" 2>/dev/null && break; sleep 0.1; done
  [ -d "$LOCK" ] || { echo "ERROR: failed to acquire $LOCK" >&2; exit 1; }
  NUM=$(cat "$COUNTER")
  echo $((NUM + 1)) > "$COUNTER"
  rmdir "$LOCK"
  echo $NUM
)
```

The Phase 5 verify D-pass surfaced a Major correctness regression in this
pattern: when `mkdir` cannot acquire the lock after 50 retries (≈5 s), the
`exit 1` fires inside the `$(...)` subshell. That `exit` terminates **only the
subshell**, not the parent skill. The parent context's `REQ_NUM` is silently
assigned the empty string. The skill then proceeds into Step 3 with
`REQ_NUM=""`, writing a malformed `REQ--feature-slug/` directory.

The same bug applied to all three counter sites for the same reason.

## Lesson

`exit` inside a `$(...)` command substitution terminates the subshell, not the
caller. The caller sees the subshell exit code only if it explicitly checks
`$?` immediately after the substitution (and the assignment itself doesn't
preserve that exit code). Variable assignment `VAR=$(...)` always succeeds at
the assignment level even if the subshell exited non-zero — `$?` after the
assignment reflects the subshell's exit, but only if NOTHING between the
assignment and the check clobbers it.

**Rule**: when a `$(...)` subshell has any fail-loud `exit` path, follow the
assignment with an explicit guard on the resulting variable:

```bash
REQ_NUM=$( ... potentially-exits ... )
[ -n "$REQ_NUM" ] || { echo "ERROR: ..." >&2; exit 1; }
```

The `[ -n "$VAR" ]` form is more reliable than checking `$?` because:
- `$?` is clobbered by every subsequent command (including comments, in some
  shells, and any debug prefix you might add later).
- An empty-string assignment is what you actually want to defend against —
  it's the user-visible bug, not the exit code.
- The pattern reads naturally as "if the allocation failed, abort."

## Generalizes To

- Any locking idiom using `$(...)` to enclose a critical section.
- Any counter-allocation, ID-generation, or atomic-fetch pattern returning a
  value via stdout capture.
- The same pitfall exists with backticks (` `...` `) — same fix.

## Anti-pattern

```bash
# WRONG: exit 1 fires inside the subshell, REQ_NUM becomes ""
REQ_NUM=$(
  acquire_lock || exit 1
  cat ~/.counter
)
# REQ_NUM is silently empty — execution continues, downstream code crashes obscurely
mkdir "REQ-$REQ_NUM-slug"
```

## Correct pattern

```bash
REQ_NUM=$(
  acquire_lock || exit 1
  cat ~/.counter
)
# Guard the parent — the subshell exit doesn't reach us
[ -n "$REQ_NUM" ] || { echo "ERROR: allocation failed — aborting" >&2; exit 1; }
mkdir "REQ-$REQ_NUM-slug"
```

## Citations

- Caught by Phase 5 verify D-pass (correctness re-verify) on REQ-416 — see
  PR #43 commit `eca54b2`.
- Sites fixed: `spec/SKILL.md` (REQ counter), `wrapup/SKILL.md` (ASSUME +
  LESSON counters), `bugfix/SKILL.md` (LESSON counter).
- Companion lesson LESSON-014 covers the symlink-pre-check pattern these
  same sites use; this lesson is the natural follow-up — having fail-loud
  paths is necessary but not sufficient.

## Out of Scope

- Migrating to `set -e` / `set -o errexit` to make the subshell propagate
  via a different mechanism. POSIX `set -e` interacts poorly with `||`
  chains and conditional contexts; the explicit guard is more portable
  and more readable.
