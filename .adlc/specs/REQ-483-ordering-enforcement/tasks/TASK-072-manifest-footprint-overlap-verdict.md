---
id: TASK-072
title: "/manifest: parse footprints, compute precise overlap + deterministic ordering verdict (BR-6, BR-8, BR-13)"
status: draft
parent: REQ-483
created: 2026-06-04
updated: 2026-06-04
dependencies: []
---

## Description

Extend `/manifest` (REQ-482) to read the `adlc-footprint` block from each in-flight PR body, compute precise file/glob overlap (advisory), and emit the deterministic merge-order verdict that `/proceed` and `/sprint` consume. This is the single source of the ordering logic (BR-6).

## Files to Create/Modify

- `manifest/SKILL.md` — footprint parse + precise overlap + ordering verdict

## Acceptance Criteria

- [ ] For each in-flight PR, reads its body (`gh pr view <n> --json body,createdAt`) and parses the fenced `adlc-footprint` block into a path list.
- [ ] Every parsed path is sanitized BEFORE use: safe charset, any `..` segment rejected (reuse REQ-482's `clean_field`/validation) — PR-body footprints are untrusted (BR-13, LESSON-008).
- [ ] Computes precise overlap by resolving globs against `git ls-files` then set-intersecting concrete paths (advisory; labels the intersecting files).
- [ ] Emits a deterministic **merge order**: earliest PR `createdAt` first, lower REQ number breaks ties (BR-8); identical across repeated runs.
- [ ] Output is consumable by `/proceed` and `/sprint` (a clearly delimited "Merge order" + "Footprint overlap (advisory)" section); footprint overlap is advisory and never itself blocks (BR-7).
- [ ] Degrades safe: a PR with no `adlc-footprint` block falls back to coarse component/domain overlap (REQ-482); `gh` down → branch-only; never hard-fail (BR-15).
- [ ] `python3 tools/lint-skills/check.py` passes; sh/zsh-portable (LESSON-329); O(1)-ish network (reuse fetch + batched `gh`; one `gh pr view` per in-flight PR is acceptable, no per-branch storms beyond that).
- [ ] **Dogfood**: with two synthetic footprint blocks sharing a path, `/manifest` reports the precise overlap + a stable merge order; with disjoint footprints, no overlap.

## Technical Notes

- Build on REQ-482's collection block; add footprint parsing in the enrichment loop and the verdict after the table.
- Glob resolution via `git ls-files` (concrete-set intersection) sidesteps glob-vs-glob algebra; note that not-yet-created files won't resolve (exact paths cover those).
- Keep the verdict a pure function of remote data (no lock) — `createdAt` + REQ number only.
