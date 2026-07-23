---
id: REQ-546
title: "Atomic remote id reservation at allocation time (close the allocation-to-visibility window)"
status: approved
deployable: false
created: 2026-07-23
updated: 2026-07-23
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "git", "markdown"]
concerns: ["concurrency", "multi-user", "portability"]
tags: ["id-allocation", "collision", "reservation-ref", "remote-derived", "global-counter", "first-push-wins", "assume", "doctor"]
---

## Description

REQ-518 made the remote the source of truth for id allocation, but the remote
can only see footprints that exist: a pushed `feat/REQ-*` branch or a merged
artifact directory on the default branch. A freshly allocated id has neither —
`/spec` creates the spec directory locally and pushes nothing. Until
`/proceed` pushes the branch, the allocation is invisible to every other
machine, so N teammates who allocate inside that window all derive the same
remote high-water and mint the same id. Teams that deliberately batch
requirement-writing before implementation (spec → review → implement) stretch
this window from minutes to days and collide constantly. The REQ-545 recheck
catches the duplicate late, at branch creation; this REQ eliminates the window
at its source.

Mechanism: at allocation time, the allocator **atomically reserves** the
candidate number on the remote by pushing a lightweight reservation ref —
`refs/adlc/ids/<kind>/<NNN>` — before returning the id. Git ref-creation over
push is first-wins when each allocator pushes a **distinct object**: the loser
of a concurrent race gets a rejection, retries with the next number, and the
namespace stays collision-free. The derivation surface (`adlc_remote_high`)
and the recheck (`adlc_recheck_id`) gain the reservation namespace as an
additional source, so a reservation made seconds ago on another laptop raises
every other machine's high-water immediately — no branch push, no merge, no
lag. Works over pure git transport, so GitHub and Azure DevOps behave
identically (same forge-parity posture as REQ-523).

The local counter remains a cache; degradation remains loud-not-blocking
(offline allocation still succeeds with the existing warning). Single-user
single-machine behavior is unchanged except for one extra push per allocation.

Two additions beyond the three global kinds: **ASSUME ids** join the
reservation mechanism as a fourth kind — their counter (`.adlc/.next-assume`)
is a per-*checkout* file, so with multiple humans cloning one repo, concurrent
`/wrapup` runs can double-allocate exactly like the global kinds; reservation
scoped to that repo's origin closes it while keeping the namespace per-project.
And **`adlc doctor`** gains a reservation-pushability check, because a machine
that silently cannot push reservations allocates permanently degraded — the
one remaining duplicate source this REQ leaves open by design.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Reservation | kind | enum | req / bug / lesson (machine-global namespaces) / assume (per-repo namespace) |
| Reservation | number | number | decimal, no leading zeros; unique per kind namespace |
| Reservation | ref | string | `refs/adlc/ids/<kind>/<NNN>` on the allocating repo's `origin` |
| Reservation | payload | git object | unique per allocation attempt (allocator identity + timestamp + nonce) — required for first-wins semantics |
| Allocation | reserved | boolean | true when the reservation push succeeded; false on degraded (offline/no-push-perm) allocation |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| reservation_push | `adlc_alloc_id` after computing candidate `max(remote, local) + 1` | kind, number, ref, outcome (won / lost-retry / degraded) |
| reservation_race_retry | reservation push rejected (ref already exists) | kind, lost number, next candidate |
| degraded_reservation | push failed for non-race reasons (offline, no auth, namespace forbidden) | kind, number, warning emitted |

## Business Rules

- [ ] BR-1: Allocation order becomes: derive remote high-water (branches + merged artifacts + **reservation refs**) → candidate = `max(remote, local) + 1` → **atomically reserve candidate on the remote** → on success fast-forward the local counter and return; on a lost race retry with the next number (bounded retries, then fail loud). The existing mkdir lock, symlink/TOCTOU guards, and fail-loud counter reads are preserved intact. (informed by LESSON-014, LESSON-023)
- [ ] BR-2: First-wins must be real, not assumed: each reservation pushes a **distinct object** (payload embeds allocator identity + timestamp + nonce), because two pushes of an identical object to the same new ref both succeed (the second is an up-to-date no-op) and would silently defeat the race detection. An explicit two-clone race test proves exactly one winner.
- [ ] BR-3: The reservation namespace is a first-class derivation source: `adlc_remote_high` includes `git ls-remote origin 'refs/adlc/ids/<kind>/*'` alongside the branch and artifact scans (independent sources — one failing never skips the others, REQ-523 BR-1 parity), and `adlc_recheck_id`'s exact-id probe checks it. Number extraction is maximal-munch + exact-equality (prefix-sibling safe: reserving 120 never matches 1200).
- [ ] BR-4: Degradation stays loud-not-blocking (REQ-518 BR-3 parity): if the reservation push fails for any non-race reason — offline, no auth, read-only remote, server rejects the ref namespace — allocation proceeds from local state, emits the degraded warning, and the spec's Assumptions section records "id allocated without remote reservation — verify before PR." Never block spec/bug/lesson writing on network availability or push permission.
- [ ] BR-5: A race rejection is NOT degradation: a push rejected because the ref already exists means the number is taken — retry with the next candidate silently (one stderr note), up to a bounded retry count (proposed: 10), then fail loud. Distinguishing rejection-because-exists from transport failure is required behavior, not best-effort.
- [ ] BR-6: Forge parity over pure git transport: reservation push, listing, and probe use plain `git push` / `git ls-remote` only — no `gh`/`az` dependency — so GitHub, Azure DevOps, and any other git host behave identically (REQ-523 BR-5 parity). Reservation refs live outside `refs/heads/` and `refs/tags/` so they never appear as branches or tags in forge UIs.
- [ ] BR-7: All three kinds (req/bug/lesson) share the one parameterized mechanism inside `partials/id-alloc.sh` — no per-kind copies (REQ-518 BR-5 parity). `/spec`, `/bugfix`, and `/wrapup` call sites are unchanged (the reservation happens inside `adlc_alloc_id`).
- [ ] BR-8: Reservation refs are durable tombstones: they are never auto-deleted, since deleting one re-opens the collision it prevented. The ref count grows by one tiny object per allocated id (negligible). `adlc renumber` must reserve the new id via the same mechanism before mutating, and leaves the old id's reservation in place (the old number stays burned).
- [ ] BR-9: Single-machine happy path unchanged (REQ-518 BR-7 parity): with no concurrent allocator, the same ids are allocated as today; the only observable difference is the reservation ref appearing on origin. No new mandatory configuration.
- [ ] BR-10: All shell is sh/bash/zsh- and BSD-safe and dogfooded under `zsh -c` and `bash -c`: no `\b` in `grep -E`, no bare `$<digit>`, no `[0]` indexing, no `status=` variable, no unquoted word-splitting iteration, decimal normalization before arithmetic. (informed by LESSON-013, LESSON-329, LESSON-335, LESSON-396)
- [ ] BR-11: The reservation targets the `origin` of the repo the allocation runs in; for the machine-global kinds (req/bug/lesson) derivation scans the reservation namespace of **every** participating repo under `$ADLC_REPOS_ROOT` (the namespace is machine-global, so the scan root defines it — informed by LESSON-313).
- [ ] BR-12: ASSUME ids join the reservation mechanism as a fourth kind with **per-repo scope**: the reservation ref (`refs/adlc/ids/assume/<NNN>`) is pushed to and derived from ONLY the allocating repo's `origin` — never scanned across sibling repos — preserving the existing per-project namespace while making it collision-safe across clones of that repo. Derivation mirrors the **lesson kind** faithfully, scoped to the one repo: the merged-artifact scan of `.adlc/knowledge/assumptions/` on the origin default branch (via the shared `adlc_remote_artifact_nums` with an assume path mapping) PLUS the reservation namespace — no branch source (assumptions ride wrapup branches with no id in the branch name). Historical ASSUME ids therefore raise the high-water with no backfill, and a stale clone cannot lower the result (REQ-518 BR-2 posture). `/wrapup`'s "never re-scan after the counter exists" rule is **superseded** for assume by the same `max(remote, local) + 1` semantics as the other kinds; the per-checkout `.adlc/.next-assume` counter becomes a cache and keeps its existing mkdir lock and symlink guards. (informed by LESSON-014, LESSON-023, LESSON-313)
- [ ] BR-13: `adlc doctor` gains a `reservations` check: it resolves `origin`, probes whether the reservation ref namespace is readable (`ls-remote` the namespace) and writable via an **ephemeral probe ref that is actually pushed and deleted on success** — the ONE sanctioned ref deletion, since a probe reserves nothing. A `git push --dry-run` is NOT an acceptable substitute: it never exercises server-side pre-receive policy, which is exactly the failure layer this check exists to catch. The check reports PASS/FAIL with the failing layer named (transport, auth, server policy), and SKIPs-with-reason on a remote-less repo. Pure stdlib + subprocess like every doctor check — no dependency on anything it diagnoses. (informed by LESSON-395)

## Acceptance Criteria

- [ ] Two-clone race (one shared remote, independent `~/.claude` counter fixtures): both clones attempt to allocate concurrently; exactly one wins number N, the other transparently allocates N+1; the remote shows two reservation refs. (BR-1, BR-2, BR-5)
- [ ] Same-object hazard test: two pushes of an identical payload object to the same new ref are shown to both "succeed" — and the implementation's distinct-payload rule is verified to prevent that shape. (BR-2)
- [ ] Cross-machine visibility: machine A allocates (reservation pushed, no branch, no merge); machine B's next allocation derives a high-water ≥ A's number from the reservation namespace alone. (BR-3)
- [ ] `adlc_recheck_id` detects a collision that exists only as a reservation ref and halts with the renumber instruction. (BR-3)
- [ ] With the network blackholed, allocation succeeds, emits the degraded warning, and no reservation ref exists. (BR-4)
- [ ] Against a remote that rejects the ref namespace (simulated via a pre-receive hook or a read-only remote), allocation degrades loudly rather than failing. (BR-4)
- [ ] Azure DevOps parity: the same reservation push + ls-remote flow succeeds against an ADO remote over git transport in at least one manual verification, and no `gh`/`az` call appears in the mechanism. (BR-6)
- [ ] Existing single-machine flows produce unchanged ids when no concurrent reservation exists; the partials test matrix (lock contention, symlink refusal, empty counter, remote-ahead, local-ahead, unreachable) still passes, extended with the reservation cases. (BR-9)
- [ ] The partial's fenced usage in `/spec`, `/bugfix`, `/wrapup` is textually unchanged. (BR-7)
- [ ] ASSUME two-clone race: two clones of the SAME repo (independent working trees, shared remote) concurrently allocate an ASSUME id; exactly one wins N, the other gets N+1; a sibling repo's assume namespace is never consulted. (BR-12)
- [ ] ASSUME historical high-water: a repo whose default branch contains merged `ASSUME-040-*` and ZERO reservation refs, allocated from a clone whose stale local counter reads 5, allocates ≥ 041. (BR-12)
- [ ] `adlc doctor` reports the reservations check: PASS against a writable remote, FAIL naming the layer against a push-rejecting remote (simulated read-only or pre-receive hook), SKIP-with-reason on a repo with no `origin`; any probe ref is absent from the remote afterward. (BR-13)
- [ ] All new/modified shell passes under both `zsh -c` and `bash -c`, and `tools/lint-skills/check.py` is clean. (BR-10)

## External Dependencies

- None new — `git push` / `git ls-remote` against remotes already in use. No forge CLI involvement.

## Assumptions

- Git hosts in use (GitHub, Azure DevOps) accept pushes to custom ref namespaces outside `refs/heads/` and `refs/tags/` by default; org-level policies that forbid them are handled by the BR-4 degraded path, not by blocking.
- Allocators have push permission to `origin` at allocation time in the common case; read-only contributors degrade per BR-4 (their ids get verified later by the REQ-545 recheck).
- The allocation-time push adds acceptable latency (~1 network round-trip) to `/spec`/`/bugfix`/`/wrapup`; allocation is not a hot path.
- REQ-545 (the `/proceed` recheck) remains the late tripwire for degraded-mode allocations; this REQ does not make it redundant.

## Open Questions

- [x] ~~Payload object type: a commit vs an annotated tag object vs a raw blob?~~ Resolved (2026-07-23, per maintainer): an unborn commit created with `git commit-tree` from the empty tree — cheap, transport-safe, and carries author identity + timestamp natively (satisfying BR-2's distinct-payload requirement).
- [x] ~~For multi-repo projects, should reservations consolidate into one designated coordination repo?~~ Resolved (2026-07-23, per maintainer): no — allocating repo's origin, scanned across all participating repos (BR-11); a config key can come later if a real multi-repo install needs it.
- [x] ~~Should `adlc doctor` gain a check that probes reservation-namespace pushability?~~ Resolved (2026-07-23, per maintainer): yes, in scope — BR-13.

## Out of Scope

- A central allocation service or any infrastructure beyond git remotes already in use (REQ-518 posture unchanged).
- Garbage-collecting or expiring reservation refs (the BR-13 doctor probe ref is the one sanctioned deletion — it reserves nothing).
- Globalizing the ASSUME namespace across repos — it stays per-project; BR-12 only makes it collision-safe across clones of one repo.
- Backfilling reservation refs for historical ids (the branch + artifact scans already cover them).
- Per-user id prefixes (rejected in REQ-518 — breaks the single-namespace invariant).
- Reconciling existing duplicate ids at consumer sites (`adlc renumber` is the existing remediation).

## Retrieved Context

- LESSON-396 (lesson, score 9): Zero-padded ids are octal to shell arithmetic — decimal-normalize portably before any math
- LESSON-013 (lesson, score 9): BSD grep \b word-boundary in -E silently fails on macOS — use -wF instead
- LESSON-335 (lesson, score 8): Four zsh-executor/templating hazards in SKILL.md scripts
- LESSON-329 (lesson, score 8): Skill bash runs under the operator's shell (zsh) — dogfood by executing it
- LESSON-012 (lesson, score 7): Structural telemetry beats prose enforcement — honor-system instructions get rationalized past
- LESSON-008 (lesson, score 7): Skill delegation untrusted data and citation sanitization
- LESSON-009 (lesson, score 7): Hotfix verify finds what original verify missed
- LESSON-010 (lesson, score 6): Delegated-model silent truncation and advisory anchoring
- LESSON-398 (lesson, score 5): Data-driven registries make concurrent additions mechanical
- LESSON-313 (lesson, score 5): A global counter's namespace is its bootstrap scan root
- LESSON-023 (lesson, score 5): When mirroring a hardened pattern, port the rationale comments — not just the mechanism
- LESSON-014 (lesson, score 5): POSIX mkdir-locks need a symlink pre-check to defend against TOCTOU swap
- LESSON-003 (lesson, score 5): Sprint dispatch must declare each pipeline-runner's worktree path
- LESSON-395 (lesson, score 4): Bootstrap diagnostics must be dependency-free
- LESSON-397 (lesson, score 4): Toolkit commands that mutate project artifacts must resolve the repo root from the caller's cwd
