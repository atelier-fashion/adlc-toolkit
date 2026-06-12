---
id: REQ-518
title: "Collision-Safe ID Allocation Across Users and Machines — Architecture"
status: draft
created: 2026-06-11
updated: 2026-06-11
---

# Architecture — REQ-518

## Overview

Today three near-identical inline shell blocks (`/spec` → REQ, `/bugfix` → BUG,
`/wrapup` + `/bugfix` → LESSON) each allocate an id from a machine-local counter
under `~/.claude/.global-next-*`, protected by an `mkdir`-lock with a
symlink-precheck. The blocks see only the local filesystem, so two users on two
machines allocate the same next id and collide at PR time.

This REQ adds **remote-derived high-water** to allocation and a **pre-push
recheck** so the remote is the source of truth, and extracts the duplicated
allocation logic into a single parameterized partial (BR-5). It also ships an
automated `adlc renumber` helper (BR-9) registered additively in the REQ-519
umbrella CLI (data-driven `SUBCOMMANDS` table — REQ-519 BR-11), so a detected
collision has a one-command fix.

The design is strictly **additive** at the umbrella CLI (one `SUBCOMMANDS`
entry + one lazy handler + one new module — no dispatch-logic edits) to minimize
merge overlap with REQ-516, which registers its own subcommand concurrently
(REQ-519 BR-11 keeps both purely data-driven).

## Components

### 1. `partials/id-alloc.sh` (NEW) — shared allocation helper (BR-1, BR-5)

A sourceable POSIX partial modeled on `partials/trial-merge.sh` (prefixed
globals, no `local`, portable across `sh`/`bash`/`zsh`, fail-loud). It exports:

- `adlc_id_kind_counter <kind>` / `adlc_id_kind_lockdir <kind>` /
  `adlc_id_kind_prefix <kind>` / `adlc_id_kind_scan_glob <kind>` — pure mappers
  from `req|bug|lesson` to the counter path, lock dir, id prefix (`REQ|BUG|LESSON`),
  and bootstrap scan glob/type. One table, three kinds (BR-8: one namespace per kind).
- `adlc_remote_high <kind>` (BR-2) — derives the remote high-water **from the
  remote, not local clones**: `git ls-remote --heads <remote>` across the
  participating repos for `feat/REQ-*` / `fix/bug-*` branch patterns, plus merged
  artifact directories reachable from the default branch (via `gh api` when
  available, degraded to a shallow `git ls-remote` ref/`ls-tree` scan when not).
  Stale local checkouts can never *lower* the result. Prints the max remote
  number (0 if none / unreachable) and sets `ADLC_ALLOC_DEGRADED=1` + a warning
  on its stderr if any configured remote was unreachable (BR-3).
- `adlc_alloc_id <kind>` (BR-1) — the orchestration: acquire the existing
  `mkdir` lock with the symlink-precheck and fail-loud guards **ported verbatim
  with their rationale comments** (BR-1, BR-6, LESSON-014/023); read `local_high`
  from the counter (bootstrap-scan if absent, same as today); compute
  `remote_high = adlc_remote_high <kind>`; allocate `max(local_high, remote_high) + 1`;
  fast-forward the local counter to the allocated value; release the lock. Prints
  the allocated **number** on stdout. On any degradation, leaves
  `ADLC_ALLOC_DEGRADED=1` set so the caller can record the unverified-allocation
  assumption (BR-3).

The local counter becomes a **cache**, not an authority (Description). Single-user
single-machine behavior is unchanged: on a machine that did all the allocating,
`remote_high ≤ local_high`, so `max(...) + 1` equals today's value (BR-7).

### 2. `partials/id-recheck.sh` (NEW) — pre-push / PR-time recheck (BR-4, BR-8)

Exports `adlc_recheck_id <kind> <id>`: re-derives `adlc_remote_high <kind>` and
checks whether `<id>` is already present on the remote (a pushed
`feat/REQ-<id>` / `fix/bug-<id>` branch, or a merged artifact dir/file). On
collision it returns non-zero and prints a **halt message naming the exact
`adlc renumber <KIND-old> <KIND-new>` command** to run (BR-4, BR-9). Used at:
- `/proceed` before `git worktree add -b feat/REQ-xxx` (branch creation).
- `/bugfix` before the bug file is committed on a branch for push.
- `/wrapup` (+ `/bugfix` lesson capture) before the lesson file is committed for push.

It never blocks on network: an unreachable remote degrades to a loud warning and
proceeds (BR-3) — the recheck can only *find* a collision, never *invent* one
from absence of data.

### 3. `tools/adlc/renumber.py` (NEW) — automated renumber helper (BR-9)

A pure-stdlib module with `main(argv) -> int`, mirroring `doctor.py`'s shape.
`adlc renumber <KIND-old> <KIND-new>`:
1. Validates both ids against strict per-kind regexes
   (`^REQ-[0-9]{3,}$` etc. — LESSON-008, reject traversal/garbage).
2. Refuses if `<KIND-new>` fails the same remote-collision check (BR-9) — shells
   out to `partials/id-recheck.sh` so there is one collision authority.
3. Computes the rename set: artifact dir/file, frontmatter `id:`, in-repo
   cross-references to the old id (`grep -rl`, scoped, git-history excluded).
4. Prints a **dry-run unified diff** and requires approval before mutating
   (LESSON-006 fail-loud, atomic — write to temp + rename, never partial).
5. Applies the rename atomically; for a REQ with an existing branch, prints the
   exact `git branch -m` / push / delete-old-remote commands (does NOT run them).

Registered in `adlc.py` by appending ONE `SUBCOMMANDS` entry and ONE
`_cmd_renumber` lazy handler — no change to `main()` / `_usage()` / dispatch
(REQ-519 BR-11; keeps REQ-516's concurrent subcommand merge-clean).

### 4. Skill wiring (EDIT, scoped) — `spec/`, `bugfix/`, `wrapup/` SKILL.md

Each inline allocation block is replaced by a sourced-partial call **in the same
fenced block** as the invocation (the cross-fence-fn rule — conventions.md
"Bash in skills", enforced by `tools/lint-skills`):

```bash
. .adlc/partials/id-alloc.sh 2>/dev/null || . ~/.claude/skills/partials/id-alloc.sh
REQ_NUM=$(adlc_alloc_id req)
[ -n "$REQ_NUM" ] || { echo "ERROR: failed to allocate REQ number — aborting" >&2; exit 1; }
```

and a recheck call is added at each skill's push/branch-creation point. Edits are
**strictly scoped to the allocation/recheck blocks** — the PR/push call sites in
`/bugfix` and `/wrapup` that REQ-520 will touch are left untouched (launch-prompt
constraint).

### 5. Tests

- `tools/adlc/tests/test_renumber.py` — pytest (offline, sandbox tmp repo),
  mirroring `test_doctor.py`/`test_dispatch.py` conventions: id-regex validation,
  dry-run-then-apply, frontmatter+reference rewrite, zero-remaining-old-id grep,
  collision-refusal, and a dispatch test that `adlc renumber` is registered.
- `partials/tests/id-alloc.test.sh` — a self-contained POSIX harness exercising
  the AC test matrix (lock contention, symlink-swap refusal, empty-counter
  refusal, remote-ahead, local-ahead, remote-unreachable) against fixture
  `~/.claude` counters + a local bare-repo "remote". Runnable — and run in CI of
  the verify step — under **both** `bash -c` and `zsh -c` (BR-6, Linux parity AC).

## ADRs

### ADR-1: One parameterized partial, not three (BR-5)
The three allocation blocks differ only in counter path, lock dir, id prefix, and
scan glob. Parameterizing by `kind` collapses them to one audited code path.
Rationale comments from the original blocks are ported into the partial (BR-1,
LESSON-023 — mirror the rationale, not just the mechanism), and the SKILL.md
call sites carry a one-line pointer to the partial.

### ADR-2: Remote derivation reuses the `/manifest` model (BR-2)
The observable remote footprint of an allocation is `feat/REQ-xxx` branch names
and merged artifact directory names — the same derive-don't-store surface
`/manifest` already reads. We reuse that model (`git ls-remote` + optional
`gh api`) rather than inventing a new remote store, honoring "no infrastructure
beyond git remotes" (Out of Scope).

### ADR-3: Recheck is a separate partial from allocation (BR-4)
Allocation runs at spec/bug/lesson *creation*; the recheck runs later at
*push/branch* time — different call sites, different skills. Keeping
`id-recheck.sh` separate avoids loading the full allocation machinery at recheck
time and gives `renumber.py` a single collision authority to shell out to.

### ADR-4: Renumber lives in the umbrella CLI, additively (BR-9, REQ-519 BR-11)
Per the spec's resolved decision, renumber is a subcommand of the existing
`adlc` CLI, not a standalone script. Registration is one `SUBCOMMANDS` entry +
one lazy handler — zero dispatch-logic edits — so it merges cleanly alongside
REQ-516's concurrent subcommand addition.

### ADR-5: Degradation is loud and never blocks (BR-3)
Network failure during remote derivation never blocks spec/bug/lesson writing.
The allocator proceeds from local state, sets `ADLC_ALLOC_DEGRADED=1`, emits a
warning naming the unreachable remote, and the caller records
"id allocated without remote verification — verify before PR" in the spec's
Assumptions. The BR-4 recheck (which DOES run before push, when network is more
likely up) is the safety net for a degraded allocation.

## Task Graph

```
TASK-001 (id-alloc.sh partial) ──┬─> TASK-003 (renumber.py + CLI registration)
                                 ├─> TASK-004 (skill wiring: spec/bugfix/wrapup)
TASK-002 (id-recheck.sh partial)─┘        (TASK-004 depends on 001 & 002)
                                          (TASK-003 depends on 002 for collision authority)
TASK-001,002,003 ──> TASK-005 (test matrix: pytest + bash/zsh harness)
```

- TASK-001 and TASK-002 are independent (both foundational partials).
- TASK-003 (renumber) depends on TASK-002 (shells out to the recheck for BR-9 collision refusal).
- TASK-004 (skill wiring) depends on TASK-001 + TASK-002 (the partials must exist to source).
- TASK-005 (tests) depends on TASK-001, 002, 003 (exercises all three).
