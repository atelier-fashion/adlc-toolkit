---
id: REQ-483
title: "Architecture — ordering enforcement (draft-PR-early, footprint, advisory + trial-merge)"
status: draft
created: 2026-06-04
updated: 2026-06-04
---

## Approach

Three coupled changes, layered on REQ-482's `/manifest`, all markdown-skill + POSIX-shell (no new runtime), no stored coordination state:

1. **draft-PR-early** — `/proceed` opens a *draft* PR at Step 0 and records its number/createdAt in `pipeline-state.json`; Phase 6 flips it ready (`gh pr ready`) instead of `gh pr create`. This publishes intent (and, once `/architect` runs, the footprint) on the remote early enough for other sessions to order against.
2. **Footprint** — `/architect` captures the `architecture-mapper` agent's affected-file table (which already exists, unchanged) and publishes it into the draft-PR body as a fenced `adlc-footprint` block; `/manifest` reads it back via `gh pr view --json body`.
3. **Two-tier enforcement** — footprint overlap is **advisory** and sets a deterministic merge order; the sole **hard** gate is a **non-mutating trial-merge** that blocks `/proceed` (via the `blocked` terminal) / holds a `/sprint` merge only on a real git conflict.

## Components (file map)

| # | File | Change | Notes |
|---|------|--------|-------|
| 1 | `partials/trial-merge.sh` | **create** | shared non-mutating dry-run merge helper (BR-16) |
| 2 | `proceed/SKILL.md` | modify | Step 0: open draft PR + record state; Phase 3→4: precise trial-merge gate |
| 3 | `proceed/phases-6-8-ship.md` | modify | Phase 6: `gh pr create` → `gh pr ready`; Phase 8: pre-merge trial-merge gate |
| 4 | `architect/SKILL.md` | modify | Step 2: capture footprint → publish `adlc-footprint` block to the draft PR body |
| 5 | `manifest/SKILL.md` | modify | parse footprint blocks, compute precise overlap + deterministic ordering verdict |
| 6 | `sprint/SKILL.md` | modify | Step 5 merge sequencing: deterministic order + trial-merge gate (serialize merges) |
| 7 | `agents/pipeline-runner.md` | modify | Phase 8 single-repo merge: trial-merge gate before merge |
| 8 | `.adlc/context/architecture.md` | modify | one-line REQ-483 note (deferred to `/wrapup`) |

`agents/architecture-mapper.md` is **unchanged** — its "Files to Modify / Files to Create" table is already the footprint source.

## The `adlc-footprint` block schema (canonical)

A single fenced block in the PR body, one entry per line, `<repo-id>:<path-or-glob>` (repo-id qualifies for cross-repo; single-repo uses the primary id). Paths are repo-root-relative.

````
```adlc-footprint
adlc-toolkit:proceed/SKILL.md
adlc-toolkit:sprint/SKILL.md
adlc-toolkit:partials/*.sh
```
````

`/architect` writes it (replacing any prior block on re-runs); `/manifest` parses it. Every parsed path is **untrusted** and MUST be charset-validated and `..`-rejected before any shell/glob use (BR-13, reuse `/manifest`'s `clean_field`/validation).

## Data flow

1. `/proceed` Step 0 → push branch, `gh pr create --draft`, record `repos[<id>].prUrl` + `prNumber` + `prCreatedAt`.
2. `/architect` → after architecture-mapper, extract the file column, write the `adlc-footprint` block into the draft PR body (`gh pr edit --body-file`).
3. `/manifest` → for each in-flight PR, `gh pr view <n> --json body,createdAt`; parse footprint; resolve globs vs `git ls-files`; intersect; emit advisory overlap + deterministic merge order (verdict).
4. Enforcement: `/proceed` Phase 3→4 (early) and Phase 8 (pre-merge) run `adlc_trial_merge`; `/sprint` Step 5 serializes merges in verdict order, each gated by `adlc_trial_merge`. A real conflict → `blocked` terminal naming the conflicting REQ + files + unblock condition.

## Key decisions (ADRs)

- **ADR-1 — draft-PR-early.** PR is born draft at Step 0 (state records `prNumber`/`prCreatedAt`), readied at Phase 6. Ship the readied-path before removing the Phase-6 create-path so Phase 6 always has a PR to act on (LESSON-004: replacement before removal). (BR-1/2)
- **ADR-2 — footprint in PR body, not a committed file.** Consistent with REQ-482 derive-don't-store: the footprint lives on the remote (PR body), read on demand. `/architect` is its producer; `/manifest` its consumer. (BR-4/5/6)
- **ADR-3 — two-tier gate.** Footprint = advisory (orders); trial-merge = the only blocker. Eliminates file-level false positives (different sections of one file merge cleanly → no halt). (BR-7/9/10)
- **ADR-4 — trial-merge extracted to a partial.** `partials/trial-merge.sh` exports one function used by `/proceed`, `/sprint`, `pipeline-runner`. A partial is the sanctioned cross-skill share (conventions "Partials"), and keeping the function defined+invoked within each call site's own fence (after sourcing) avoids the `cross-fence-fn` lint failure (LESSON-020). (BR-16)
- **ADR-5 — deterministic, lock-free order.** earliest PR `createdAt` wins; lower REQ breaks ties — a pure function of shared remote data, so sessions converge with no lock (contrast LESSON-014's lock machinery, deliberately not used). (BR-8)
- **ADR-6 — bash single-source, dogfood-verified (not parallel JS helpers).** The overlap/ordering logic lives once in `/manifest` (bash) per BR-6, and trial-merge once in the partial; both consumed by every caller. Considered extracting pure JS helpers into `workflows/` for `node:test` coverage (per REQ-474's harness) but **declined** — it would fork a second implementation that can diverge from the bash single-source. Verification is lint + the dogfood AC scenarios (the toolkit's markdown-skill model), plus a focused dogfood of `trial-merge.sh` (clean + conflict + non-mutating).
- **ADR-7 — untrusted footprint sanitization.** PR-body footprints are attacker-controllable; validate each path (safe charset, reject `..`) before any use, reusing REQ-482's sanitizer (LESSON-008). (BR-13)

## Trial-merge mechanism (`partials/trial-merge.sh`)

`adlc_trial_merge <worktree> <base-ref>`: inside the worktree (isolated since Step 0), `git merge --no-commit --no-ff <base-ref>`; capture status; on conflict collect `git diff --name-only --diff-filter=U`; **always** `git merge --abort` (restore exactly); return 0 (clean) / 1 (conflict, files on stdout). Non-mutating: no commit, clean tree/index after. Portable (sh/zsh; no unquoted word-split — LESSON-329).

## pipeline-state.json additions

`repos[<id>]`: add `prNumber` and `prCreatedAt` (recorded at Step 0). Top-level (optional, advisory): `ordering` (the last computed verdict) and `blockers` (already used by the `blocked` terminal — populate `{blockedBy, conflictFiles, unblockCondition}` on a trial-merge halt).

## Verification

- `python3 tools/lint-skills/check.py` clean (balance, posix-fence, cross-fence-fn — the trial-merge function lives in a partial, sourced+called in-fence).
- **Dogfood**: `trial-merge.sh` run against a synthetic clean merge AND a synthetic conflicting merge, asserting correct result + clean `git status` after (non-mutating). The two AC scenarios (different-sections→no-halt; same-lines→halt) exercised end-to-end. All new shell identical under `sh` and `zsh`.
- No CI in this repo; lint + dogfood is the gate (conventions "Testing changes").

## Lessons applied

LESSON-004 (halt = returned `blocked`, not throw; ship replacement before removal), LESSON-008 (sanitize untrusted PR-body footprints), LESSON-014 (deliberately lock-free), LESSON-020 (cross-fence functions → partial), LESSON-329 (sh/zsh portability; dogfood under the executor shell), REQ-482 (derive-don't-store; reuse `clean_field`), REQ-263/REQ-474 (worktree isolation; deterministic consolidation in code; terminal-state contract).

## Out of scope

Auto-rebase/replay of the blocked REQ after the blocker merges (manual `/proceed` resume); UI beyond manifest + halt messages; `/status` changes; physical edit prevention. (Per requirement.md.)
