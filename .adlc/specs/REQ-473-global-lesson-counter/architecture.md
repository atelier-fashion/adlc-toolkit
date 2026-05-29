# Architecture — REQ-473: Global cross-repo LESSON-ID counter

## Approach

Mirror the **canonical global counter pattern** already proven in
`spec/SKILL.md` Step 2 (`~/.claude/.global-next-req`) and `bugfix/SKILL.md`
Phase 1 (`~/.claude/.global-next-bug`, REQ-441): `LOCK=…lock.d`, `mkdir` retry
loop, `[ -L "$LOCK" ]` symlink pre-check, unreadable/empty fail-loud guards,
parent `[ -n "$LESSON_NUM" ]` guard, first-run bootstrap scanning
`$ADLC_REPOS_ROOT` with BSD `grep -oE`/`sed`. Apply it to LESSON-ID allocation
in the **two** places that mint LESSON ids: `wrapup/SKILL.md` Step 4 and
`bugfix/SKILL.md`'s lesson-capture step.

Blast radius (verified by grep, not assumed):
- `.adlc/.next-lesson` is authoritative in exactly two skills:
  `wrapup/SKILL.md` (allocation block ~273–294, plus the Step-4 pointer
  at ~260) and `bugfix/SKILL.md` (allocation block ~204–225). Both must move
  to the global counter in lockstep.
- `.adlc/.next-assume` (ASSUME ids) is a **separate** per-project counter,
  minted only by `/wrapup`, with no cross-repo reference surface. It is
  explicitly **out of scope** — globalizing it would be scope creep (BR-9).
- `init/SKILL.md` `.gitignore` guidance already lists per-project counters;
  the edit adds `.adlc/.next-lesson` + a "LESSON is global" note (additive).
- `.adlc/context/architecture.md` "Key cross-cutting dependencies" currently
  groups LESSON with ASSUME as per-project (line ~103). The edit promotes
  LESSON to the global group (line ~102, with REQ + BUG) and leaves ASSUME as
  the sole remaining per-project counter.
- Historical `.adlc/specs/*/` and `.adlc/knowledge/lessons/LESSON-014*` mention
  `.next-lesson` as frozen history — NOT live logic — and are left untouched.

## Key Decisions

### ADR-1: Replicate the REQ/BUG-counter block exactly (no novel locking)

The REQ counter's lock/guard shape is the proven, reviewed reference (hardened
across REQ-416 verify, LESSON-014, LESSON-015) and was already mirrored once for
BUG ids (REQ-441). LESSON allocation adopts the identical shape
(`~/.claude/.global-next-lesson`, `~/.claude/.global-next-lesson.lock.d`).
Rationale: a third, subtly-different locking implementation is a maintenance and
correctness hazard; uniformity means one mental model and one place to fix
future lock bugs.

### ADR-2: Two allocators, one shared global lock

Unlike REQ-441 (a single allocator in `/bugfix`), LESSON ids are minted by BOTH
`/wrapup` and `/bugfix`. Today they share the per-project lock
`.adlc/.next-lesson.lock.d` so a concurrent `/wrapup` + `/bugfix` in the same
repo cannot double-allocate. Under the global scheme both MUST point at the
single global lock `~/.claude/.global-next-lesson.lock.d`. This strengthens the
guarantee (mutual exclusion is now machine-wide, covering parallel `/sprint`
pipelines in *different* repos that previously could not collide on LESSON ids
but now share one counter and therefore one lock). Both blocks must be edited in
lockstep; a divergence (one global, one per-project) would silently re-open the
double-allocation window (BR-1, BR-5).

### ADR-3: Scope is exactly four files; ASSUME and the init dedup-example excluded

In scope: `wrapup/SKILL.md`, `bugfix/SKILL.md`, `init/SKILL.md` `.gitignore`
guidance, `.adlc/context/architecture.md`. The `.adlc/.next-assume` counter
stays per-project (ADR rationale: ASSUME has a single intra-repo allocator and
no cross-repo reference surface — there is no ambiguity to fix). Any unrelated
`.next-lesson 2`-style dedup-example strings in `init/SKILL.md` (if present) are
illustrative filenames, not authoritative readers, and are left untouched
(mirrors REQ-441 ADR-2's treatment of `.next-bug 2`).

### ADR-4: Faithful mirror — port the comments and `-type f`, not just the mechanism

Per LESSON-023 (the REQ-441 retro), a patch that reproduces a hardened pattern's
*behavior* is not a faithful mirror. The four canonical inline rationale
comments (lock-acquire hard-fail / REQ-416 verify C1; counter-read hard-fail /
M2; rmdir TOCTOU residual / LESSON-014; subshell-`exit`-only-exits-subshell
parent guard / LESSON-015) MUST be ported verbatim. The bootstrap `find` MUST
use `-path '*/.adlc/knowledge/lessons/LESSON-*' -type f` — lessons are `.md`
files, so the correct sibling-substitution of the spec's `-type d` is `-type f`
(same as `/bugfix`'s `BUG-*` scan). The verify gate diffs the new block
**against the canonical block**, accounting for every differing line as either a
deliberate `REQ`/`BUG`→`LESSON` (or `-type d`→`-type f`) substitution or an
accidental omission to restore. (informed by LESSON-023)

### ADR-5: No-renumber migration + explicit counter seeds (incl. stale-BUG fix)

Migration mirrors REQ-380's intentional-gap policy: existing LESSON files are
NOT renumbered. The bootstrap dry-run revealed the counter is machine-global
across ALL ADLC repos under the repos root — atelier-fashion (max 233),
**infrastructure (max 312)**, atelier-web (max 67), admin-api (max 34),
adlc-toolkit (max 23) — not just two. Their low LESSON ranges already collide
heavily (LESSON-001..023 in four-plus repos); those collisions are frozen
history, and the global counter fast-forwards past the machine-wide max so every
future id is unique. Implementation seeds two machine-local counter files (NOT
version-controlled — they live in `~/.claude/`, outside any repo):
- `~/.claude/.global-next-lesson` ← `313` (machine-wide max LESSON file = 312, in infrastructure).
- `~/.claude/.global-next-bug` ← `67` (corrects the stale `65`; machine-wide max BUG
  file = 066). This is an operational counter-value fix — the BUG allocation
  *logic* is already global (REQ-441) and unchanged. Folded in because the
  user's goal is correct/universal numbering for BOTH bug and lesson.

The BR-4 bootstrap is the self-healing fallback if a counter file is ever
absent at allocation time; the explicit seed makes the first post-migration
allocation deterministic regardless.

### ADR-6: Verification is the lint-skills linter + grep assertions, plus a live dogfood

Per conventions, skills are markdown — there is no unit-test runner for skill
behavior; dogfooding is the test. Objective gates:
`python3 tools/lint-skills/check.py --root .` exits 0 (the new fenced bash is
balanced + POSIX), and grep assertions that both skills read
`~/.claude/.global-next-lesson`, no skill still treats `.adlc/.next-lesson` as
authoritative, and `.adlc/.next-assume` is unchanged from `main`. A genuine
end-to-end test arrives for free: **this REQ's own `/wrapup` lesson capture will
be the first global allocation (LESSON-313)** — a live proof the new block
works, exercised before merge.

## Applicable Lessons

- **LESSON-023** — faithful-mirror discipline: port the rationale comments and
  `-type` discipline, not just the mechanism (ADR-4). This REQ is the direct
  application of the REQ-441 retro.
- **LESSON-014** — POSIX mkdir-locks need a `[ -L ]` symlink pre-check (TOCTOU);
  ported verbatim into both blocks.
- **LESSON-015** — `exit 1` inside `$(...)` only exits the subshell; the parent
  `[ -n "$LESSON_NUM" ]` guard is the required defense.
- **LESSON-004 / LESSON-002** — global-counter + cross-repo-uniqueness rationale
  (REQ ids) extended here to LESSON ids; underpins the no-renumber migration.
- **LESSON-003** — sprint worktree / counter race precedent for the shared lock.

## Proposed additions to `.adlc/context/architecture.md`

Done as part of this REQ (BR-7, not deferred — unlike REQ-441 ADR-2 which
deferred its one-line doc edit to wrapup, this REQ's doc edit is a structural
move of LESSON between two existing bullets and is core to the change):
move the LESSON counter into the global-counter group (with REQ + BUG), leave
`.adlc/.next-assume` as the sole per-project counter, and update the shared-lock
note to `~/.claude/.global-next-lesson.lock.d`.

## Task Graph

```
TASK-054 (migrate LESSON allocation to global counter in wrapup/SKILL.md +
          bugfix/SKILL.md; update init/SKILL.md gitignore guidance +
          architecture.md; seed counters; verify lint + grep)
```

Single task — primary repo `adlc-toolkit`, no dependencies. The change is a
coherent multi-file migration of one mechanism; splitting wrapup-vs-bugfix-vs-
init into separate tasks would be over-granular (no parallelism or review
benefit, and the two allocation blocks must move in lockstep per ADR-2).
