---
id: REQ-441
title: "Global cross-repo BUG-ID counter (mirror the global REQ counter)"
status: complete
deployable: true
created: 2026-05-17
updated: 2026-05-17
component: "adlc/bugfix"
domain: "adlc"
stack: ["bash", "markdown"]
concerns: ["concurrency", "correctness", "cross-repo"]
tags: ["global-counter", "bug-counter", "mkdir-lock", "cross-repo", "id-allocation", "next-bug"]
---

## Description

`~/.claude/.global-next-req` is already a machine-global, cross-repo atomic
counter so a REQ id resolves to exactly one work item across every repo on
the machine (architecture.md "Atomic REQ counter"; the REQ-380 global-counter
policy in project-overview.md). BUG ids have **no** such guarantee:
`bugfix/SKILL.md` Phase 1 still allocates from a per-project
`.adlc/.next-bug`, so two repos independently mint `BUG-0xx` collisions and
cross-repo references (branch names, lesson `req:` fields, links) become
ambiguous.

This REQ migrates BUG-ID allocation to a global
`~/.claude/.global-next-bug`, using the **same hardened allocation pattern**
the REQ counter uses: a POSIX `mkdir`-based lock, a `[ -L ]` symlink
pre-check (LESSON-014), empty/unreadable-counter fail-loud guards, and a
parent-context guard because `exit 1` inside `$(...)` only exits the
subshell (LESSON-015). It also adds the first-run bootstrap that seeds the
global counter from the cross-repo highest existing `BUG-xxx`, and updates
`init/SKILL.md`'s `.gitignore` guidance so consumer projects ignore the
deprecated per-project counters.

This also reconciles documentation with reality: because `~/.claude/skills/`
is a symlink to this checkout, the in-progress `bugfix/SKILL.md` edit has
already been the live skill — `BUG-054` and `BUG-056` were in fact
allocated from `~/.claude/.global-next-bug` while the committed
`origin/main` `bugfix/SKILL.md` still documents the deprecated per-project
counter. Committing this REQ makes the committed/documented behavior match
what already runs.

The implementation already exists as captured WIP
(`~/adlc-wip-backup-2026-05-17/thread1-global-bug-counter.patch`) and
applies cleanly onto current `origin/main`.

## System Model

_No data model — this is skill-definition (markdown) behavior. The relevant
contract is the BUG-ID allocation procedure._

### Components

| Component | Responsibility | Contract change |
|-----------|----------------|------------------|
| `bugfix/SKILL.md` Phase 1 | Allocate the next BUG id | Read/increment `~/.claude/.global-next-bug` under a `mkdir` lock with symlink pre-check + fail-loud guards; first-run bootstrap scans cross-repo highest `BUG-xxx`; legacy `.adlc/.next-bug` no longer read or written |
| `init/SKILL.md` Step 5 | `.gitignore` guidance for new consumer projects | Document both counters as global; mark per-project counters deprecated; add `.adlc/.next-req` next to `.adlc/.next-bug` in the ignored list |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| BUG id allocated | `/bugfix` Phase 1 with a new bug description | `BUG_NUM` from `~/.claude/.global-next-bug`; counter incremented atomically |

### Permissions

_Not applicable — local developer tooling, no auth surface._

## Business Rules

- [ ] BR-1: `bugfix/SKILL.md` MUST allocate BUG ids from
  `~/.claude/.global-next-bug`, never from per-project `.adlc/.next-bug`
  (which is deprecated, neither read nor written).
- [ ] BR-2: The allocation MUST use a POSIX `mkdir` lock with a `[ -L ]`
  symlink pre-check that refuses to proceed if the lock path is a symlink
  (TOCTOU defense). (informed by LESSON-014)
- [ ] BR-3: The allocation MUST fail loud — abort with a non-zero,
  diagnosable error — if the counter is unreadable or empty inside the
  lock, and the parent context MUST re-check `[ -n "$BUG_NUM" ]` because
  `exit 1` inside `$(...)` only terminates the subshell. (informed by
  LESSON-015)
- [ ] BR-4: First run (counter file absent) MUST seed
  `~/.claude/.global-next-bug` from the highest existing `BUG-xxx` found by
  scanning `$ADLC_REPOS_ROOT` (or the repo parent) across all `.adlc/bugs/`,
  using BSD-compatible `grep -oE` + `sed` (no GNU-only flags). (informed by
  LESSON-002, LESSON-003)
- [ ] BR-5: `init/SKILL.md`'s `.gitignore` block MUST list both
  `.adlc/.next-bug` and `.adlc/.next-req` as deprecated/ignored and state
  the counters are global.
- [ ] BR-6: The change is confined to `bugfix/SKILL.md` and
  `init/SKILL.md`; no other skill/file may continue to treat
  `.adlc/.next-bug` as authoritative.

## Acceptance Criteria

- [ ] `bugfix/SKILL.md` Phase 1 reads/increments
  `~/.claude/.global-next-bug` under the mkdir-lock + symlink pre-check +
  empty/unreadable + parent-guard pattern (matches the REQ-counter pattern).
- [ ] First-run bootstrap block present and BSD-portable
  (`grep -oE`/`sed`, no `grep -oP`, no GNU-only flags).
- [ ] Deprecation note for legacy `.adlc/.next-bug` present in
  `bugfix/SKILL.md`.
- [ ] `init/SKILL.md` `.gitignore` guidance updated (both counters global;
  `.adlc/.next-req` + `.adlc/.next-bug` listed as deprecated/ignored).
- [ ] `python3 tools/lint-skills/check.py --root .` exits 0 over the
  toolkit after the change (no `skill-md-corruption` / `balance` /
  `canonical-helper` findings introduced — the new fenced bash is balanced
  and POSIX).
- [ ] `grep -rn '\.adlc/\.next-bug' --include=SKILL.md` shows no remaining
  skill treats it as an authoritative source (only deprecation mentions).
- [ ] Implementation equals the captured WIP patch applied verbatim (the
  pipeline applies it, does not re-derive), with the verify-phase parity
  fixes (canonical inline LESSON-014/015 comments restored; bootstrap
  `find -type f`).
- [ ] `.adlc/context/architecture.md` "Key cross-cutting dependencies"
  gains a line stating BUG ids now use `~/.claude/.global-next-bug` with
  the same `mkdir`-lock + symlink pre-check as the REQ/LESSON/ASSUME
  counters (ADR-2 defers this to Phase 8 `/wrapup` knowledge capture — this
  AC exists so it cannot be silently dropped).

## External Dependencies

- None.

## Assumptions

- The global REQ-counter pattern in `/spec` Step 2 is the canonical
  reference implementation to mirror (same lock/guard shape).
- `~/.claude/.global-next-bug` may already exist on the dev machine (it does
  — the live symlinked skill has been using it); the migration is therefore
  also a documentation/commit reconciliation, not a behavior change on this
  machine.

## Open Questions

- None (scope and mechanism fully specified; implementation already exists
  as the captured patch).

## Out of Scope

- The REQ counter (already global; unchanged).
- Migrating or deleting existing per-project `.adlc/.next-bug` files (left
  in place, simply ignored).
- The LESSON counter (`.adlc/.next-lesson`) — separate concern.
- Any `.adlc/config.yml` / cross-repo schema change.
- A backfill of historical cross-repo BUG-id collisions.

## Retrieved Context

- LESSON-014 (lesson, score 7): POSIX mkdir-locks need a symlink pre-check
  to defend against TOCTOU swap — directly informs BR-2.
- LESSON-015 (lesson, score 5): `exit 1` inside `$(...)` only exits the
  subshell — guard the parent context — directly informs BR-3.
- LESSON-004 (lesson, score 4): /proceed canary/snapshot removal — carries
  the global-counter + cross-repo-pairing rationale this REQ extends to BUG
  ids.
- LESSON-002 (lesson, score 3): cross-repo "primary" is per-REQ — the
  cross-repo-uniqueness motivation that applies equally to BUG ids.
- LESSON-003 (lesson, score 3): sprint worktree collision / counter
  race-condition — concurrency precedent for the lock.
