---
id: REQ-545
title: "Wire the REQ id pre-push recheck into /proceed branch creation (close the REQ-518 BR-4 gap)"
status: complete
deployable: false
created: 2026-07-23
updated: 2026-07-23
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "markdown"]
concerns: ["concurrency", "multi-user", "correctness"]
tags: ["id-allocation", "collision", "recheck", "proceed", "pre-push", "br-4"]
---

## Description

REQ-518 BR-4 mandated a pre-push id recheck at every point an allocated id is
about to become a remote footprint: "before `/proceed` creates the
`feat/REQ-xxx` branch (and `/manifest` when run), the id is re-verified against
the remote; a detected collision halts with a renumber procedure rather than
pushing a duplicate." The recheck partial (`partials/id-recheck.sh`,
`adlc_recheck_id`) shipped and was wired into `/bugfix` (BUG ids) and
`/bugfix`/`/wrapup` (LESSON ids) — but the **REQ-kind call site in `/proceed`
never landed**. REQ-518's TASK-004 scoped its wiring to "the three
artifact-creating skills" and deferred the `/proceed` consumer-view call site,
which then fell through the crack: `proceed/SKILL.md` contains no
`adlc_recheck_id` call today.

Consequence at multi-user installs: the allocation-to-visibility window (a REQ
allocated by `/spec` leaves no remote footprint until `/proceed` pushes the
branch) is unguarded for exactly the id kind teams collide on most. When two
machines allocate the same REQ number, the second `/proceed` run happily
creates and pushes a duplicate `feat/REQ-xxx` branch — the collision surfaces
at PR/merge time, the most expensive point to fix it. This REQ completes
REQ-518's design by adding the missing REQ-kind recheck to `/proceed`,
immediately before the worktree/branch is created.

Prose alone saying "re-verify before branch creation" is exactly the
honor-system enforcement that fails silently — the guard must be an explicit
fenced call in the step sequence, not guidance (informed by LESSON-012).

## System Model

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| req_recheck | `/proceed` Step 4, after origin fetch, before `git worktree add -b feat/REQ-xxx` | req id, result (clear / collision / degraded) |
| collision_halt | recheck returns collision | req id, colliding repo + footprint kind (pushed branch / merged artifact), renumber instruction |

## Business Rules

- [ ] BR-1: `/proceed` sources `partials/id-recheck.sh` (two-level fallback: `.adlc/partials/` then `~/.claude/skills/partials/`) and calls `adlc_recheck_id req "REQ-xxx"` **in the same fenced block**, positioned after the Step 4 origin fetch and before the Step 4b/4c worktree-registration scan and `git worktree add -b`. (informed by LESSON-329 — cross-fence functions are undefined in a new shell)
- [ ] BR-2: A collision result halts the pipeline with the partial's renumber message (`adlc renumber REQ-xxx REQ-yyy`) **before any worktree, branch, or push is created**. This halt is classified alongside the existing worktree-collision gate — a legitimate pre-flight halt, not a new mid-pipeline halt point.
- [ ] BR-3: Resume safety — no false self-collision: when `/proceed` resumes a pipeline whose own `feat/REQ-xxx-<slug>` branch was already created/pushed by a prior run of the SAME pipeline (per `pipeline-state.json` `repos[<id>].branch`), the recheck is skipped (or its hit is recognized as self) rather than halting on the pipeline's own remote footprint. This must also survive the state-file-less crash-recovery case: when the recheck's hit is a pushed branch whose FULL name equals the branch this run would itself create (`feat/REQ-xxx-<identical slug>`), treat it as self — a prior crashed/interrupted session of the same work item — and continue with reuse semantics. A hit with the same id but a **different** slug, or a merged-artifact hit for a different work item, remains a true collision. A run must never tell the user to renumber their own in-flight REQ.
- [ ] BR-4: Degraded parity with REQ-518 BR-3: an unreachable/degraded remote derivation proceeds with the partial's existing loud warning and never blocks the pipeline. The recheck can only fail to FIND a collision, never invent one.
- [ ] BR-5: Subagent-mode parity: the recheck runs identically in solo `/proceed` and in `/sprint` pipeline-runner subagent mode (both reach branch creation through the same Step 4 sequence).
- [ ] BR-6: All added shell is sh/bash/zsh- and BSD-safe: no `\b` in `grep -E`, no bare `$<digit>`, no `[0]` indexing, no `status=` variable, no unquoted word-splitting loops, decimal-normalized arithmetic (informed by LESSON-013, LESSON-329, LESSON-335, LESSON-396). `tools/lint-skills/check.py` passes clean on the edited SKILL.md (no cross-fence-fn finding).
- [ ] BR-7: The call site carries the rationale pointer comments (why the recheck exists, pointer to `partials/id-recheck.sh`, REQ-518 BR-4 provenance) — mirror the rationale, not just the mechanism. (informed by LESSON-023)

## Acceptance Criteria

- [ ] Given a remote that already has a pushed `feat/REQ-545-*` branch from another machine, a fresh `/proceed REQ-545` halts before `git worktree add` with the renumber instruction naming the colliding repo.
- [ ] Given a remote whose default branch already contains a merged `.adlc/specs/REQ-545-*/` directory for a different work item, the same halt fires (merged-artifact probe path).
- [ ] Given a clean remote, `/proceed` behavior is byte-identical to today apart from the recheck call — no new prompts, no reordering.
- [ ] Given an unreachable remote, `/proceed` warns (`degraded — proceeding WITHOUT remote verification`) and continues.
- [ ] Given a resume of a pipeline that already pushed its own `feat/REQ-545-<slug>` branch, no collision halt fires (BR-3).
- [ ] Given a fresh run with NO `pipeline-state.json` against a remote holding `feat/REQ-545-<identical slug>` from a crashed prior session, no renumber halt fires (self via slug match); given the same id with a **different** slug on the remote, the collision halt fires (BR-3).
- [ ] Prefix-sibling safety holds: rechecking REQ-120 does not hit a remote `feat/REQ-1200-*` branch (inherited from `id-recheck.sh`'s exact-equality probe; covered by an explicit test).
- [ ] The recheck block executes correctly under both `zsh -c` and `bash -c` (dogfooded by extracting and running the fence, per LESSON-329).
- [ ] `tools/lint-skills/check.py` passes on `proceed/SKILL.md`.

## External Dependencies

- None new — `git ls-remote` and the existing `partials/id-recheck.sh` / `partials/id-alloc.sh` surfaces.

## Assumptions

- `partials/id-recheck.sh` semantics (exact-id probe + degraded-short-circuit, REQ-523 contract) are correct as shipped; this REQ adds a call site, it does not modify the partial.
- The branch-name slug used at recheck time is the same `feat/REQ-xxx-<slug>` value Step 4b already derives, so no new slug-derivation logic is introduced.
- Consumer projects with a vendored (possibly stale) `.adlc/partials/` copy resolve the partial via the standard two-level fallback; a pre-REQ-518 vendored tree that lacks `id-recheck.sh` falls through to the global copy.

## Open Questions

- [x] ~~Should `/architect` (which publishes the footprint into the draft PR body) also recheck, or is the `/proceed` Step 4 gate sufficient?~~ Resolved (2026-07-23, per maintainer): `/proceed` Step 4 only — it is the single choke point before any remote footprint is created.

## Out of Scope

- Any change to `partials/id-recheck.sh` or `partials/id-alloc.sh` themselves.
- Closing the allocation-to-visibility window itself — that is REQ-546 (atomic remote id reservation); this REQ is the late tripwire, REQ-546 is the fix at the source.
- `/manifest` recheck integration (already advisory-only by design).

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
