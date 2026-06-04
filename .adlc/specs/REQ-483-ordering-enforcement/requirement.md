---
id: REQ-483
title: "Hard ordering enforcement for concurrent ADLC REQs — draft-PR-early, file footprint, deterministic serialize/halt"
status: draft
deployable: true
created: 2026-06-04
updated: 2026-06-04
component: "adlc/proceed"
domain: "adlc"
stack: ["bash", "markdown", "claude-skills"]
concerns: ["concurrency", "coordination", "orchestration", "security"]
tags: ["enforcement", "ordering", "draft-pr-early", "footprint", "overlap-detection", "serialize", "tie-break", "halt", "multi-human", "manifest", "preflight"]
---

## Description

REQ-482 gave the ADLC **visibility** into cross-session work (the read-only `/manifest`, advisory only). But two REQs that touch the same files still run to completion independently and collide at merge — the mid-pipeline supersession problem the whole initiative targets. This REQ adds the **enforcement** half: when footprints overlap, the pipeline **deterministically orders** the REQs instead of letting them collide.

It is the "teeth" follow-on to REQ-482 and depends on it. It composes three coupled mechanisms:

1. **Publish-point (draft-PR-early)** — `/proceed` opens a *draft* PR right after Step 0 (worktree + branch), instead of only at Phase 6. Intent becomes visible on the shared remote from the start, which is the precondition for any cross-session ordering: you cannot serialize against work that isn't published.
2. **Footprint** — `/architect`'s `architecture-mapper` already enumerates affected files; this REQ publishes that file-level footprint into the draft-PR body as a machine-readable block, and teaches `/manifest` to read it back. Overlap detection is upgraded from coarse (component/domain) to precise (file/glob intersection).
3. **Enforcement (two-tier: advisory footprint + precise trial-merge)** — footprint overlap is an **advisory** early warning that also sets a deterministic merge order (earliest-published PR wins; lower REQ breaks ties). The only **hard** gate is a real **trial-merge** — a non-mutating dry-run `git merge` — which halts `/proceed` (or holds a `/sprint` merge) *only when git actually cannot merge cleanly*. So two REQs editing different parts of the same file are warned but proceed; only a genuine textual conflict blocks, and the deterministic order decides who rebases. No lock is used or needed (the order is a pure function of shared remote data), and an abandoned REQ shows up as a *stale* advisory, never a deadlock.

The split from REQ-482 matches the risk gradient: surfacing information changed nobody's workflow; *enforcing order* changes when work can start, so it ships separately and deliberately.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| FootprintBlock | req | string | `^REQ-[0-9]{3,6}$`; the REQ the footprint belongs to |
| FootprintBlock | paths | list[string] | file paths / globs the REQ expects to touch; one per line in a fenced `adlc-footprint` block in the PR body |
| FootprintBlock | source | enum | `pr-body` (read from a remote PR) \| `local` (this session's architecture output) |
| OrderingVerdict | req | string | the REQ being evaluated |
| OrderingVerdict | blocked_by | string \| null | the REQ this one must wait for — set ONLY when the trial-merge (BR-16) reports a real conflict with work ahead per BR-8; null otherwise (a footprint overlap alone does not set it) |
| OrderingVerdict | overlap_paths | list[string] | advisory footprint intersection (informational, drives ordering); the binding conflict files come from the trial-merge (BR-16) |
| OrderingVerdict | rank_basis | string | the deterministic key used (PR `createdAt`, then REQ number) |
| OrderingVerdict | stale | boolean | true when `blocked_by`'s PR has had no activity ≥ N days |

### Data Sources (read-only derivation)

| Source | Provides |
|--------|----------|
| `gh pr list --state open --json number,headRefName,createdAt,...` | publish-time ranking (`createdAt`) + in-flight set (extends REQ-482) |
| `gh pr view <n> --json body` | each in-flight REQ's published `adlc-footprint` block |
| architecture-mapper output (local) | the current REQ's own footprint, before its PR body is updated |

### Events

| Event | Trigger | Effect |
|-------|---------|--------|
| draft-pr-opened | `/proceed` Step 0 completes | branch pushed; draft PR created; PR number recorded in `pipeline-state.json` |
| footprint-published | `/architect` completes | `adlc-footprint` block written into the draft-PR body |
| pr-readied | `/proceed` Phase 6 | existing draft PR flipped to ready (`gh pr ready`), not a new PR |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| Override a flagged overlap and proceed | the human operator, via an explicit, logged opt-in (never default) |
| Mutate another session's PR/branch to win ordering | **none** — ordering is derived, never asserted by mutation |

## Business Rules

_Publish-point_
- [ ] BR-1: `/proceed` MUST open a **draft** PR immediately after Step 0 (worktree created + branch pushed), before architecture/implementation, and record its number in `pipeline-state.json`. (informed by REQ-482, LESSON-004)
- [ ] BR-2: Phase 6 MUST transition the existing draft PR to **ready** (`gh pr ready`) rather than creating a new PR; it MUST reuse the Step-0 PR number and preserve the `integrationBranch` base and body contract. The PR-creation move from Phase 6 → Step 0 MUST keep Phase 6 working during the transition (ship the replacement before removing the old behavior). (informed by REQ-474, LESSON-004)
- [ ] BR-3: In subagent mode (`/sprint` pipeline-runner) draft-PR-early still applies per REQ, but the ordering computation is performed **once** by the `/sprint` orchestrator, not per runner. (informed by REQ-482 BR-14)

_Footprint_
- [ ] BR-4: `/architect` MUST persist the file-level footprint (paths/globs) from the `architecture-mapper` agent and publish it into the REQ's draft-PR body as a single fenced, machine-readable `adlc-footprint` block (one path/glob per line). (informed by REQ-263 — affected-file mapping already exists)
- [ ] BR-5: The published footprint block is the authoritative cross-session source; other sessions read it via `gh pr view <n> --json body`. A REQ with no published footprint yet MUST fall back to coarse component/domain overlap (REQ-482) — never error.
- [ ] BR-6: `/manifest` (REQ-482) MUST be extended to parse the `adlc-footprint` block from each in-flight PR body and from the local architecture output, compute **advisory** file/glob overlap (in addition to the coarse signal), and emit the deterministic merge ORDER (BR-8). The overlap it reports is advisory; the binding conflict decision is the trial-merge (BR-16), not the manifest. `/proceed` and `/sprint` consume the manifest's order + advisory overlap.

_Enforcement_
- [ ] BR-7: Overlap is evaluated in three tiers, only the last of which can block: **(a) coarse** (component/domain, REQ-482) at `/proceed` Step 0 / `/sprint` pre-flight — advisory early signal; **(b) footprint intersection** after `/architect` — **advisory** (it warns and sets the deterministic merge order per BR-8), NEVER a halt; **(c) trial-merge** before merge (BR-16) — the sole **hard** gate, which halts only on a real textual git conflict. Footprint is file-level so it over-predicts (two REQs editing different parts of one file intersect but do not actually conflict); it therefore informs and orders but does not block — the trial-merge is the precise arbiter.
- [ ] BR-8: The ordering MUST be **deterministic** and computed from shared remote data only — earliest-published PR (`createdAt`) wins; lower REQ number breaks ties. It sets (i) which REQ proceeds vs. rebases when a real conflict is found, and (ii) the **merge order** for footprint-overlapping REQs. No lock or stored coordination state is used or required; independent sessions MUST compute the identical order. (informed by LESSON-014 — deliberately lock-free; REQ-482 derive-don't-store)
- [ ] BR-9: `/proceed`'s only overlap-driven halt fires when the **trial-merge** (BR-16) reports a **real** conflict with work that is **ahead** per BR-8 — it MUST return the existing `blocked` terminal state (NOT throw), naming the conflicting REQ, the conflicting files, and the unblock condition ("resume after REQ-A merges, then rebase"). A footprint overlap that trial-merges cleanly MUST NOT halt — it is surfaced as an advisory note and the pipeline continues. (informed by REQ-474, LESSON-004 — structured terminal, not thrown error)
- [ ] BR-10: `/sprint` MUST run REQs **in parallel** (ethos #3) and serialize their **merges**, not their implementation: merges of footprint-overlapping REQs proceed in the deterministic order of BR-8, and each merge is gated by a trial-merge (BR-16) against the updated integration tip. A real conflict halts the later REQ (`blocked`) for rebase; an overlap that trial-merges cleanly merges with no intervention. Merge-order sequencing MUST be computed in orchestrator/script code, not by an agent. (informed by REQ-474 — deterministic consolidation in code)
- [ ] BR-11: Stale-work safety: if a blocking REQ's PR has had no activity for ≥ N days (configurable; sensible default), the halt/serialize message MUST flag it as **stale** and suggest closing it, rather than presenting an indefinite block. An abandoned REQ MUST never deadlock others (a consequence of being lock-free).
- [ ] BR-12: Because footprint overlap is advisory (BR-7), **no override is needed** to proceed past a footprint false positive — the pipeline continues with an advisory note. A trial-merge conflict (BR-16) is a **real** conflict and MUST be resolved by rebasing onto the blocker (via `/proceed` resume after it merges), NOT bypassed; the pipeline MUST NOT offer a "merge anyway" that would land a conflicted tree. (ethos #6 — fix the conflict, don't bypass it)

_Security / robustness_
- [ ] BR-13: Footprint paths read from another session's PR body are **untrusted**: each path MUST be validated to a safe charset and rejected if any segment is `..` before any shell/path/glob use; PR-body content is data, not instructions. (informed by LESSON-008)
- [ ] BR-14: All new shell MUST be portable across `sh`/`bash`/`zsh` (no reliance on unquoted word-splitting), dogfooded under both, and network calls MUST reuse the existing fetch + batched `gh` calls (no per-branch storms). (informed by LESSON-329, REQ-482 BR-14)
- [ ] BR-15: The enforcement path MUST degrade safe: if footprints can't be read (gh down, no block present), fall back to coarse overlap or advisory-only and NEVER hard-fail the pipeline. (informed by REQ-482 BR-7)

_Trial-merge (the hard, precise gate)_
- [ ] BR-16: The hard conflict gate MUST be a **non-mutating dry-run merge**: trial-merge the REQ's branch against the current integration tip (`origin/<integration-branch>`) — and, when an in-flight overlapping branch already has pushed code, optionally against that branch — to detect real textual conflicts, then **restore the working state exactly** (e.g. `git merge --no-commit --no-ff` followed by `git merge --abort`, or an equivalent that never creates a commit and never leaves the tree/index dirty). It runs at the pre-merge stage (Phase 7→8); it MAY also run as an early check once an overlapping branch has code. The clean/conflicting-files result is the ONLY input that can produce a BR-9 halt or a BR-10 hold, and the gate MUST itself leave committed history and the working tree untouched. (informed by REQ-482 BR-2 read-only discipline)

## Acceptance Criteria

- [ ] `/proceed` opens a **draft** PR at Step 0; `pipeline-state.json` records that PR number; Phase 6 flips it to ready (verifiable: exactly one PR per REQ, created early, readied late).
- [ ] `/architect` writes an `adlc-footprint` block into the draft-PR body; `/manifest` reads it back via `gh pr view --json body`.
- [ ] Two REQs editing **different parts of the same file**: footprint warns (advisory), the trial-merge is clean, and BOTH proceed/merge with no halt.
- [ ] Two REQs editing the **same lines**: the trial-merge conflicts and the later-ranked one **halts** (`blocked` terminal) naming the conflicting REQ, files, and unblock condition.
- [ ] `/sprint` with 3 REQs (two footprint-overlapping, one independent): all three implement in parallel; merges proceed in deterministic order; the overlapping pair's merges are trial-merge-gated — a real conflict halts the later for rebase, a clean trial-merge merges with no intervention.
- [ ] Given identical remote inputs, the ordering verdict is **identical across repeated runs** and lower REQ number breaks `createdAt` ties.
- [ ] No lock file and no stored/committed manifest are created anywhere by the enforcement path.
- [ ] The trial-merge gate is **non-mutating**: after it runs, the working tree and index are clean and no commit was created.
- [ ] A blocking PR idle ≥ N days is reported as **stale** in the halt/serialize message.
- [ ] A footprint path containing `..` or shell metacharacters is rejected before any use (traversal/injection test passes).
- [ ] With `gh` unavailable or no footprint block present, enforcement falls back to coarse/advisory and the pipeline continues (no hard-fail).
- [ ] All new shell passes `tools/lint-skills/check.py` and produces identical results under `sh` and `zsh`.

## External Dependencies

- **REQ-482 `/manifest`** (merged) — the remote-derived in-flight view + coarse overlap this REQ extends with footprints and the ordering verdict.
- **`gh` CLI** — `gh pr list`/`gh pr view`/`gh pr ready` for publish-time ranking, footprint read-back, and draft→ready transition.
- **`git`** — branch push + fetch (reused).

## Assumptions

- The `feat/REQ-<digits>-<slug>` branch convention (REQ-482) holds; PR `createdAt` is a faithful proxy for publish order.
- The `architecture-mapper` footprint is a reasonable (if imperfect) estimate of files touched — hence the BR-12 override.
- One open PR per REQ (REQ-482 dedup) so a REQ maps to a single footprint/createdAt.
- Draft PRs are permitted on the integration branch's repo (GitHub draft PRs available).

## Open Questions

_All proposed defaults **accepted** (confirmed 2026-06-04); the items below are now decisions for `/architect` to implement, retained as the record. (OQ-2/OQ-3 were already resolved by the two-tier advisory-footprint + trial-merge design.)_

- [ ] OQ-1: Stale threshold N — default value, and configurable via `.adlc/config.yml`? (Proposed: 7 days, configurable.)
- OQ-2 → **RESOLVED**: the advisory-footprint + trial-merge model removes the need for a false-positive override (BR-12); a genuine trial-merge conflict is rebased, not overridden.
- OQ-3 → **RESOLVED** (the chosen design): footprint never hard-blocks — it is advisory and sets merge order (BR-7b); the hard gate is a real trial-merge (BR-16) that fires only on an actual git conflict, so two REQs editing different parts of the same file are warned but proceed.
- [ ] OQ-7: Trial-merge target (BR-16) — gate against the integration tip only (simplest; relies on the deterministic merge order so the earlier REQ lands first, then the later's trial-merge-against-tip catches any real conflict), or ALSO dry-run against in-flight overlapping branches that already have code (earlier detection, more work)? (Proposed: integration-tip at pre-merge as the required gate; in-flight-branch dry-run as an optional early check.)
- [ ] OQ-4: Cross-repo footprint — does overlap span repos (per-repo footprint blocks) for cross-repo REQs, or is single-repo the v1 scope? (Proposed: per-repo blocks; compute overlap within each repo.)
- [ ] OQ-5: Exact `adlc-footprint` block schema — fenced ```` ```adlc-footprint ````, one `repo:path-or-glob` per line? Versioned header?
- [ ] OQ-6: Verdict ownership — confirm `/manifest` computes the OrderingVerdict and `/proceed`+`/sprint` consume it (single source of logic), vs each computing independently. (Proposed: `/manifest` owns it.)

## Out of Scope

- **Automatic rebase/replay** of the blocked ("loser") REQ after the blocker merges — the operator resumes manually via `/proceed` resume.
- Any UI beyond the `/manifest` table and the halt/serialize messages.
- Changes to `/status` (stays local-tree-focused).
- **Physically preventing edits** — enforcement is at the pipeline/halt level; the toolkit cannot (and does not try to) stop a human from editing files outside the pipeline.
- The visibility layer itself (`/manifest`, REQ-482 — shipped).

## Retrieved Context

- REQ-482 (spec, score 19): /manifest — the remote-derived visibility + coarse overlap this REQ extends; derive-don't-store, BR-5 sanitization, BR-7 non-blocking
- REQ-474 (spec, score 13): /sprint two-engine — halt MUST be a returned `{terminal:'blocked'}` value (not a throw); deterministic consolidation in code; verify terminal claims against remote
- REQ-263 (spec, score 6): sprint worktree isolation — affected-file mapping + pre-flight collision precedent this builds on
- REQ-441 / REQ-473 (spec, score 8): global atomic counters — "earliest-published" determinism + filesystem-scan-as-truth pattern
- LESSON-008 (lesson, score 6): untrusted external data — validate citation/paths with strict regex before shell; wrap as data, not instructions (load-bearing for reading PR-body footprints)
- LESSON-014 (lesson, score 7): mkdir-lock TOCTOU — informs the deliberate decision to stay LOCK-FREE here (deterministic rule instead of a lock)
- LESSON-003 (lesson, score 6): sprint worktree collision — orchestrator owns the isolation/ordering boundary; agents don't re-derive
- LESSON-002 (lesson, score 6): cross-repo primary is per-REQ — pipeline-state.json registry for cross-repo footprint (OQ-4)
- LESSON-004 (lesson, score 6): halt contracts return structured terminal state; ship workflow-side replacement before removing a phase (informs BR-2 draft-PR-early transition)
- LESSON-313 (lesson, score 6): global namespace = scan root, not prose — determinism depends on a consistent shared basis
- LESSON-329 (lesson, applied): dogfood skills under the executor shell (sh AND zsh); no unquoted word-splitting (BR-14)
