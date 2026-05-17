# Architecture — REQ-441: Global cross-repo BUG-ID counter

## Approach

Mirror the **canonical global REQ-counter pattern** already in
`spec/SKILL.md` Step 2 (lines ~198–233: `~/.claude/.global-next-req`,
`LOCK=…lock.d`, `mkdir` retry loop, `[ -L "$LOCK" ]` symlink pre-check,
unreadable/empty fail-loud guards, parent `[ -n "$REQ_NUM" ]` guard,
first-run bootstrap scanning `$ADLC_REPOS_ROOT` with BSD `grep -oE`/`sed`)
onto BUG-ID allocation in `bugfix/SKILL.md` Phase 1. The implementation
already exists verbatim as the captured WIP patch
(`~/adlc-wip-backup-2026-05-17/thread1-global-bug-counter.patch`) and
applies cleanly onto current `origin/main`.

Blast radius (verified by grep, not assumed):
- `.adlc/.next-bug` is authoritative **only** in `bugfix/SKILL.md:34–39`
  (the allocation two-liner + the "doesn't exist" bootstrap line). Nothing
  else reads it as a source of truth.
- `init/SKILL.md:130` already lists `.adlc/.next-bug` in the `.gitignore`
  guidance block; the patch reword + `.adlc/.next-req` addition is
  additive/clarifying, not a new entry.
- `init/SKILL.md:159` (`".next-bug 2"`) is an **illustrative filename in
  the duplicate-file cleanup note** — a different concern, explicitly **out
  of scope**, left untouched.
- No other skill/file references `global-next-bug` on `origin/main` yet
  (the live behavior only exists via the `~/.claude/skills/` symlink to the
  dirty checkout — this REQ commits it).

## Key Decisions

### ADR-1: Replicate the REQ-counter pattern exactly (no novel locking)

The REQ counter's lock/guard shape is the proven, reviewed reference
(hardened across REQ-416 verify, LESSON-014, LESSON-015). BUG allocation
adopts the identical shape (`~/.claude/.global-next-bug`,
`~/.claude/.global-next-bug.lock.d`). Rationale: a second, subtly-different
locking implementation is a maintenance and correctness hazard; uniformity
means one mental model and one place to fix future lock bugs.

### ADR-2: Scope is exactly two files; `init/SKILL.md:159` excluded

`bugfix/SKILL.md` Phase 1 allocation block (the only authoritative reader)
and `init/SKILL.md` Step 5 `.gitignore` guidance (consumer-project
gitignore advice). The unrelated `.next-bug 2` dedup-example string at
`init/SKILL.md:159` is deliberately **not** touched — changing it would be
scope creep into an orthogonal cleanup note.

### ADR-3: Implementation = apply the captured WIP patch verbatim

`/proceed`'s implement phase applies
`thread1-global-bug-counter.patch` exactly, rather than re-deriving the
block. The patch already encodes LESSON-014 (`[ -L "$LOCK" ]` TOCTOU
pre-check) and LESSON-015 (parent `[ -n "$BUG_NUM" ]` guard for the
`exit 1`-only-exits-subshell trap). Re-deriving risks drift from the
canonical REQ-counter block this REQ exists to mirror.

### ADR-4: Verification is the lint-skills linter + grep assertions, not unit tests

Per conventions.md, skills are markdown — there is no unit-test runner for
skill behavior; dogfooding is the test. The objective gates are:
`python3 tools/lint-skills/check.py --root .` exits 0 (the new fenced bash
is balanced + POSIX — the REQ-425/436 corruption linter, now non-vacuous
from a worktree thanks to REQ-435/436), and grep assertions that
`bugfix/SKILL.md` reads `~/.claude/.global-next-bug` and no skill still
treats `.adlc/.next-bug` as authoritative. Real-world validation already
exists: BUG-054 and BUG-056 were allocated through this exact global-counter
logic (the live symlinked skill), and both produced collision-free ids.

## Applicable Lessons

- **LESSON-014** — POSIX mkdir-locks need a `[ -L ]` symlink pre-check
  (TOCTOU). The patch's lock block includes it; verify it survives.
- **LESSON-015** — `exit 1` inside `$(...)` only exits the subshell; the
  patch's parent `[ -n "$BUG_NUM" ]` guard is the required defense.
- **LESSON-004 / LESSON-002** — the global-counter + cross-repo-uniqueness
  rationale (REQ ids) extended here to BUG ids.
- **LESSON-013 / LESSON-016 (lint-skills)** — the verification linter must
  not be vacuous; run it from the worktree (REQ-435/436 already made the
  walk root-relative, so `--root .` inside `.worktrees/REQ-441` genuinely
  scans).

## Proposed additions to `.adlc/context/architecture.md`

One line under "Key cross-cutting dependencies": note that BUG ids now use
`~/.claude/.global-next-bug` with the same `mkdir`-lock + symlink pre-check
as the REQ/LESSON/ASSUME counters. Deferred to `/wrapup` knowledge capture
rather than done here (keeps the diff to the two in-scope files; ADR-2).

## Task Graph

```
TASK-053 (apply the captured WIP patch to bugfix/SKILL.md + init/SKILL.md; verify lint + grep)
```

Single task — primary repo `adlc-toolkit`, no dependencies. The change is a
coherent two-file migration whose implementation already exists; splitting
into bugfix-vs-init tasks would be over-granular (one would be a one-line
edit) for no parallelism or review benefit.
