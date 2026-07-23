# Architecture — REQ-546 Atomic remote id reservation at allocation time

## Summary

Close the allocation-to-visibility window (REQ-518 left open) by making the
allocator **atomically reserve** its candidate number on the remote *before*
returning the id. The reservation is a lightweight git ref
`refs/adlc/ids/<kind>/<NNN>` pushed over pure git transport. Ref-creation over
push is first-wins when each allocator pushes a **distinct object**; the loser
of a concurrent race is rejected (`non-fast-forward`), retries with the next
number, and the namespace stays collision-free. The reservation namespace
becomes a **first-class derivation source** in `adlc_remote_high` and an exact
probe in `adlc_recheck_id`, so a reservation made seconds ago on another laptop
raises every other machine's high-water immediately — no branch push, no merge.

All mechanism lives in `partials/id-alloc.sh` (allocation + derivation),
`partials/id-recheck.sh` (recheck probe), `tools/adlc/renumber.py` (reserve
before renumber), `tools/adlc/checks.py` (doctor pushability check), and
`wrapup/SKILL.md` (route ASSUME through the mechanism). No new external
dependency; GitHub and Azure DevOps behave identically (REQ-523 forge-parity
posture preserved).

## Empirically-verified git behavior (classification is load-bearing — BR-5)

Reservation push `git push origin "${obj}:refs/adlc/ids/<kind>/<NNN>"` outcomes,
captured against a local bare remote during design:

| Outcome | exit | stderr signal | Action |
|---|---|---|---|
| Won (ref created) | 0 | `* [new reference] … -> refs/adlc/ids/…` | fast-forward counter, return |
| Race lost (ref exists, our object unrelated) | 1 | `! [rejected] … (non-fast-forward)` | retry with next number (BR-5) |
| Server policy decline | 1 | `! [remote rejected] … (pre-receive hook declined)` | DEGRADED — non-blocking (BR-4) |
| Transport/auth failure | 128 | `fatal: Could not read from remote …` | DEGRADED — non-blocking (BR-4) |
| Same object pushed twice | 0 | `Everything up-to-date` | no-op — the BR-2 hazard the nonce defeats |

`! [remote rejected]` does **not** contain the substring `! [rejected]`, so the
two are distinguishable by literal match. Classifier order: check
`[remote rejected]` / `pre-receive hook declined` FIRST (→ degraded), then plain
`[rejected]` (→ race retry), else degraded. This is the required
rejection-vs-transport distinction (BR-5); a pre-receive decline must degrade
(BR-4), NOT spin the retry loop.

## Shell-safety notes (BR-10)

- **`${obj}:refs/...` MUST use braces.** Bare `$obj:refs` triggers zsh's `:r`
  history modifier and silently corrupts the refspec (verified: the SHA was
  concatenated with `efs/...`). Every refspec is built as
  `"${obj}:refs/adlc/ids/${kind}/${num}"`. (LESSON-335 class.)
- **`ls-remote` glob quoting.** `git ls-remote origin "refs/adlc/ids/$kind/*"` —
  the `*` is inside double quotes so the shell never globs it; git receives it
  literally and fnmatch-matches the namespace (verified working).
- **List iteration via positional params.** `adlc_remote_high` iterates the
  participating-repo set with `set --` + `for x in "$@"`, never `for x in $var`
  (zsh does not word-split unquoted expansions — BUG-116).
- Decimal-normalize every extracted number before arithmetic (octal trap,
  LESSON-396); maximal-munch extraction + exact-equality compare (prefix-sibling
  safe: 120 never matches 1200).

## New / changed surfaces

### `partials/id-alloc.sh`

1. **Fourth kind `assume`** added to the kind mappers:
   - `adlc_id_kind_prefix assume` → `ASSUME`
   - `adlc_id_kind_counter assume` → `<repo-toplevel>/.adlc/.next-assume` (per-repo, NOT machine-global)
   - `adlc_id_kind_lockdir assume` → `<repo-toplevel>/.adlc/.next-assume.lock.d`
   - `adlc_id_kind_artifact_path assume` → `.adlc/knowledge/assumptions`
   - `adlc_id_kind_scan assume` → `*/.adlc/knowledge/assumptions/ASSUME-* f`
   The per-repo counter path is resolved via `git rev-parse --show-toplevel`;
   allocation of `assume` outside a git repo fails loud.

2. **`adlc_reservation_nonce`** — a distinct-payload nonce: hex from
   `/dev/urandom` (via `od`) when available, always combined with `date +%s` and
   `$$`. Guarantees two allocators computing the same candidate build different
   commit objects (BR-2).

3. **`adlc_reserve_id <repo> <kind> <num>`** — builds a distinct object
   (`git commit-tree` of the empty tree, message carries kind/num/nonce, author
   identity from git config), pushes `"${obj}:refs/adlc/ids/${kind}/${num}"` to
   the repo's `origin`, and classifies the result: return **0**=won, **1**=race
   lost, **2**=degraded (per the table above). Push output captured with `2>&1`
   so nothing leaks to the allocator's stdout.

4. **`adlc_remote_reservation_nums <repo> <kind>`** — `ls-remote` the reservation
   namespace, extract the trailing number of each ref. rc 0 iff the scan ran.

5. **`adlc_remote_high`** gains the reservation namespace as a **third
   independent source** alongside branches and merged artifacts (BR-3, REQ-523
   BR-1 independence — one source failing never skips the others). The
   participating-repo set is now kind-scoped: **assume → the current repo only**
   (BR-12, no branch source); **req/bug/lesson → all repos under
   `$ADLC_REPOS_ROOT`** (BR-11). Iteration refactored to positional params so the
   single-repo (assume) and multi-repo (global) cases share one body.

6. **`adlc_alloc_id`** — after computing `ALLOC = max(remote, local) + 1` inside
   the existing mkdir lock, runs the **reservation retry loop** (BR-1, BR-5):
   push-reserve `ALLOC`; on race-lost `ALLOC++` and retry (bounded, default 10,
   `ADLC_RESERVE_MAX_TRIES`); on won, break; on degraded, warn and proceed
   unreserved (non-blocking, BR-4). Exhausting all retries fails loud (BR-5). The
   counter fast-forward and the lock's symlink/TOCTOU guards are unchanged.

### `partials/id-recheck.sh`

`adlc_recheck_id`'s exact-id presence probe gains a reservation check:
`git ls-remote origin "refs/adlc/ids/<kind>/<num>"` (exact ref path → exact
match, prefix-sibling safe). A reservation-only collision now halts with the
renumber instruction (BR-3). High-water/degraded already flow from
`adlc_remote_high`, so the reservation source is inherited automatically.

### `tools/adlc/renumber.py`

Before mutating, after the existing new-id remote-collision refusal, **reserve
the new id** via the same mechanism (shell out to a small `adlc_reserve_id`
call in `id-alloc.sh`, mirroring how `remote_collision` shells out to
id-recheck.sh — one authority, BR-8). The old id's reservation is left in place
(the old number stays burned). A degraded reservation does not block the
renumber (parity with the degraded posture everywhere else).

### `tools/adlc/checks.py`

New `check_reservations` (registered after `forge`): resolves `origin`, probes
the reservation namespace **readable** (`ls-remote`) and **writable** via an
**ephemeral probe ref actually pushed and deleted** (`refs/adlc/ids/_probe/<nonce>`
— `_probe` is not a real kind; the delete is the ONE sanctioned deletion, BR-13).
NOT `--dry-run` (which never exercises server-side pre-receive policy). Reports
PASS / FAIL-with-layer (transport | auth | server policy) / SKIP-with-reason on a
remote-less repo. Pure stdlib + subprocess (BR-13, LESSON-395).

### `wrapup/SKILL.md`

The bespoke inline ASSUME allocation block is replaced by sourcing
`id-alloc.sh` and calling `adlc_alloc_id assume` in the same fenced block (BR-12).
The per-checkout `.adlc/.next-assume` counter becomes a cache; the "never
re-scan after the counter exists" rule is superseded by `max(remote, local) + 1`.
The fenced usages that already call `adlc_alloc_id lesson` (and `/spec`,
`/bugfix` for req/bug) are textually unchanged (BR-7).

## ADRs

- **ADR-1 — Reservation push executes inside the mkdir lock.** The existing
  design derives the (multi-repo, many-round-trip) high-water OUTSIDE the lock.
  The reservation is ONE push (~1 round-trip); holding the machine-local lock
  across it fully serializes same-machine allocation through the reservation, so
  same-machine allocators never even race on the ref (only cross-machine races
  reach the retry loop). Simpler and strictly correct; accepted because
  allocation is not a hot path (spec Assumptions). The lock's 50×0.1s budget is
  unchanged (a tiny-ref push is typically sub-second).

- **ADR-2 — Distinct object via `commit-tree` of the empty tree.** Resolved Open
  Question: an unborn commit from the empty tree, carrying author identity +
  time + nonce. Cheap, transport-safe, natively distinct per attempt (BR-2). Two
  identical objects pushed to the same new ref both "succeed" (second is a
  no-op) — the same-object hazard the nonce closes; proven by an explicit test.

- **ADR-3 — Reservation refs are durable tombstones.** Never auto-deleted
  (deleting re-opens the collision). The doctor probe ref is the single
  sanctioned deletion because it reserves nothing (BR-8, BR-13).

- **ADR-4 — assume is single-repo-scoped throughout.** Counter, local bootstrap
  scan, remote derivation, and reservation push/scan are all scoped to the
  allocating repo's origin — never sibling repos (BR-12). The global kinds keep
  their machine-global `$ADLC_REPOS_ROOT` scan (BR-11).

## Task graph

```
TASK-001 (core reservation mechanism in id-alloc.sh, + assume kind)
   ├─> TASK-002 (id-recheck.sh reservation probe)
   ├─> TASK-003 (wrapup ASSUME -> adlc_alloc_id assume)
   ├─> TASK-004 (renumber reserves new id)
   └─> TASK-005 (doctor reservations check)
TASK-006 (test matrix: shell AC cases + doctor + renumber tests)  depends on 001–005
```

Sequential execution order (subagent mode): 001 → 002 → 003 → 004 → 005 → 006.
