---
id: REQ-473
title: "Global cross-repo LESSON-ID counter (mirror the global REQ/BUG counters)"
status: complete
deployable: true
created: 2026-05-29
updated: 2026-05-29
component: "adlc/wrapup"
domain: "adlc"
stack: ["bash", "markdown"]
concerns: ["concurrency", "correctness", "cross-repo"]
tags: ["global-counter", "lesson-counter", "mkdir-lock", "cross-repo", "id-allocation", "next-lesson"]
---

## Description

`~/.claude/.global-next-req` (REQ ids) and `~/.claude/.global-next-bug` (BUG
ids, REQ-441) are machine-global, cross-repo atomic counters: a REQ or BUG id
resolves to exactly one work item across every repo on the machine
(architecture.md "Key cross-cutting dependencies"; the REQ-380 global-counter
policy). LESSON ids are the lone holdout — `/wrapup` Step 4 and `/bugfix`'s
lesson-capture step still allocate from a **per-project** `.adlc/.next-lesson`,
so every ADLC repo on the machine mints LESSON numbers from its own independent
sequence: atelier-fashion at LESSON-233, **infrastructure at LESSON-312**,
atelier-web at LESSON-067, admin-api at LESSON-034, adlc-toolkit at LESSON-023.
These low ranges overlap massively (LESSON-001..023 exist in four-plus repos at
once), so a bare `LESSON-NNN` reference is deeply ambiguous across repos — far
worse than a two-repo view would suggest. The per-project counters have also
drifted from the on-disk high-water marks (a known failure mode under worktrees
/ parallel `/sprint`). The global REQ and BUG counters already span all of these
repos (they are machine-global at `~/.claude/.global-next-*`, keyed on absolute
paths independent of which repo invokes the skill); LESSON is the only id type
still fragmented per-project.

This REQ migrates LESSON-ID allocation to a global `~/.claude/.global-next-lesson`,
using the **same hardened allocation pattern** the REQ and BUG counters use: a
POSIX `mkdir`-based lock, a `[ -L ]` symlink pre-check (LESSON-014),
empty/unreadable-counter fail-loud guards, and a parent-context
`[ -n "$LESSON_NUM" ]` guard because `exit 1` inside `$(...)` only exits the
subshell (LESSON-015). It adds the first-run bootstrap that seeds the global
counter from the cross-repo highest existing `LESSON-xxx` (`-type f`,
BSD-compatible `grep -oE`/`sed`), and updates `init/SKILL.md`'s `.gitignore`
guidance plus `.adlc/context/architecture.md`.

**Two allocators, one lock.** `/wrapup` and `/bugfix` both mint LESSON ids and
today share the per-project lock path `.adlc/.next-lesson.lock.d` so concurrent
runs mutually exclude. Under the global scheme they MUST share the **global**
lock path `~/.claude/.global-next-lesson.lock.d` to preserve that mutual
exclusion machine-wide. This is the one structural difference from REQ-441
(which had a single allocator): the migration must touch both skills in lockstep.

**Migration follows the REQ-380 "intentional gap" precedent — no renumbering.**
Existing LESSON files are left in place as frozen history in every repo. The
low ranges already collide heavily across repos (e.g. LESSON-001..023 exist in
four-plus repos) — but those collisions are pre-existing and are NOT
retroactively renumbered. The global counter simply fast-forwards past the
machine-wide high-water mark (**312, in infrastructure → seed 313**), exactly as
the REQ counter did across the REQ-264..379 gap, so every *future* LESSON id is
globally unique. The ASSUME counter (`.adlc/.next-assume`) stays **per-project**
— it is only minted by `/wrapup` within a single repo and has no cross-repo
reference surface, so globalizing it would be scope creep.

This REQ also corrects an operational drift it surfaced: `~/.claude/.global-next-bug`
currently holds `65` while the on-disk global max BUG is `066`, so the next
`/bugfix` would re-mint BUG-065/066. The BUG allocation *logic* is already
global and correct (REQ-441) — only the counter *value* is stale — so the fix
is a one-line re-seed to `67`, folded in here as an operational migration step
(no BUG code change). This keeps the user's stated goal ("make BOTH bug and
lesson numbering universal/correct") whole.

## System Model

_No data model — this is skill-definition (markdown) behavior. The relevant
contract is the LESSON-ID allocation procedure._

### Components

| Component | Responsibility | Contract change |
|-----------|----------------|------------------|
| `wrapup/SKILL.md` Step 4 (Fallback drafting) | Allocate the next LESSON id during knowledge capture | Read/increment `~/.claude/.global-next-lesson` under a `mkdir` lock with `[ -L ]` symlink pre-check + fail-loud guards; first-run bootstrap scans cross-repo highest `LESSON-xxx` (`-type f`); legacy `.adlc/.next-lesson` no longer read or written |
| `bugfix/SKILL.md` lesson-capture step (~line 204) | Allocate the next LESSON id after a bug fix | Same global block; shares the global lock `~/.claude/.global-next-lesson.lock.d` with `/wrapup` for mutual exclusion |
| `init/SKILL.md` Step 5 (`.gitignore` guidance) | gitignore advice for new consumer projects | List `.adlc/.next-lesson` as deprecated/ignored alongside `.next-bug`/`.next-req`; note LESSON ids are now global |
| `.adlc/context/architecture.md` "Key cross-cutting dependencies" | Canonical counter-topology doc | Move LESSON into the global-counter group (with REQ + BUG); leave `.adlc/.next-assume` as the sole per-project counter; update the shared-lock note to the global path |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| LESSON id allocated | `/wrapup` Step 4 or `/bugfix` lesson-capture with a lesson worth recording | `LESSON_NUM` from `~/.claude/.global-next-lesson`; counter incremented atomically under the shared global lock |

### Permissions

_Not applicable — local developer tooling, no auth surface._

## Business Rules

- [ ] BR-1: Both `wrapup/SKILL.md` and `bugfix/SKILL.md` MUST allocate LESSON
  ids from `~/.claude/.global-next-lesson`, never from a per-project
  `.adlc/.next-lesson` (deprecated — neither read nor written).
- [ ] BR-2: The allocation MUST use a POSIX `mkdir` lock with a `[ -L ]`
  symlink pre-check that refuses to proceed if the lock path is a symlink
  (TOCTOU defense). (informed by LESSON-014)
- [ ] BR-3: The allocation MUST fail loud — abort with a non-zero, diagnosable
  error — if the counter is unreadable or empty inside the lock, and the parent
  context MUST re-check `[ -n "$LESSON_NUM" ]` because `exit 1` inside `$(...)`
  only terminates the subshell. (informed by LESSON-015)
- [ ] BR-4: First run (counter file absent) MUST seed
  `~/.claude/.global-next-lesson` from the highest existing `LESSON-xxx` found
  by scanning `$ADLC_REPOS_ROOT` (or the repo parent) across all
  `.adlc/knowledge/lessons/`, using BSD-compatible `grep -oE` + `sed` and
  `-type f` (lessons are `.md` files — the bug-sibling discipline, NOT the
  spec's `-type d`). (informed by LESSON-023)
- [ ] BR-5: `/wrapup` and `/bugfix` MUST share the single global lock path
  `~/.claude/.global-next-lesson.lock.d` so concurrent lesson allocation across
  the two skills mutually excludes — preserving the existing shared-lock
  property, now machine-global rather than per-repo. (informed by LESSON-014,
  LESSON-003)
- [ ] BR-6: `init/SKILL.md`'s `.gitignore` block MUST list `.adlc/.next-lesson`
  as deprecated/ignored and state that LESSON ids are global (consistent with
  how `.next-bug`/`.next-req` are documented).
- [ ] BR-7: `.adlc/context/architecture.md` MUST describe the LESSON counter in
  the global-counter group (alongside REQ + BUG) and retain `.adlc/.next-assume`
  as the sole per-project counter, with the shared-lock note updated to the
  global lock path.
- [ ] BR-8: The new global allocation block MUST be a faithful line-by-line
  mirror of the canonical REQ/BUG block — porting the four inline rationale
  comments (lock-acquire hard-fail / REQ-416 C1, counter-read hard-fail / M2,
  rmdir TOCTOU residual / LESSON-014, subshell parent guard / LESSON-015) and
  the `-type f` discipline. Every divergence from the canonical block MUST be a
  documented deliberate sibling-substitution (REQ/BUG→LESSON, `-type d`→`-type f`),
  not an accidental omission. (informed by LESSON-023)
- [ ] BR-9: The change is confined to `wrapup/SKILL.md`, `bugfix/SKILL.md`,
  `init/SKILL.md`, and `.adlc/context/architecture.md`; no other skill/file may
  continue to treat `.adlc/.next-lesson` as authoritative, and the
  `.adlc/.next-assume` (ASSUME) counter MUST remain per-project (NOT globalized
  by this REQ).

## Acceptance Criteria

- [ ] `wrapup/SKILL.md` Step 4 and `bugfix/SKILL.md` lesson-capture read/increment
  `~/.claude/.global-next-lesson` under the mkdir-lock + symlink pre-check +
  empty/unreadable + parent-guard pattern (matches the REQ/BUG block).
- [ ] Both allocators reference the shared global lock
  `~/.claude/.global-next-lesson.lock.d` (BR-5).
- [ ] First-run bootstrap block present, BSD-portable (`grep -oE`/`sed`, no
  `grep -oP`), and uses `-path '*/.adlc/knowledge/lessons/LESSON-*' -type f`.
- [ ] Deprecation note for legacy `.adlc/.next-lesson` present in BOTH
  `wrapup/SKILL.md` and `bugfix/SKILL.md`; the Step-4 pointer at
  `wrapup/SKILL.md:~260` updated to the global counter.
- [ ] `init/SKILL.md` `.gitignore` guidance updated (`.adlc/.next-lesson`
  deprecated/ignored; LESSON noted global).
- [ ] `.adlc/context/architecture.md` updated per BR-7.
- [ ] `python3 tools/lint-skills/check.py --root .` exits 0 over the toolkit
  after the change (no new `skill-md-corruption` / `balance` /
  `canonical-helper` findings — the new fenced bash is balanced and POSIX).
- [ ] `grep -rn '\.adlc/\.next-lesson' --include=SKILL.md` shows no skill treats
  it as an authoritative source (only deprecation mentions remain).
- [ ] `grep -rn '\.adlc/\.next-assume' --include=SKILL.md` is unchanged from
  `main` — ASSUME stays per-project (regression guard for BR-9).
- [ ] Operational: `~/.claude/.global-next-lesson` seeded to `313` (machine-wide
  max LESSON file = 312, in the infrastructure repo; verified by cross-repo scan
  across all `.adlc/` repos under the repos root).
- [ ] Operational: `~/.claude/.global-next-bug` corrected from `65` to `67`
  (global max BUG file = 066; eliminates the latent BUG-065/066 re-mint). No
  BUG code change.

## External Dependencies

- None.

## Assumptions

- The global REQ/BUG-counter block (`/spec` Step 2, `/bugfix` Phase 1) is the
  canonical reference implementation to mirror (same lock/guard shape).
  (informed by LESSON-023)
- Extensive LESSON collisions ALREADY exist across the machine's ADLC repos
  (the per-project counters overlap — LESSON-001..023 exist in four-plus repos;
  the machine-wide max is 312 in infrastructure). The no-renumber migration
  freezes all existing files as history; fast-forwarding the global counter past
  the machine-wide max (312) guarantees every FUTURE id is unique without
  touching history — the REQ-380 intentional-gap precedent. (informed by
  LESSON-004)
- `~/.claude/.global-next-lesson` does not yet exist (verified absent); seeding
  it explicitly to 313 makes the first post-migration allocation deterministic,
  with the BR-4 bootstrap as a self-healing fallback. The bootstrap scan is
  machine-wide by design (same as the REQ/BUG counters) — it intentionally spans
  every `.adlc/` repo under the repos root, not just two.

## Open Questions

- None (mechanism fully specified; this is a faithful mirror of REQ-441's
  approach applied to the sibling LESSON counter).

## Out of Scope

- The REQ and BUG counter *logic* (already global; unchanged). Only the stale
  BUG counter *value* is corrected operationally.
- The ASSUME counter (`.adlc/.next-assume`) — remains per-project (single-skill,
  intra-repo; no cross-repo reference surface).
- Renumbering existing LESSON files or backfilling gaps (frozen history; the
  REQ-380 intentional-gap precedent).
- The pre-existing cross-repo BUG-054 duplicate (frozen history — operator
  decision).
- Migrating or deleting existing per-project `.adlc/.next-lesson` files (left in
  place, simply ignored).
- atelier-fashion's `CLAUDE.md` narrative (a consumer-repo doc; REQ-441 likewise
  did not touch it — optional follow-up).

## Retrieved Context

- LESSON-023 (lesson, score 9): When mirroring a hardened pattern to a sibling,
  port the rationale comments + type-discipline, not just the mechanism —
  directly informs BR-4 and BR-8; this is the REQ-441 retro this REQ exists to
  apply.
- LESSON-014 (lesson, score 7): POSIX mkdir-locks need a `[ -L ]` symlink
  pre-check (TOCTOU) — directly informs BR-2 and BR-5.
- LESSON-015 (lesson, score 5): `exit 1` inside `$(...)` only exits the subshell
  — guard the parent context — directly informs BR-3.
- LESSON-004 (lesson, score 4): global-counter + cross-repo-uniqueness rationale
  (REQ ids) — the motivation extended here to LESSON ids; informs the
  no-renumber migration.
- LESSON-002 (lesson, score 3): cross-repo "primary" is per-REQ — the
  cross-repo-ambiguity motivation that applies equally to LESSON ids.
- LESSON-003 (lesson, score 3): sprint worktree collision / counter race —
  concurrency precedent for the shared lock (BR-5).
- REQ-441 (spec, score 8): the immediate predecessor — global BUG counter; same
  approach, same canonical source.
- REQ-416 (spec, score 4): lock TOCTOU hardening — the provenance of the inline
  rationale comments BR-8 requires.
