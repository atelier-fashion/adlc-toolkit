# Changelog

All notable changes to the **adlc-toolkit** are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/). This
project follows a **semver-flavored, epoch-based** scheme:

- **MAJOR** — a product *epoch*: an identity or platform shift that changes what the
  toolkit fundamentally is.
- **MINOR** — a feature drop: new skills, pipeline phases, or capabilities (typically
  one or more landed `REQ-*`).
- **PATCH** — fixes, docs, and bookkeeping (reserved going forward; in this
  back-populated history such commits are folded into the minor they shipped with).

This history was back-populated from git on 2026-06-08. Each version is an annotated
tag pointing at the last commit of its release; pure-bookkeeping commits (ID counters,
"mark complete") are folded into their feature's release. `#N` references are GitHub
PRs (`atelier-fashion/adlc-toolkit`).

**The five epochs:**

1. **1.x — SDLC toolkit** — the original SDLC skill pipeline.
2. **2.x — ADLC** — rebrand SDLC → ADLC; tag-based retrieval and cross-repo support.
3. **3.x — Portable toolkit** — genericized for external use via a config seam + presets.
5. **5.x — Works anywhere** — provider-agnostic delegation, one-command install +
   `adlc doctor`, configurable agent tiers, collision-safe multi-user ids, and the
   GitHub/Azure DevOps forge adapter: the toolkit stops assuming its author's machine.
4. **4.x — Kimi delegation** — Kimi K2.5 token-offload tooling, delegation telemetry,
   and the Dynamic-Workflows / multi-human-coordination era.

---

## [5.0.0] — 2026-06-12

The **portability drop** — six REQs making the toolkit configurable for adopters
beyond the original machine, model, and forge:

- **REQ-515** Provider-agnostic delegation: `adlc-read`/`adlc-write` (Kimi names kept
  as shims), config-file provider resolution with strict precedence, delegation
  **disabled by default** on fresh installs, key-in-config refusal (#80).
- **REQ-517** New **`/adversary` skill** + dedicated `adversary` agent (18th):
  adversarial review of any artifact with mandatory self-refutation (#79).
- **REQ-519** **One-command `install.sh`** + **`adlc` umbrella CLI** with `doctor`
  (12 environment checks, copy-pasteable remediations, pure stdlib) (#82).
- **REQ-516** Configurable **agent model tiers**: `tier:` classes on all 18 agents,
  `adlc agents render` from config, drift detection in lint-skills (#83).
- **REQ-518** **Collision-safe ID allocation** across users/machines: remote-derived
  high-water via shared `id-alloc`/`id-recheck` partials, `adlc renumber` (#84).
- **REQ-520** **Forge adapter**: all PR operations behind `partials/forge.sh` with
  GitHub (`gh`), Azure DevOps (`az repos`), and mock backends — GitHub↔ADO is a
  one-line `forge:` config change or pure auto-detect (#85).
- Knowledge capture: LESSON-390 through LESSON-398 from the sprint's runner reports.

## [4.9.0] — 2026-06-08

- Added an **MIT `LICENSE`** (#64).
- ETHOS principle #7 **"Skeptical by Default"** added (#74).
- **fix(BUG-080):** `ask-kimi` now skips unreadable `--paths` instead of aborting the
  whole batch (#73); resolved with LESSON-334.

## [4.8.0] — 2026-06-05

- **REQ-483 — ordering enforcement:** draft-PR-early, footprint publishing, advisory +
  trial-merge preflight (#70); LESSON-330.
- **REQ-484 — cross-repo footprint publishing:** per-repo attribution derived from tasks (#71).
- **REQ-485 — auto-rebase & resume a blocked REQ** after its blocker merges
  (`/sprint` self-healing serialization) (#72); LESSON-331.

## [4.7.0] — 2026-06-04

- **REQ-482 — `/manifest` skill:** remote-derived in-flight visibility + advisory
  preflight overlap report (#69); LESSON-329.
- **fix(init):** stop vendoring `workflows/tests/` into consumer `.adlc/` (the Jest
  landmine) (#68).

## [4.6.0] — 2026-05-30

- **REQ-474 — re-platform `/sprint` onto Dynamic Workflows** (v1, `--workflow`-gated) (#67).
- Collapsed the workflow engine to one self-contained file (runtime has no `require`).

## [4.5.0] — 2026-05-29

- **REQ-473 — global cross-repo LESSON-ID counter** for `/wrapup` and `/bugfix` (#65);
  LESSON-313.
- Tuned agent model tiers + reasoning effort for Opus 4.8.

## [4.4.0] — 2026-05-18

- **REQ-433 — Kimi telemetry global-fallback resolver** (#50); LESSON-019.
- **REQ-436 — extract the analyze telemetry helper to a sourceable POSIX partial** (#53).
- **REQ-441 — global cross-repo BUG-ID counter** (#59); LESSON-023.
- **Fixes:** BUG-054 (lint-skills leaking absolute paths into CI logs) (#55), BUG-056
  (lazy-import `openai` so pre-API guards run without the SDK) (#57), and `/sprint`
  Phase-0 base-ref hygiene / integration-branch detection (#61). REQ-435 added
  `check.sh`-entrypoint + symlink-escape test coverage (#54).

## [4.3.0] — 2026-05-15

- **REQ-416 — toolkit refactor:** DRY the ethos + kimi blocks, shrink `/proceed`, lock a
  TOCTOU window, pin the kimi venv (#43); LESSON-015.
- **REQ-424 — skill-delegation telemetry:** ghost-skip detection + `/analyze` Step 1.8
  audit (#41); LESSON-012.
- **REQ-425 — `SKILL.md` corruption linter** (lint-skills) (#44); LESSON-016.
- **REQ-426 — REQ-416 follow-ups bundle:** install.sh integrity, reason DRY, partials
  drift + tests (#45); LESSON-017.
- **REQ-423 — content-anchored JSONL discovery** in `/wrapup` Step 4 (#42); LESSON-013.
- **REQ-427 / REQ-428 — analyze cleanups:** replace non-POSIX `shasum`/`xargs -0` (#46)
  and extract a shared `_adlc_emit_step_telemetry` helper (#47).

## [4.2.0] — 2026-05-14

- **REQ-417 — wave-2 Kimi skill delegation:** `/spec`, `/analyze`, `/proceed` Phase 5
  (#39); LESSON-010.
- **REQ-422 — Kimi rc-fallback + LaunchAgent** to break the launchctl
  env-inheritance failure mode (#40); LESSON-011.
- **fix(install):** canonicalize `REPO_ROOT` via `git rev-parse --git-common-dir` so
  wrappers survive worktree invocation (#38).

## [4.1.0] — 2026-05-13

- **REQ-413 — Kimi tools hardening:** offline pytest suite, base64 filter, exfil notice
  (#35); LESSON-007.
- **REQ-414 — pilot Kimi delegation in `/analyze` and `/wrapup`** with hard fallback
  (#36); LESSON-008.
- **REQ-415 — hotfix bundle:** path-traversal regex, broader redaction, install.sh shell
  detection + launchctl (#37); LESSON-009.

## [4.0.0] — 2026-05-12 · _Epoch: Kimi delegation_

- **REQ-412 — Kimi K2.5 delegation tooling** — the `ask-kimi` / `kimi-write` token-offload
  CLIs (#34); LESSON-006.

## [3.1.0] — 2026-05-04

- **REQ-380 — drop Phase 7.5 (canary) and Phase 8a (snapshot promotion)** from
  `/proceed` (#28).
- **REQ-381 — drop `/bugfix` Phase 6 canary**, fix the dangling Phase 7.5 reference (#31).
- ETHOS principle #6 **"If It's Broken, Fix It"** (#27).

## [3.0.0] — 2026-04-28 · _Epoch: Portable toolkit_

- **Genericize the toolkit for external use** via a config seam + presets (#24); scrubbed
  remaining project-specific examples (#25).
- Added `/proceed` Phase 8a (Create Promotion Snapshot), gated on
  `pipeline.snapshot_promotion` (#26). _(Later removed in 3.1.0.)_

## [2.3.0] — 2026-04-28

- **`/bugfix` ship phases** — PR + canary + merge + deploy + knowledge capture (#23).

## [2.2.0] — 2026-04-25

- **Cross-repo REQ support** across `/proceed`, `/architect`, `/wrapup`, `/canary`,
  `/validate`, `/init` (#18) and cross-repo awareness for `/status`, `/sprint`,
  `/bugfix` (#19).
- **REQ-263 — per-REQ unique worktree paths** for sprint orchestration (#22); a
  terminal-state contract for sprint (#21); repo-hygiene checks in `/analyze` (#20).
- Per-phase gating mitigation in `/proceed` (#15); LESSON-001. Fixes: cwd-agnostic
  wrapup cleanup (#17), atomic ASSUME/LESSON IDs, test-auditor dual-layout scan.

## [2.1.0] — 2026-04-20

- **REQ-258 — unified tag-based retriever** for `/spec` (#12).
- **REQ-262 — backfill tag frontmatter** across 4 consumer repos (#13).
- Genericized the review skill, consolidated the reflect checklist, removed the orphaned
  llm-review-prompt template, and made skills portable with local ETHOS/templates for the
  worktree sandbox (#8–#11).

## [2.0.0] — 2026-04-14 · _Epoch: ADLC_

- **REQ-249 — rebrand SDLC → ADLC** across all skills, agents, README, and ETHOS (#7).

## [1.3.0] — 2026-04-14

- **Added test-auditor and security-auditor** to the parallel review set (#4).
- Closed gate gaps, fixed wrapup ordering, and added the **template-drift** skill (#6);
  documented the symlink-based live-install setup (#5).

## [1.2.0] — 2026-04-11

- **Formal agent definitions** with model tiering and tool restrictions (#3).
- Optimized the SDLC pipeline — merged review phases, context filtering, component
  lessons (#1) — plus a follow-on perf pass on `/proceed` (#2).
- Began tracking **ETHOS.md** in-repo and pointed all skills at the tracked path.

## [1.1.0] — 2026-03-27

- **`/proceed` pipeline** — feature-branch-first, PR review/fix + wrapup phases, and
  pipeline-state tracking to prevent phase-skipping.
- **Parallel-session safety** — worktrees + an atomic REQ counter.
- Surfaced lessons-learned across the SDLC lifecycle.

## [1.0.0] — 2026-03-18 · _Epoch: SDLC toolkit_

- **Initial toolkit** — the original suite of SDLC skills + templates.
- `/reflect` gained a questions-for-user step before fix/defer.
