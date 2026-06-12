---
id: TASK-005
title: "Reorder CHANGELOG epoch list and remove /map from the distribution with a tombstone"
status: complete
parent: REQ-526
created: 2026-06-12
updated: 2026-06-12
dependencies: []
repo: adlc-toolkit
---

## Description

Two edits to CHANGELOG.md plus the `/map` removal (BR-2, BR-4):

1. **BR-4** — the epoch summary list renders 1, 2, 3, **5, 4** (the `5.x` bullet precedes
   the `4.x` bullet). Reorder so it reads 1→5 in source order. The `[5.0.0]` body section
   below is untouched.
2. **BR-2** — `/map` is a project-specific skill (hardcoded to `atelier-map`/atelier repos)
   in a stack-agnostic distribution. `install.sh` symlinks the whole repo root at
   `~/.claude/skills`, so removing the `map/` directory from the tree is what excludes it
   from distribution — there is no per-skill list to edit. The Open Question default is to
   relocate to the atelier project's own skill dir; since this run is sandboxed inside this
   repo and cannot write to a sibling, preserve `/map`'s content via a CHANGELOG tombstone
   migration note (full body recoverable from git history at the removal commit), then
   remove `map/`.

## Files to Create/Modify

- `CHANGELOG.md` (epoch summary list, ~lines 21–27) — swap the `4.x` and `5.x` bullets so
  the list reads 1, 2, 3, 4, 5 in source order; renumber the bullet labels accordingly
- `CHANGELOG.md` (top, under an `## [Unreleased]` / next section) — add a `/map` removal
  tombstone: it was project-specific (atelier-map vault), removed from the distribution per
  REQ-526; content preserved in git history; relocate to the atelier project's own skill dir
- `map/SKILL.md` + `map/` directory — remove via `git rm`

## Acceptance Criteria

- [ ] CHANGELOG epoch list reads 1, 2, 3, 4, 5 in source order
- [ ] `[5.0.0]`'s body entries are byte-identical to before (only the summary list reordered)
- [ ] `map/` is absent from the repo (`test ! -d map`)
- [ ] `grep -rn 'atelier' README.md install.sh` returns no project-specific *skill* reference (atelier-fashion as an example consumer/PR-owner is fine; a live `/map` skill ref is not)
- [ ] CHANGELOG carries a `/map` tombstone migration note

## Technical Notes

Reorder is a pure swap of two list items + relabeling `5.` → `4.` and `4.` → `5.` so the
visible numerals are sequential. Use `git rm -r map` (not a plain `rm`) so the deletion is
staged. The grep for `atelier` will still legitimately match atelier-fashion mentions in
README install examples and CHANGELOG PR attributions — those are not project-specific
*skills* and are acceptable; the criterion is specifically "no project-specific skill ref".
