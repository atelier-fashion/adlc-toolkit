---
id: TASK-004
title: "Wire spec/bugfix/wrapup SKILL.md to the shared partials (alloc + recheck)"
status: draft
parent: REQ-518
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-001, TASK-002]
---

## Description

Replace the three inline allocation blocks with sourced-partial calls (BR-1,
BR-5) and add the pre-push recheck call site to each skill (BR-4, BR-8). Edits
are STRICTLY scoped to the allocation/recheck blocks — the PR/push call sites
REQ-520 will later touch are left untouched (launch-prompt constraint).

## Files to Create/Modify

- `spec/SKILL.md` — Step 2 REQ allocation block → `adlc_alloc_id req`; add recheck.
- `bugfix/SKILL.md` — BUG allocation block → `adlc_alloc_id bug`; LESSON
  allocation block → `adlc_alloc_id lesson`; add recheck before commit-for-push.
- `wrapup/SKILL.md` — LESSON allocation block → `adlc_alloc_id lesson`; add recheck.

## Acceptance Criteria

- [ ] Each allocation block is replaced by a sourced-partial call placed IN THE
      SAME fenced block as `adlc_alloc_id <kind>` (cross-fence-fn rule; the
      two-level fallback `. .adlc/partials/id-alloc.sh 2>/dev/null || . ~/.claude/skills/partials/id-alloc.sh`).
- [ ] The parent-context empty-guard (`[ -n "$REQ_NUM" ] || { ...; exit 1; }`)
      is preserved at each call site (REQ-416 verify D-pass).
- [ ] A recheck call (`adlc_recheck_id <kind> <id>`) is added before branch
      creation in `/proceed`'s consumer view AND before the bug/lesson file is
      committed for push in `/bugfix` and `/wrapup` (BR-4, BR-8). NOTE: the
      `/proceed` recheck is documented at the consumer-view branch-creation
      point; this REQ wires the three artifact-creating skills.
- [ ] `tools/lint-skills/check.py` passes clean on all three edited SKILL.md
      (no cross-fence-fn finding, no sentinel/balance regressions).
- [ ] `git diff` on each SKILL.md touches ONLY the allocation/recheck regions —
      no edits to the PR/push call sites reserved for REQ-520.
- [ ] Rationale comments are present at each call site (BR-1, LESSON-023 —
      mirror the rationale, pointer to the partial).

## Technical Notes

The lock-block rationale now lives in the partial; each SKILL.md call site keeps
a one-line pointer comment to `partials/id-alloc.sh`. Run
`python3 tools/lint-skills/check.py` after editing. Do not touch
`/bugfix` Phase "push the fix branch" or `/wrapup` PR-creation steps.
