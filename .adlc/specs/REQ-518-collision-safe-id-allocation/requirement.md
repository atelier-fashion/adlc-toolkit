---
id: REQ-518
title: "Collision-Safe ID Allocation Across Users and Machines"
status: approved
deployable: false
created: 2026-06-11
updated: 2026-06-11
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "markdown"]
concerns: ["concurrency", "multi-user", "portability"]
tags: ["global-counter", "req-id", "collision", "multi-machine", "remote-derived", "lock"]
---

## Description

REQ, BUG, and LESSON ids are allocated from machine-local counter files under
`~/.claude/` (`.global-next-req` and siblings). The mkdir-lock hardening makes
allocation safe across *concurrent sessions on one machine*, and the bootstrap
scan seeds from the *local* filesystem — but neither mechanism can see a
colleague's laptop. At a company with two or more ADLC users, both machines will
allocate the same next id, and the collision surfaces only at PR time: duplicate
`feat/REQ-518` branches, duplicate spec directories merging into the same repo,
and cross-references (lessons, manifests, footprints) that resolve ambiguously.
This breaks the core invariant the global counter exists to protect — "a single
REQ id resolves to one work item."

This REQ makes allocation collision-safe across machines by treating the
**remote as the source of truth**: before an id is finalized, the allocator
derives the high-water mark from what is observable remotely (merged spec/bug/
lesson directories on default branches plus pushed `feat/REQ-*` / PR branch
names across the project's repos — the same derive-don't-store principle as
`/manifest`), takes the max of remote-derived and local-counter values, and
fast-forwards the local counter. The local counter becomes a cache, not an
authority. (informed by LESSON-313)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Allocation | id_kind | enum | req / bug / lesson — one shared mechanism, three counters |
| Allocation | local_high | number | from `~/.claude/.global-next-*` (cache) |
| Allocation | remote_high | number | derived per allocation from remote refs + merged artifact dirs across participating repos |
| Allocation | allocated_id | number | `max(local_high, remote_high) + 1`; written back to local counter under the existing mkdir lock |
| RepoSet | repos | list | the repos scanned for remote high-water; from `$ADLC_REPOS_ROOT` checkouts that have a remote, plus an optional explicit list in the shared ADLC config |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| allocation | `/spec`, `/bugfix`, `/wrapup` (lesson) allocate an id | id_kind, local_high, remote_high, allocated_id, repos consulted, degraded? |
| degraded allocation | remote unreachable (offline, no auth) | warning naming the unreachable remotes; local-only allocation flagged in output |

## Business Rules

- [ ] BR-1: Allocation order is: derive remote high-water → take `max(remote, local)` → allocate `max + 1` → fast-forward the local counter, all inside the existing mkdir lock with its symlink/TOCTOU guards intact. The lock code is extended, not reimplemented, and rationale comments are ported wherever the block is mirrored into `/spec`, `/bugfix`, and lesson allocation. (informed by LESSON-014, LESSON-023)
- [ ] BR-2: Remote high-water derivation must read the remote, not local clones' state: `git ls-remote` for `feat/REQ-*`-pattern branches plus the merged artifact directories reachable from the default branch (via the GitHub API or a shallow ref scan). Stale local checkouts must not lower the result. (informed by LESSON-313)
- [ ] BR-3: Offline/no-auth degradation is loud, not silent: if any configured remote is unreachable, allocation proceeds from local state but the skill output and the spec's Assumptions section must record "id allocated without remote verification — verify before PR." Never block spec-writing on network availability.
- [ ] BR-4: A pre-push/PR-time recheck exists: before `/proceed` creates the `feat/REQ-xxx` branch (and `/manifest` when run), the id is re-verified against the remote; a detected collision halts with a renumber procedure rather than pushing a duplicate. (informed by LESSON-330, LESSON-356 — pre-flight probes beat mid-pipeline discovery)
- [ ] BR-5: The three counters (req/bug/lesson) share one allocation helper (a sourced partial, not copy-pasted blocks in each SKILL.md), parameterized by kind — replacing the three near-identical inline blocks over time. (informed by LESSON-020, LESSON-023)
- [ ] BR-6: All shell is BSD- and zsh-safe and dogfooded under both `zsh -c` and `bash -c`; no `\b` in `grep -E`, no bare `$<digit>`, no `[0]` indexing, no `status=` variable. (informed by LESSON-013, LESSON-329, LESSON-335)
- [ ] BR-7: Single-user single-machine behavior is unchanged in the happy path: same ids would be allocated as today (remote high-water ≤ local on a machine that did all the allocating), and no new mandatory configuration is introduced.
- [ ] BR-8: Numbering remains one global namespace per artifact kind (REQ, BUG, LESSON) across all repos, machines, and users — this REQ strengthens that invariant, never relaxes it. The BR-4 pre-push recheck applies to all three kinds via the shared helper: REQs at branch creation, bugs and lessons at the point their file/directory is about to be committed on a branch for push.
- [ ] BR-9: An automated renumber helper ships with this REQ: `adlc renumber <KIND-old> <KIND-new>` rewrites the artifact's directory/file name, frontmatter `id`, in-repo cross-references to the old id, and (for REQs with an existing branch) prints the exact branch-rename commands. It refuses to run if the new id fails the same remote-collision check, refuses ids not matching the strict id regexes, and shows a dry-run diff before mutating. The BR-4 collision halt message points at this helper. (informed by LESSON-008 — strict id validation; LESSON-006 — fail-loud, atomic mutation)

## Acceptance Criteria

- [ ] Simulated two-machine scenario (two clones, one shared remote, independent `~/.claude` counter fixtures): machine B, whose local counter lags, allocates an id strictly above machine A's pushed `feat/REQ-*` branch number.
- [ ] With the network blackholed, allocation still succeeds, emits the degraded warning, and the spec records the unverified-allocation assumption (BR-3).
- [ ] Pre-branch recheck (BR-4): given a remote that already has `feat/REQ-600`, an attempt to proceed with a locally-allocated REQ-600 halts with the renumber message before any push.
- [ ] The shared allocation partial passes a test matrix: lock contention, symlink-swap refusal, empty counter refusal, remote-ahead, local-ahead, remote-unreachable.
- [ ] Existing single-machine flows (`/spec`, `/bugfix`, lesson allocation in `/wrapup`) produce unchanged ids when the remote has no higher allocation.
- [ ] Linux parity: the partial behaves identically under Ubuntu bash and macOS zsh.
- [ ] Renumber helper: given a colliding REQ-600 with a spec dir, frontmatter, and two in-repo references, `adlc renumber REQ-600 REQ-601` (after dry-run approval) renames the directory, rewrites frontmatter and both references, and a repo-wide grep finds zero remaining `REQ-600` outside git history; running it against a new id that also collides on the remote is refused.
- [ ] The pre-push recheck fires for a bug id and a lesson id about to be pushed when the remote already shows that id, halting with the renumber-helper instruction (BR-8).

## External Dependencies

- `git ls-remote` (already required); GitHub API via `gh` optional — used when available for merged-artifact scanning, degraded to ref-pattern scanning when not.

## Assumptions

- Branch naming `feat/REQ-xxx` and spec-directory naming `REQ-xxx-slug` remain the observable remote footprint of an allocation (consistent with the `/manifest` derivation model).
- Participating repos are discoverable from `$ADLC_REPOS_ROOT` checkouts; a fully remote-only repo a user has never cloned is out of view until first clone (accepted: collisions require both parties to push, and the recheck in BR-4 catches late discovery).

## Open Questions

- [ ] Is a per-user id prefix (e.g. REQ-B515) worth offering as a zero-network alternative mode? Proposed: no — it breaks the single-namespace invariant that motivated the global counter.
- [ ] None remaining beyond the prefix question above. (Resolved decisions, 2026-06-11, per maintainer: pre-push recheck covers all three id kinds; renumber is an automated helper; it lives in the umbrella `adlc` CLI decided in REQ-519 BR-11 — if REQ-518 lands first it ships the minimal CLI skeleton that REQ-519 extends.)

## Out of Scope

- A central allocation service or any infrastructure beyond git remotes already in use.
- Reconciling historical collisions (none known to exist yet).
- The `/manifest` and footprint-publishing work (REQ-482/483/484) — this REQ only consumes the same remote-derivation principle.

## Retrieved Context

- LESSON-013 (lesson, score 9): BSD grep word-boundary silent failure
- LESSON-335 (lesson, score 8): zsh-executor and arg-templating hazards
- LESSON-329 (lesson, score 8): dogfood skills under executor shell
- LESSON-020 (lesson, score 7): cross-block shell state and guard rot
- LESSON-012 (lesson, score 7): structural telemetry beats prose enforcement
- LESSON-008 (lesson, score 7): skill delegation untrusted data and citation sanitization
- LESSON-009 (lesson, score 7): hotfix verify finds what original verify missed
- LESSON-010 (lesson, score 6): delegated-model silent truncation and advisory anchoring
- LESSON-313 (lesson, score 5): global counter scope is its scan root
- LESSON-023 (lesson, score 5): mirror the rationale not just mechanism
- LESSON-014 (lesson, score 5): lock symlink TOCTOU
- LESSON-003 (lesson, score 5): sprint worktree collision
- LESSON-019 (lesson, score 4): presence guards rot when indirection moves
- LESSON-004 (lesson, score 4): drop proceed canary and snapshot phases
- LESSON-330 (lesson, score 3): review catches omitted requirements
