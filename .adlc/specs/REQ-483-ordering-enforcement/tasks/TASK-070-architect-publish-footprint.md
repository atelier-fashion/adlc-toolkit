---
id: TASK-070
title: "/architect: capture architecture-mapper footprint + publish adlc-footprint block to the draft PR body (BR-4)"
status: draft
parent: REQ-483
created: 2026-06-04
updated: 2026-06-04
dependencies: [TASK-071]
---

## Description

After `/architect`'s architecture-mapper agent enumerates affected files, capture that file list and publish it into the REQ's draft PR body (opened by TASK-071) as the canonical `adlc-footprint` block, so other sessions can read the precise footprint.

## Files to Create/Modify

- `architect/SKILL.md` — Step 2: add footprint capture + publish

## Acceptance Criteria

- [ ] After the architecture-mapper agent returns, `/architect` extracts the file paths from its "Files to Modify" + "Files to Create" tables into a footprint list.
- [ ] It publishes them into the draft PR body as a single fenced `adlc-footprint` block, one `<repo-id>:<path-or-glob>` per line (schema per architecture.md), via `gh pr edit <prNumber> --body-file <tmp>` (read the PR number from `pipeline-state.json`).
- [ ] Re-running `/architect` replaces any existing `adlc-footprint` block rather than appending a duplicate.
- [ ] If there is no draft PR yet (e.g. `/architect` run standalone, not under `/proceed`), the publish step is skipped with a one-line note — it never errors.
- [ ] `python3 tools/lint-skills/check.py` passes; new shell is sh/zsh-portable (LESSON-329) and balanced.

## Technical Notes

- The architecture-mapper output format is stable (`agents/architecture-mapper.md` "Architecture Impact Map" tables) — parse the first column of the `Files to Modify`/`Files to Create` rows.
- Use `gh pr edit --body-file` with a `mktemp` temp file (not `--body` with a huge inline string); preserve the rest of the PR body (only replace the fenced `adlc-footprint` region).
- Single-repo: qualify paths with the primary repo id. Cross-repo: qualify each with its `repo:`.
- This runs after architecture is designed but before/around task creation, so the footprint is published early.
