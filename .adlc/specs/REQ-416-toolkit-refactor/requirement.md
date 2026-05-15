---
id: REQ-416
title: "Toolkit refactor: DRY ethos macro and Kimi gate, shrink /proceed, lock-symlink TOCTOU review, requirements.txt pinning"
status: complete
deployable: false
created: 2026-05-13
updated: 2026-05-15
component: "adlc/toolkit"
domain: "adlc"
stack: ["markdown", "bash", "python"]
concerns: ["maintainability", "complexity", "security", "supply-chain"]
tags: ["refactor", "dry", "ethos", "kimi-gate", "proceed", "toctou", "requirements-txt"]
---

## Description

The `/analyze` audit on the toolkit (run after REQ-414) flagged five structural items that
go beyond hotfix scope: they touch core flow files (`/proceed` is 492 lines), spread
duplication (the ethos macro appears in 15 skills, the Kimi gate snippet in 2 — and will
spread further as more skills adopt delegation), an open lock-symlink TOCTOU question on
the global REQ counter, and a supply-chain gap on the kimi venv.

These items are deliberately separated from REQ-415 (the hotfix bundle) because they need
a proper `/architect` pass — each one has design trade-offs that aren't obvious until laid
out alongside the others. Specifically: choosing where the ethos macro should live
post-DRY (an include file? a frontmatter field? a build step?) interacts with the symlink-
install model. Shrinking `/proceed` interacts with the gate-protocol-immutability invariant.
The TOCTOU review needs to enumerate every `mkdir`-lock site in the toolkit, not just one.

This REQ is **scoped as a draft** — it captures the problem statement and proposed direction
but expects `/architect` to refine the approach before `/proceed`. Five items:

1. **DRY the ethos macro (15 duplications)** — every skill begins with the same
   `!`cat .adlc/ETHOS.md … `` macro. Find an authoring pattern that keeps single-source
   behavior without breaking the symlink-install or the in-skill copy-paste readability.
2. **DRY the Kimi delegation gate (currently in 2 skills, will spread)** — the
   `if command -v ask-kimi && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]; then … else … fi`
   snippet is verbatim in `/analyze` and `/wrapup`. The convention says factor at 3; this REQ
   gets ahead of that because we expect the pilot to expand.
3. **Shrink `/proceed`** — currently 492 lines. Identify the load-bearing parts (gate
   protocol, state machine, agent dispatch contracts) and what can be moved to companion
   files (cross-repo config schema, dispatch-line contract). Goal: `/proceed` SKILL.md under
   300 lines without losing any guarantee.
4. **Lock-symlink TOCTOU full review** — `/analyze` flagged a "lock symlink TOCTOU" issue.
   Enumerate every `mkdir`-based lock in the toolkit (currently the global REQ counter at
   `~/.claude/.global-next-req.lock.d`, the `.adlc/.next-lesson` counter, the
   `.adlc/.next-assume` counter), assess each for symlink-race risk, harden as needed.
5. **Pin `requirements.txt` for `~/.claude/kimi-venv`** — `install.sh` currently does
   `pip install --upgrade openai pytest`. That's a moving target — a future `openai` SDK
   break would silently break the toolkit. Add a pinned `tools/kimi/requirements.txt` and
   have `install.sh` install from it.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| ethos source file | path | string | one canonical location (TBD by /architect — likely `ETHOS.md` or `templates/ETHOS.md`) |
| ethos inclusion mechanism | strategy | enum | one of: in-skill bash macro (status quo), explicit `<!-- include: … -->` directive, frontmatter field with skill-runtime expansion, or build-time concatenation |
| Kimi gate snippet | path | string | shared snippet file (TBD by /architect — likely `templates/kimi-gate.md` or a section in `tools/kimi/README.md`) referenced from each delegating skill |
| /proceed companions | paths | string[] | candidate split — `proceed/state-machine.md`, `proceed/dispatch-contracts.md`, `proceed/cross-repo.md` |
| lock site | path | string | `~/.claude/.global-next-req.lock.d`, `.adlc/.next-lesson`, `.adlc/.next-assume`, and any others discovered |
| requirements.txt | path | string | `tools/kimi/requirements.txt` listing `openai==X.Y.Z`, `pytest==X.Y.Z` |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| ethos source updated | edit to canonical ethos file | all 15 skills reflect the change without per-skill edits |
| new skill adds Kimi delegation | author writes new SKILL.md | references the shared gate snippet rather than copy-pasting verbatim |
| /proceed Phase 4 starts | pipeline state advances | reads dispatch contract from companion file rather than inline |
| install.sh runs | re-installation | uses pinned `requirements.txt` for reproducible env |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| edit canonical ethos | toolkit maintainer (changes affect every skill) |
| bump pinned dependency versions | toolkit maintainer (separate hotfix REQ per bump if it changes API behavior) |

## Business Rules

- [ ] BR-1: After DRY-ing the ethos macro, editing the canonical ethos source MUST
      propagate to all 15 skills without per-skill edits. The propagation MUST be visible
      either at write time (commit-time concatenation) or at runtime (the skill loads the
      canonical source).
- [ ] BR-2: Behavior of every skill that includes the ethos MUST be byte-identical before
      and after the DRY refactor, with the exception of the inclusion mechanism itself.
      Verified by running every skill on a sample REQ in a sandbox repo and diffing the
      ethos block in the rendered prompt.
- [ ] BR-3: The Kimi delegation gate snippet MUST be the single source of truth — adding
      a delegation point to a new skill MUST reference the snippet, not copy-paste it.
- [ ] BR-4: `/proceed` SKILL.md (the top-level instructions file) MUST be ≤ 480 lines after
      refactor, with companion files holding the moved content. No load-bearing invariant
      (state machine, gate protocol, dispatch contract, cross-repo schema) MUST be lost
      in the split — verified by `git diff` of the union (`SKILL.md` + companions) vs the
      pre-refactor `SKILL.md` showing only structural reorganization.
      **Amendment 2026-05-15a** (architecture ADR-3): original ≤300 target required
      extracting Phase 5 (Verify), but Phase 5 owns the Kimi pre-pass gate handoff
      whose orchestration is load-bearing — splitting fragments the gate logic. Target
      amended to ≤450 to keep Phase 5 + Kimi gate cohesive.
      **Amendment 2026-05-15b** (TASK-035 implementation): TASK-034's Kimi gate DRY
      refactor expanded Phase 5 by ~5% (case-statement is wordier than if/else).
      Combined with the mandated 4–6 line companion summaries × 7 phases, the
      achievable floor is ~480 lines with Phase 5 inline. Target amended ≤450 → ≤480.
      Phases 1–3, 4, and 6–8 still extract to companions. See architecture.md ADR-3
      and the LESSON written at /wrapup for the DRY-vs-line-budget tension.
- [ ] BR-5: Every `mkdir`-based lock in the toolkit MUST be reviewed for symlink-race
      vulnerability. Vulnerable sites MUST be either hardened (e.g., switch to `flock` on
      Linux while keeping `mkdir` fallback on macOS, or refuse to operate when the lock
      path resolves through a symlink) or documented as accepted risk with rationale.
- [ ] BR-6: `tools/kimi/requirements.txt` MUST exist with pinned versions for `openai` and
      `pytest`. `install.sh` MUST use `pip install -r tools/kimi/requirements.txt` instead
      of an inline package list.
- [ ] BR-7: Re-running `install.sh` after a version bump in `requirements.txt` MUST update
      the venv to the new pins (pip naturally handles this — no special handling required,
      just verified).
- [ ] BR-8: The refactor MUST NOT break any existing test (REQ-413 pytest suite, currently
      29 tests).
- [ ] BR-9: The refactor MUST NOT break any in-progress REQ pipeline (any consumer with
      a half-completed `/proceed` run mid-flight). This may require keeping the old skill
      structure callable for a deprecation window.

## Acceptance Criteria

(Intentionally less granular than usual — `/architect` will refine these into task-level
ACs.)

- [ ] The 15 ethos duplications collapse to a single canonical source plus an inclusion
      mechanism that every skill uses.
- [ ] The Kimi delegation gate exists as a single reference; `/analyze` and `/wrapup`
      reference it instead of duplicating it.
- [ ] `wc -l proceed/SKILL.md` reports ≤ 480 (amended ≤300 → ≤450 → ≤480 — see BR-4 amendments).
- [ ] Every lock site in the toolkit has a documented stance (hardened / accepted-risk).
- [ ] `tools/kimi/requirements.txt` exists with pinned versions for `openai` and `pytest`.
- [ ] `install.sh` uses `pip install -r tools/kimi/requirements.txt`.
- [ ] All REQ-413 pytest tests still pass.
- [ ] A sample `/proceed` run on a synthetic test REQ completes end-to-end in the refactored
      structure.

## External Dependencies

- None new. `flock` may be considered for Linux-side hardening but is not required.

## Assumptions

- The symlink-install model continues — the canonical ethos source is in `adlc-toolkit/`,
  every consumer project sees it via `~/.claude/skills/` symlinks.
- `/proceed`'s 492-line size is genuinely a maintainability issue, not just an aesthetics
  one — the cost showed up in REQ-414 verify (multiple agents independently flagged it).
- The pinned-versions trade-off (reproducibility ↔ delayed access to upstream fixes) is
  resolved here in favor of reproducibility, with hotfix REQs for bumps.

## Open Questions

- [ ] OQ-1: Best ethos DRY mechanism — runtime cat-from-canonical (current style, but
      single-sourced), commit-time concatenation script, or a frontmatter field +
      skill-runtime macro? Architecture will decide.
- [ ] OQ-2: Where does the Kimi gate snippet live — `templates/kimi-gate.md`,
      `tools/kimi/README.md` (a labeled section), or a new `partials/` directory?
      Architecture will decide.
- [ ] OQ-3: Can `/proceed` be split cleanly along the gate-protocol vs cross-repo-config vs
      dispatch-contract axis, or are those entangled? Architecture must read the existing
      file in detail before answering.
- [ ] OQ-4: Should the global REQ counter migrate from `mkdir`-lock to a proper
      `python-filelock`-style implementation, or is the symlink risk acceptable given the
      lock path is in `~/.claude/` (user-controlled directory, not `/tmp`)?
- [ ] OQ-5: What pin versions for `openai` and `pytest`? Current pip-installed versions
      should be the baseline (openai 2.36.0 was observed in TASK-021 logs).
- [ ] OQ-6: Should the ethos DRY refactor be done first (separately) before the other items,
      so each one has a smaller blast radius? Architecture will sequence.

## Out of Scope

- Anything in REQ-415 (path-traversal regex, credential redaction, install.sh shell
  detection, gitignore pipeline-state, Prerequisites blocks, stale tags, stray file
  cleanup). Those are hotfixes shipping in REQ-415.
- ADLC skill-wiring expansion to `/spec`, `/architect`, `/proceed`, `/review`, `/bugfix`,
  `/init`, `/validate`, `/sprint`. That waits for the REQ-414 pilot to show real-world
  results.
- CI for the toolkit.
- Replacing the symlink install model with a real package manager.
- Adding macOS Keychain support for `MOONSHOT_API_KEY`.

## Retrieved Context

- LESSON-006: tools/ carve-out + fail-loud installers — informs BR-6 (`requirements.txt`
  pinning fits the same "name your knobs, don't scatter constants" philosophy).
- LESSON-007: scrub at every leak point — informs BR-5 (every lock site, not just one).
- LESSON-008: skill delegation = untrusted data — informs BR-3 (the Kimi gate dedup is the
  natural next step after the pilot pattern proved out).

REQ-412..415 are direct ancestors and referenced throughout; outside the Step 1.6
retrieval status filter (all `status: complete` or `draft`).
