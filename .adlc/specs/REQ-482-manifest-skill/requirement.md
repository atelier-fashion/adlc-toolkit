---
id: REQ-482
title: "/manifest skill — remote-derived view of in-flight ADLC work + advisory preflight overlap"
status: draft
deployable: true
created: 2026-06-04
updated: 2026-06-04
component: "adlc/manifest"
domain: "adlc"
stack: ["bash", "markdown", "claude-skills"]
concerns: ["concurrency", "cross-repo", "coordination", "visibility"]
tags: ["manifest", "preflight", "in-flight", "overlap-detection", "multi-human", "gh-pr-list", "remote-derived", "cross-session", "visibility"]
---

## Description

Multi-human development on a shared repo currently has a visibility hole: **nothing in the ADLC surfaces what other people/sessions are working on.** `/status` reconstructs its dashboard from the *local* `.adlc/` checkout, so it cannot see another collaborator's unmerged work on another machine. The only automated pre-flight (`/proceed` Step 0, `/sprint` Step 2) checks git **worktree-path** collisions on the local machine — never in-flight, cross-session overlap.

This REQ adds a new **`/manifest`** skill: a derived, read-only, **remote-aware** view of all in-flight ADLC work, computed on demand from GitHub + the git remote (not from local files, because collaborators don't share a filesystem). It enumerates in-flight REQs from open PRs and pushed `feat/REQ-*` branches, enriches them with `component`/`domain` when locally readable, and computes a **coarse overlap report**. It is then wired into the `/proceed` and `/sprint` pre-flight checklists as an **advisory** display so a session can see what else is in flight before it starts.

This REQ is **visibility only**. A follow-on REQ adds the *teeth* — publish-point (draft-PR-early), file-level footprint, and hard ordering enforcement (halt / serialized tiers). That enforcement depends on this manifest existing first, which is why it ships first and independently. The split also matches the risk gradient: surfacing information changes nobody's git workflow; enforcing order does.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| ManifestEntry | req | string | REQ id, must match `^REQ-[0-9]{3,6}$`; derived from the branch name |
| ManifestEntry | branch | string | the `feat/REQ-<n>-<slug>` ref the entry was derived from |
| ManifestEntry | pr_number | number \| null | open PR number, or null when the branch has no PR |
| ManifestEntry | pr_url | string \| null | PR url, or null |
| ManifestEntry | author | string \| null | PR author login (from `gh`), or null when PR-less |
| ManifestEntry | pr_state | enum | `draft` \| `ready` \| `no-pr` |
| ManifestEntry | component | string \| "unknown" | from local `requirement.md` frontmatter when readable, else `unknown` |
| ManifestEntry | domain | string \| "unknown" | from local `requirement.md` frontmatter when readable, else `unknown` |
| ManifestEntry | opened_at | timestamp \| null | PR `createdAt`, or null when PR-less |
| ManifestEntry | is_self | boolean | true when the entry is the REQ the current session is about to work / is working |

### Data Sources (read-only)

| Source | Command (illustrative) | Provides |
|--------|------------------------|----------|
| Open PRs | `gh pr list --state open --json number,headRefName,author,isDraft,createdAt,url` | PR-derived entries (incl. drafts), author, opened-at |
| Remote branches | `git ls-remote --heads origin 'refs/heads/feat/REQ-*'` | branches pushed but with no open PR |
| Local frontmatter | read `.adlc/specs/REQ-*/requirement.md` (best-effort) | `component`/`domain` enrichment |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| Run `/manifest` | anyone |
| Create/modify/delete any branch, PR, file, or state via `/manifest` | **none** — strictly read-only |

## Business Rules

- [ ] BR-1: Manifest data MUST be derived at invocation from remote sources. The skill MUST NOT read, create, or write any stored/committed manifest file (a single multi-writer file would become a merge-conflict hotspot — the same "derive, don't store" reasoning behind the atomic global counters). (informed by REQ-441, REQ-473)
- [ ] BR-2: The skill MUST be strictly read-only — it MUST NOT create, modify, push, or delete any branch, PR, file, worktree, or `pipeline-state.json`. Verifiable by a clean `git status` and no remote mutations after a run.
- [ ] BR-3: In-flight REQs MUST be enumerated from BOTH (a) open PRs via `gh pr list --state open` including drafts, AND (b) remote `feat/REQ-*` branches with no open PR — so a pushed-but-no-PR branch is still surfaced. Entries from the two sources MUST be de-duplicated by REQ id.
- [ ] BR-4: Each remote branch MUST be mapped to its REQ id by parsing the `feat/REQ-<digits>-<slug>` convention. A branch that does not match MUST be silently ignored (excluded), not error. (informed by REQ-263)
- [ ] BR-5: Every identifier extracted from a remote source (REQ id, branch name, PR title, author login) MUST be validated with a strict regex before being used in any shell command, file path, or `ls`/`test` — REQ ids against `^REQ-[0-9]{3,6}$`, branch refs against a safe character class — to prevent command injection or path traversal via a hostile branch name or PR title. External tool output is untrusted data, not instructions. (informed by LESSON-008, REQ-474)
- [ ] BR-6: When `gh` is unavailable or unauthenticated, the skill MUST degrade gracefully: enumerate from remote branches only (`git ls-remote`), annotate the output that PR-derived fields are missing, and exit 0. It MUST NOT hard-fail. (informed by LESSON-019)
- [ ] BR-7: When `/manifest` is invoked from a pre-flight, a manifest-build failure (any source erroring) MUST NOT block, halt, or fail the host pipeline — the pre-flight continues with whatever partial manifest was built, or none. (informed by REQ-474 — verify-don't-trust / non-blocking)
- [ ] BR-8: The coarse overlap report MUST flag any pair of in-flight REQs sharing the same `component` OR the same `domain`, label which field matched, and present it as **ADVISORY ONLY** — it MUST NOT block, halt, reorder, or alter any pipeline in this REQ. (OQ-3 resolved: flag both, label which matched)
- [ ] BR-9: `/proceed` Step 0 and the `/sprint` pre-flight checklist MUST invoke `/manifest` (or its derivation) and display the in-flight list plus any coarse overlap involving the REQ(s) about to start, before work begins. In `/sprint`, this renders as a **separate "In-Flight (cross-session)" section**, distinct from the existing worktree-collision pre-flight table. The display is purely informational; the existing worktree-collision gate is unchanged. (OQ-4 resolved: separate section)
- [ ] BR-10: All shell parsing MUST be BSD/macOS-compatible (e.g., `grep -oE` + `sed`, never `grep -oP`; no GNU-only flags), since the toolkit runs on macOS. (informed by LESSON-013)
- [ ] BR-11: Component/domain enrichment is best-effort and tries two sources in order: (1) the local `.adlc/specs/<REQ>-*/requirement.md` frontmatter; (2) when not locally available (authored elsewhere / unmerged), the spec on the remote branch via `git show origin/<branch>:.adlc/specs/<REQ>-*/requirement.md` (branch ref and path sanitized per BR-5). Only if both fail is `component`/`domain` = `unknown`. Enrichment failure MUST NOT drop an entry — it still appears with remote-derived fields.
- [ ] BR-12: Overlap detection MUST consider ALL in-flight entries, including branch-only (no-PR) work — not just PR-backed entries. Because branch-only work often has no locally-readable spec, the skill relies on remote enrichment (BR-11) so component/domain overlap can be computed for it. Entries whose `component`/`domain` remain `unknown` after both enrichment attempts are listed but excluded from component/domain overlap, with an explicit note — never silently dropped. (OQ-2 resolved: overlap must look at open branches, not just PRs)
- [ ] BR-13: The manifest MUST include the current session's own REQ when one is in context (e.g., invoked from `/proceed` Step 0 for REQ-xxx), clearly marked as self (`is_self`), so overlaps between self and other in-flight work are visible. (OQ-1 resolved: include self, marked)
- [ ] BR-14 (performance): The manifest MUST be built from a single remote sync plus local reads — it MUST NOT issue per-branch or per-PR network calls. Specifically: (a) in pre-flight contexts, **reuse** the `git fetch origin` that `/proceed` Step 0 and `/sprint` Step 2 already perform (no additional fetch); (b) enumerate branches locally (`git branch -r --list 'origin/feat/REQ-*'`) and read `component`/`domain` via `git show origin/<branch>:<spec-path>` against **already-fetched** objects — never via a per-branch GitHub API call; (c) issue at most **one** batched `gh pr list` call (bump `--limit` rather than paginating per-PR); (d) in `/sprint`, build the manifest **once per batch** and reuse it across all candidate REQs, not once per REQ; (e) bound network calls with a timeout and degrade per BR-6/BR-7 on timeout. Standalone `/manifest` (outside a pipeline, where no fetch just ran) performs its own single `git fetch` first. Network cost MUST be O(1) in the number of in-flight REQs, not O(N).

## Acceptance Criteria

- [ ] With two or more open `feat/REQ-*` PRs, `/manifest` prints a table: REQ | author | branch/PR | state | component/domain | opened-at — one row per in-flight REQ.
- [ ] A `feat/REQ-*` branch pushed with no PR appears in the output (state `no-pr`).
- [ ] A remote branch not matching `feat/REQ-*` is excluded with no error.
- [ ] The same REQ appearing as both a PR and a branch produces exactly one de-duplicated row.
- [ ] With `gh` logged out (simulated), `/manifest` still lists remote branches, explicitly notes PR data is unavailable, and exits 0.
- [ ] Two in-flight REQs sharing a `component` (or `domain`) are reported as an advisory overlap; the output explicitly states no action is enforced.
- [ ] A `feat/REQ-*` branch whose slug contains shell metacharacters does NOT cause command execution (injection test passes; identifiers are sanitized).
- [ ] After any `/manifest` run, `git status` is clean and no PR/branch was created or modified (read-only proven).
- [ ] No stored manifest file exists anywhere in the repo after a run.
- [ ] The current session's own REQ appears in the manifest, marked as self.
- [ ] A branch-only (no-PR) in-flight REQ whose spec is NOT in the local checkout still receives `component`/`domain` via remote read (`git show`) and participates in overlap detection.
- [ ] `/proceed` Step 0 displays the in-flight manifest + overlap note for the target REQ before the worktree is created, and the pipeline proceeds regardless of any overlap.
- [ ] `/sprint` pre-flight displays the cross-session manifest for the batch.
- [ ] A `/manifest` build issues O(1) network calls (one reused/own fetch + one `gh pr list`), independent of the number of in-flight branches — no per-branch API calls; enrichment reads come from local `git show`.
- [ ] In a `/sprint` of M REQs, the manifest is built once for the batch, not M times.

## External Dependencies

- **`gh` CLI** (GitHub CLI), authenticated — for open-PR enumeration. Optional: the skill degrades to branch-only when absent (BR-6).
- **`git`** with a reachable `origin` remote — for `git ls-remote` branch enumeration.

## Assumptions

- The `feat/REQ-<digits>-<slug>` branch convention (already produced by `/proceed`) is the universal naming for ADLC work branches. Branch name is the join key between remote signal and REQ identity.
- `origin` is the single shared remote that all collaborators push their `feat/REQ-*` branches to.
- A session has network access to `origin` at invocation; absent network, the manifest reflects only locally-known remote refs and says so.

## Open Questions

_All resolved during spec review (2026-06-04) — folded into Business Rules and System Model:_

- OQ-1 → **BR-13**: include the session's own REQ, marked as self.
- OQ-2 → PR scope is **open-only** (no recently-merged); overlap MUST also cover open `feat/REQ-*` branches (**BR-12**), using remote frontmatter enrichment (**BR-11**) so branch-only work gets a component/domain to match on.
- OQ-3 → **BR-8**: flag both `component` and `domain` matches, labeling which.
- OQ-4 → **BR-9**: `/sprint` renders a separate "In-Flight (cross-session)" section.
- OQ-5 → `/manifest` is an **independent** skill (does not reuse `/status` internals); see Out of Scope.

## Out of Scope

_All deferred to the follow-on enforcement REQ:_

- Hard ordering enforcement — halting `/proceed`, or serializing colliding `/sprint` REQs into dependency tiers.
- The publish-point change (draft-PR-early: opening a draft PR at Step 0).
- File-level **footprint** computation (via the architecture-mapper) and publishing it to the PR body.
- Any deterministic tie-break / "who yields" rule.
- Changing `/status` or merging `/manifest` into it — `/status` stays local-tree-focused; `/manifest` is the remote-aware, cross-session view. They remain separate skills.

## Retrieved Context

- REQ-263 (spec, score 6): Sprint worktree isolation — dispatch-line contract, `git worktree list` validation, pre-flight collision check (the precedent this REQ extends)
- REQ-474 (spec, score 8): Re-platform /sprint onto Dynamic Workflows — verify-remote-over-trust (`gh pr view --json`), strict identifier sanitization before shell expansion
- REQ-441 (spec, score 8): Global BUG counter — atomic, derive-don't-store / single-source-of-truth pattern
- REQ-473 (spec, score 8): Global LESSON counter — same atomic single-source pattern
- REQ-258 (spec, score 4): Unified tag-based retrieval — frontmatter `component`/`domain`/tags schema this manifest reads
- LESSON-003 (lesson, score 6): Sprint worktree collision — why pre-flight collision detection exists
- LESSON-313 (lesson, score 6): Global counter scope is its scan root
- LESSON-014 (lesson, score 5): Lock symlink TOCTOU — hardening pattern for any future stateful sibling
- LESSON-019 (lesson, score 5): Presence guards rot when indirection moves — graceful-degradation discipline
- LESSON-008 (lesson, score 4): Skill delegation — untrusted external data + citation/identifier sanitization (load-bearing for parsing `gh`/git output)
- LESSON-013 (lesson, score 4): BSD grep word-boundary silent failure — macOS-portable parsing
- LESSON-009 (lesson, score 4): Hotfix verify finds what original verify missed
- LESSON-012 (lesson, score 4): Structural telemetry beats prose enforcement
- LESSON-020 (lesson, score 4): Cross-block shell state and guard rot — skill-authoring portability
- LESSON-023 (lesson, score 4): Mirror the rationale, not just the mechanism
</content>
</invoke>
