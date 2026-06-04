---
id: REQ-482
title: "Architecture — /manifest skill (remote-derived in-flight visibility)"
status: draft
created: 2026-06-04
updated: 2026-06-04
---

## Approach

A new **standalone, read-only `/manifest` skill** (markdown, like every other skill) that derives a cross-session view of in-flight ADLC work from the **remote** — open GitHub PRs plus pushed `feat/REQ-*` branches — and an **advisory, non-blocking** wiring of that view into the `/proceed` Step 0 and `/sprint` Step 2 pre-flights. No new executable code, no stored state, no Kimi delegation.

**Why remote-derived (the central constraint):** collaborators don't share a filesystem, so `/status` (which reconstructs its view from the *local* `.adlc/` checkout) is structurally blind to another session's unmerged work on another machine. The remote — PRs + pushed branches — is the only cross-session source of truth. `/manifest` is therefore a *separate* skill from `/status`, not an extension of it.

This REQ is **visibility only**. Enforcement (halt/serialize), the draft-PR-early publish point, file-level footprint, and the tie-break rule are a deliberate follow-on REQ (see requirement.md "Out of Scope").

## Components

| # | File | Change | Notes |
|---|------|--------|-------|
| 1 | `manifest/SKILL.md` | **create** | The skill: derive → enrich → overlap → render |
| 2 | `proceed/SKILL.md` | modify | Step 0: advisory in-flight display before work starts (after the existing `git fetch origin`, reusing it) |
| 3 | `sprint/SKILL.md` | modify | Step 2: separate "In-Flight (cross-session)" section after the eligibility table, built once per batch |
| 4 | `README.md` | modify | Skill-catalog entry after `/status` |

No changes to `agents/`, `templates/`, `partials/`, `workflows/`, or `tools/lint-skills/` (confirmed by architecture-mapper + integration-explorer).

## Data flow (manifest derivation)

1. **Sync** — in a pre-flight context, reuse the `git fetch origin` the caller already ran (`/proceed` Step 0 L193; `/sprint` Step 2 LESSON-036). Standalone `/manifest` performs exactly one `git fetch origin` itself.
2. **Enumerate** in-flight REQs from two sources, deduped by REQ id:
   - Open PRs: `gh pr list --state open --json number,headRefName,author,isDraft,createdAt,url --limit 200` (one batched call; includes drafts).
   - Remote branches with no PR: `git branch -r --list 'origin/feat/REQ-*'` (local read against already-fetched refs).
   - Map branch → REQ via the `feat/REQ-<digits>-<slug>` convention; ignore non-matching branches.
3. **Enrich** `component`/`domain` (best-effort, two sources in order): local `.adlc/specs/<REQ>-*/requirement.md` frontmatter → else `git show origin/<branch>:.adlc/specs/<REQ>-*/requirement.md` → else `unknown`. Never drop an entry.
4. **Overlap** — flag pairs sharing `component` OR `domain` (label which); mark the current session's REQ as self.
5. **Render** the table + an advisory overlap block; degrade gracefully (no `gh` → branch-only + note; any failure in a pre-flight → continue, never block).

## Key decisions (ADRs)

- **ADR-1 — Derive from remote, never store.** A committed manifest file would be a single multi-writer artifact and the worst merge-conflict hotspot in the repo. The remote is the cross-session source of truth; the manifest is computed on demand. (Mirrors the "single source of truth" reasoning behind the atomic global counters — REQ-441/473.)
- **ADR-2 — New skill, not a `/status` extension.** `/status` is intentionally local-tree-focused; `/manifest` is remote-aware. Conventions.md cautions against casual new skill dirs, but this responsibility is genuinely orthogonal (different data source, different purpose) and coupling `/status` to `gh`/network would regress it. They stay separate.
- **ADR-3 — No Kimi delegation.** `/manifest` does git/gh I/O, not bulk file-reading, so the delegation gate adds telemetry + lint surface for zero benefit. Omitting any `ADLC_DISABLE_KIMI` reference also keeps the `lint-skills` canonical-helper check untriggered.
- **ADR-4 — Advisory-only, non-blocking.** This is the visibility half; enforcement is deferred. A manifest-build failure inside a pre-flight MUST NOT block, halt, or fail the host pipeline (BR-7). The existing worktree-collision gate is unchanged.
- **ADR-5 — O(1) network.** Reuse the caller's fetch + one batched `gh pr list` + local `git show` enrichment. No per-branch GitHub API calls; `/sprint` builds the manifest once per batch, not once per REQ (BR-14).
- **ADR-6 — Sanitize all remote-derived identifiers before shell use.** Branch names and PR titles are untrusted input. Validate REQ ids against `^REQ-[0-9]{3,6}$`, single-quote substituted values, and reject any path segment equal to `..` before `git show`/`ls` (LESSON-008).

## Lessons applied

- **LESSON-008** — untrusted external-tool output + identifier sanitization (the core security posture; ADR-6).
- **LESSON-013** — BSD-grep word-boundary: use `grep -oE`, no GNU-only flags (macOS).
- **LESSON-019** — presence guards / graceful degradation when an indirection (here, `gh`) is absent.
- **LESSON-020 / conventions "Bash in skills"** — fenced blocks don't share shell state; keep any shell function defined-and-called within the same fence (or it's a `cross-fence-fn` lint failure).
- **LESSON-003** — the `/sprint` pre-flight is the established collision-surfacing hook; this extends it advisorily.

## Verification

- `python3 tools/lint-skills/check.py` must pass — 5 checks: sentinels, shell `$(`/`)` + `$((`/`))` balance per fence, canonical-helper presence (N/A — no Kimi), no `local` in `sh`/`shell` fences, no cross-fence functions.
- **Dogfood**: running `/manifest` in this repo lists `feat/REQ-482-manifest-skill` as in-flight (marked self) and exits 0; with `gh` logged out, it degrades to branch-only and still exits 0; `git status` clean afterward (read-only).
- No CI exists in `.github/workflows/` for this repo (confirmed); verification is lint + dogfood per conventions.md "Testing changes".

## Proposed addition to `.adlc/context/architecture.md`

Add one line to the skill catalog / a short "cross-session visibility" note describing `/manifest` as the remote-derived counterpart to `/status`. Deferred to `/wrapup` to avoid editing a shared context file mid-pipeline.

## Out of scope (follow-on enforcement REQ)

Hard ordering enforcement (halt `/proceed`, serialize `/sprint` tiers), draft-PR-early publish point, file-level footprint + PR-body publishing, deterministic tie-break rule.
