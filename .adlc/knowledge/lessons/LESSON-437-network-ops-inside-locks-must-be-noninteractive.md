---
id: LESSON-437
title: "Network operations inside a lock must be forced non-interactive — a credential prompt while holding a mkdir lock hangs every allocator on the machine"
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "git"]
concerns: ["concurrency", "reliability"]
tags: ["mkdir-lock", "credential-prompt", "git-terminal-prompt", "hang", "degradation", "git-push"]
req: REQ-546
created: 2026-07-23
updated: 2026-07-23
---

## What Happened

REQ-546 places the reservation `git push` inside the existing mkdir-lock
critical section (it must be atomic with the counter fast-forward). Phase-5
review flagged a Major: on a machine with missing/expired credentials, git
would open an interactive username/password prompt — inside a non-interactive
skill context, with the lock held. The prompt never completes, the lock is
never released, and every subsequent allocation on the machine spins through
its 50×0.1s acquisition budget and hard-fails. The fix: force non-interactive
(`GIT_TERMINAL_PROMPT=0`, and `core.askPass=`/`SSH_ASKPASS` handling as
applicable) on the reservation push, the ls-remote probes, and the doctor
probe — a credential gap now fails in milliseconds and routes into the
loud-not-blocking degraded path (BR-4) instead of hanging.

## Lesson

Any network call executed while holding a lock must be provably
non-blocking-on-input: force the tool's non-interactive mode and let failure
flow into the designed degradation path. Interactive prompts are a
liveness hazard that testing rarely catches (developer machines have
credentials; CI has none but also no TTY), so the guard must be structural
in the code, not assumed from the environment. Corollary: keep the
lock-held region minimal — everything that CAN run before acquisition
(derivation, classification) should.

## Why It Matters

A hang inside a critical section is strictly worse than a failure: it
converts one machine's auth problem into a machine-wide allocation outage
with no error pointing at the cause, and the mkdir-lock idiom has no owner
liveness detection — the stale lock persists until a human removes it.

## Applies When

- Adding any `git push`/`fetch`/`ls-remote`, curl, or API call inside a
  lock-held region or any non-interactive skill fence.
- Reviewing lock-region diffs: ask "can anything in here wait on a human?"
