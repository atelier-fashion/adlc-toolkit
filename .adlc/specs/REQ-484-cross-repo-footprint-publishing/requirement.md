---
id: REQ-484
title: "Cross-repo footprint publishing — per-repo attribution from tasks, published to each touched repo's draft PR"
status: approved
deployable: true
created: 2026-06-05
updated: 2026-06-05
component: "adlc/architect"
domain: "adlc"
stack: ["bash", "markdown", "claude-skills"]
concerns: ["concurrency", "coordination", "orchestration", "security"]
tags: ["footprint", "cross-repo", "multi-human", "manifest", "overlap-detection", "draft-pr-early", "repo-attribution"]
---

## Description

REQ-483 shipped footprint publishing with a deliberate single-repo limitation. The **read** side (`/manifest`) is already repo-qualified: it parses `<repo-id>:<path>` lines and requires **both** repo and path to match for an overlap (so `web:src/x` and `api:src/x` never false-collide). But the **write** side (`/architect`) has two coupled gaps:

1. It selects the PR with `prnum=$(… | head -1)` (architect/SKILL.md L50) — the **first** repo's PR only — so in cross-repo mode only one repo's PR ever receives a footprint block.
2. It sources the affected-file list from the `architecture-mapper` output (bare paths, no repo column), so it cannot reliably attribute each path to its owning repo.

**Consequence.** A cross-repo REQ (touching sibling repos, with one draft PR per repo per REQ-483 BR-1 / `/proceed` Step 0) publishes a footprint only for its primary repo. Sibling-repo files have no published footprint, so another session colliding on a sibling-repo file falls back to coarse component/domain overlap (REQ-482) for that repo. The trial-merge **hard** gate (REQ-483 BR-16) is per-repo and unaffected — real conflicts are still caught at merge — so this is a degradation of the **advisory early-warning** for cross-repo siblings, not a correctness hole.

This REQ closes the write-side gap. The authoritative per-repo attribution source already exists: in cross-repo mode every task carries a `repo:` frontmatter field **and** a `## Files to Create/Modify` list (task-template L9, L18). So `/architect` derives each repo's footprint from the tasks (grouped by `repo:`) and publishes each repo's subset to **that** repo's draft PR — iterating `repos[*].prNumber`, not `head -1`. Scope is **`/architect` only**: `/proceed` Step 0 already opens a PR per touched repo and records each in `pipeline-state.json` `repos[<id>].prNumber` (proceed/SKILL.md L51, L119–146).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| PerRepoFootprint | req | string | `^REQ-[0-9]{3,6}$` — the REQ |
| PerRepoFootprint | repo | string | a repo-id key under `pipeline-state.json` `repos` |
| PerRepoFootprint | paths | list[string] | files/globs for THIS repo, emitted as repo-qualified `<repo-id>:<path-or-glob>`, one per line |
| PerRepoFootprint | source | enum | `tasks` (authoritative) \| `mapper-fallback` (coarse) |

### Events

| Event | Trigger | Effect |
|-------|---------|--------|
| footprint-published | `/architect` completes | each touched repo's draft PR body receives its own fenced `adlc-footprint` block (one per repo, not one global) |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| Write a footprint block into a PR body | the originating session, into its OWN REQ's per-repo draft PRs |
| Mutate another session's PR/branch | **none** |

## Business Rules

- [ ] BR-1: `/architect` MUST derive each touched repo's footprint from the task files — the union of `## Files to Create/Modify` paths across tasks whose `repo:` equals that repo id — producing a per-repo path set. This replaces the mapper-only bare-path capture as the attribution source. A task with **no** `repo:` field MUST attribute to the **primary** repo (single-repo projects omit `repo:` per the task template), so single-repo REQs derive their footprint from tasks via this same path — NOT via the BR-4 fallback. (informed by REQ-483 BR-4; task-template `repo:` + Files section)
- [ ] BR-2: `/architect` MUST publish each repo's footprint into THAT repo's draft PR. It MUST iterate every touched repo's `prNumber` from `pipeline-state.json` (`repos[*].prNumber`), NOT `head -1`. Each PR receives only its own repo's lines, repo-qualified `<repo-id>:<path-or-glob>`, in a single fenced `adlc-footprint` block (idempotent — replace any prior block). (informed by REQ-483 BR-4/BR-6; architect/SKILL.md L50 `head -1` limitation)
- [ ] BR-3: Single-repo REQs MUST be equivalent in intent to REQ-483 — the per-repo loop degenerates to one repo, one PR, one block, deriving that block from tasks via BR-1 (with `repo:`-absent tasks attributed to the sole repo), NOT through the BR-4 mapper-fallback (a single-repo run is the normal path, never flagged "coarse"). No regression, no separate code path. (informed by REQ-483; proceed/SKILL.md L148 single-repo-mode invariant)
- [ ] BR-4: Graceful degradation, never error: a task with no file list, or a touched repo with no tasks attributing files, falls back to the architecture-mapper paths attributed to the primary repo and emits a one-line `source: mapper-fallback` notice. A repo with genuinely zero attributable files is skipped with a note — never publish an empty block silently. (informed by REQ-483 BR-5; ethos #6 — file the gap explicitly)
- [ ] BR-5: Every published line MUST pass the same sanitization REQ-483's read side applies — charset-validate (`^[A-Za-z0-9_.-]*:?[A-Za-z0-9_./*-]+$`) and reject any line containing `..` — BEFORE being written to any PR body. Untrusted-path discipline applies on write as well as read. (informed by LESSON-008, REQ-483 BR-5)
- [ ] BR-6: A path is attributed to a repo solely by its task's `repo:` tag — never broadcast to all PRs and never inferred from the path string. A filename that legitimately exists in multiple repos appears in a repo's block only because a task tagged for that repo lists it. (informed by REQ-483 read-side repo-qualification)
- [ ] BR-7: The cross-repo round-trip MUST be dogfooded by EXECUTING it (not by reading): publish per-repo footprints to ≥2 repos' PRs, then run `/manifest` and confirm it reads each back and computes per-repo overlap correctly (`web:x` vs `api:x` do NOT collide). REQ-483 dogfooded only single-repo. (informed by LESSON-329 — dogfood under the executor shell; REQ-483 Phase-7 footprint round-trip)

## Acceptance Criteria

- [ ] A cross-repo REQ touching repos A and B publishes an `adlc-footprint` block to A's draft PR containing only A's repo-qualified paths, and to B's draft PR containing only B's.
- [ ] A single-repo REQ produces output identical to REQ-483 behavior (regression check on a single-repo fixture).
- [ ] `/manifest` reads both PRs' footprints back and reports per-repo overlap correctly; a same-path-different-repo pair does NOT register as an overlap.
- [ ] A task missing a file list (or a repo with no attributing tasks) degrades to a logged `mapper-fallback` / skip — no error, no silent empty block.
- [ ] Every emitted footprint line is charset-valid and contains no `..` (sanitization verified on write).
- [ ] Standalone `/architect` (no `/proceed`, no draft PR) still skips publishing with a one-line note (REQ-483 behavior preserved).

## External Dependencies

- None (uses existing `gh`, task files, `pipeline-state.json`).

## Assumptions

- In `/proceed`, task files exist by the time `/architect`'s footprint-publish step runs (the publish reads task `repo:` attribution). If the publish currently runs before task creation, this REQ must move it after (see OQ-1).
- `/proceed` Step 0 / draft-PR-early opens one draft PR per touched repo and records each in `repos[<id>].prNumber` (confirmed: proceed/SKILL.md L51, L119–146).
- Task `repo:` + `## Files to Create/Modify` are populated in cross-repo mode (confirmed: task-template L9, L18).

## Open Questions

- [ ] OQ-1: Does `/architect`'s footprint-publish step (Step 2 item 3) run AFTER task files are created within the same `/architect` invocation? If not, reorder so per-repo attribution is available. (Default: publish after tasks exist.)
- [ ] OQ-2: For BR-4's coarse fallback, "primary repo" = the repo `/proceed` was invoked from (the `primary: true` entry). Confirm that's the right sink for unattributable files. (Default: yes, primary.)
- [ ] OQ-3: A touched repo whose tasks legitimately list zero files (pure-merge / pure-config repo) — skip with a notice vs. publish a coarse component/domain marker. (Default: skip-with-notice.)

## Out of Scope

- Auto-rebase / blocked-REQ auto-resume (REQ-485, the sibling follow-up).
- Republishing the footprint from the ACTUAL diff post-implementation (footprint-from-diff — a separate smaller accuracy improvement noted in REQ-483 wrapup).
- Changing the trial-merge gate (already per-repo correct).
- Cross-repo trial-merge atomicity / 2-phase commit across repos (each repo merges independently per `mergeOrder`).
- Globs that intentionally span repos (each repo's glob is independent once repo-qualified).

## Retrieved Context

_Retrieved in-context this session (REQ-482/REQ-483 initiative); not re-delegated to Kimi — the matched corpus was already fully loaded and is architectural-decision material._

- REQ-483 (spec, score ~11): ordering enforcement — footprint schema, read-side repo-qualification, trial-merge gate (direct parent)
- REQ-482 (spec, score ~8): `/manifest` remote-derived visibility — the footprint reader this REQ feeds
- LESSON-329 (lesson, score ~3): dogfood skills under the executor shell — informs BR-7
- LESSON-330 (lesson, score ~2): Phase-5 review catches omitted requirements — informs BR-coverage discipline
