---
id: TASK-006
title: "Migrate PR-lifecycle call sites in skills + sprint workflow to the adapter (BR-1, BR-3)"
status: complete
parent: REQ-520
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-002, TASK-005]
---

## Description

Replace every executable direct `gh pr <op>` call site in the skills and the sprint
workflow with the adapter function, sourcing `partials/forge.sh` with the two-level
fallback in the same fenced block as the call (conventions.md cross-fence rule). GitHub
behavior stays byte-identical (BR-3). Pure-git artifact scans and CI polling are NOT
migrated (BR-8 / out-of-scope).

## Files to Create/Modify

- `proceed/SKILL.md` — Step 0 draft create; Phase-6/7/8 inline summaries.
- `proceed/phases-6-8-ship.md` — pr ready, edit (body/title, preserve footprint block),
  view (footprint body), merge.
- `architect/SKILL.md` — footprint publish: `pr_view` body + `pr_edit` body.
- `manifest/SKILL.md` — open-PR `pr_list` + per-PR `pr_view` body; keep the
  `ls-remote`/`gh api` tree fallback (BR-8) untouched.
- `bugfix/SKILL.md` — create/edit/view/merge.
- `wrapup/SKILL.md` — create/view/merge.
- `sprint/SKILL.md` — merge + `gh pr view` verify call sites.
- `workflows/adlc-sprint.workflow.js` — agent-prompt strings instructing `gh pr …`
  updated to instruct the adapter op (leaf agents execute these).
- `agents/pipeline-runner.md` — Phase-8 merge instruction references the adapter
  (`adlc_forge_pr_merge`) while preserving the parent-repo-path merge caveat.

## Acceptance Criteria

- [ ] Zero direct `gh pr {create,ready,edit,view,list,merge,comment}` remain in migrated
      skills (grep-verified; lint-enforced by TASK-005).
- [ ] Each adapter call sources `partials/forge.sh` with the two-level fallback in the
      SAME fenced block as the call (no cross-fence function use; `cross-fence-fn` lint clean).
- [ ] GitHub path is byte-compatible — the adapter emits the same `gh` command/flags as
      the replaced lines (BR-3); a full GitHub `/proceed` behaves identically.
- [ ] REQ-518's `partials/id-alloc.sh`/`id-recheck.sh` `gh api` tree reads and the
      `/spec`,`/bugfix`,`/wrapup` allocation/recheck blocks are NOT modified (BR-8 +
      inherited-context constraint).
- [ ] `gh pr diff`, `gh pr checks`, and `gh api` tree reads remain direct (out of scope).
- [ ] Footprint-block preservation on `pr_edit` is intact (architect publish + proceed
      Phase-6 body finalize still keep the fenced `adlc-footprint` block).

## Technical Notes

Migrate one skill at a time; after each, grep that file for residual `gh pr` ops and run
the lint check. For the workflow JS, the change is to the prose-in-string agent
instructions, not control flow. Preserve the exact footprint sed/extract logic in
proceed/phases-6-8-ship.md — only the surrounding `gh pr view/edit` becomes the adapter call.
