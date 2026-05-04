---
id: TASK-010
title: "Remove /bugfix Phase 6 (Canary), renumber Phase 7 → Phase 6, fix all cross-references"
status: complete
parent: REQ-381
created: 2026-05-04
updated: 2026-05-04
dependencies: []
---

## Description

Edit `bugfix/SKILL.md` to delete the Phase 6 (Canary Deploy — Optional) section in its entirety, renumber the current Phase 7 (Wrapup — Merge, Deploy, Knowledge Capture) to Phase 6, and update every inline cross-reference and the skill's frontmatter `description` field so the file is internally consistent. This closes REQ-381 BR-1, BR-2, BR-3, BR-4 and the bulk of the ACs.

## Files to Create/Modify

- `bugfix/SKILL.md` — multi-edit:
  - **Frontmatter `description`**: replace `End-to-end bug fix workflow — report, analyze, fix, verify, ship (PR + canary + merge + deploy + knowledge capture)` with `End-to-end bug fix workflow — report, analyze, fix, verify, ship (PR + merge + deploy + knowledge capture)`. The `+ canary` segment goes away.
  - **Phase 4 verify step**: the line that reads `do NOT mark resolved yet — that happens in Phase 7 after the fix is merged and deployed` becomes `do NOT mark resolved yet — that happens in Phase 6 after the fix is merged and deployed`.
  - **Phase 6 section** (lines ~119–135 starting at `### Phase 6: Canary Deploy (Optional)`): delete the entire section — the heading, the "Skip when" / "Run when" prose, and all numbered steps including the dangling `Steps (mirrors /proceed Phase 7.5):` line.
  - **Phase 7 section heading** (line ~137 `### Phase 7: Wrapup — Merge, Deploy, Knowledge Capture`): renumber to `### Phase 6: Wrapup — Merge, Deploy, Knowledge Capture`. The body of the section is unchanged except for any inline phase-number references inside it (audit during implementation).
  - **Phase 4 → Phase 5 transition line** (`Then continue to Phase 5`): unchanged — Phase 5 still exists.
  - **Cross-Repo Bugs section** (lines ~240–247): delete the bullet `Phase 6 (canary) runs per service — invoke /canary from each affected repo's worktree.` Update the next bullet `Phase 7 merges in the order the repos are listed in touched_repos:` to read `Phase 6 merges in the order the repos are listed in touched_repos:`.
  - **Any other phase-number references** uncovered during implementation: audit the full file for the literal strings `Phase 6`, `Phase 7`, and `7.5` after the edits and reconcile each occurrence with the new numbering.

## Acceptance Criteria

- [ ] `grep -n 'Phase 7\.5' bugfix/SKILL.md` returns no matches.
- [ ] `grep -n '### Phase 6: Canary' bugfix/SKILL.md` returns no matches.
- [ ] `grep -n '### Phase 6: Wrapup' bugfix/SKILL.md` returns exactly one match.
- [ ] `grep -n '### Phase 7' bugfix/SKILL.md` returns no matches.
- [ ] `grep -n 'happens in Phase 6' bugfix/SKILL.md` returns the renumbered Phase 4 verify line.
- [ ] The frontmatter `description` field no longer contains the substring `+ canary`.
- [ ] No remaining `/canary` invocation appears as a numbered pipeline step. (`/canary` may still be referenced in prose if the audit finds a sensible context; otherwise remove.)
- [ ] The "Cross-Repo Bugs" section's bullet list contains no `Phase 6 (canary)` line and the merge-order bullet says `Phase 6 merges` (not `Phase 7 merges`).
- [ ] The file still reads as a coherent end-to-end bug-fix workflow when read top-to-bottom.

## Technical Notes

- Use the Edit tool with surgical, anchored old_string values; do NOT Write the whole file. Each edit should target a unique-enough span to avoid `old_string is not unique` errors.
- The Phase 6 deletion is the largest single edit. Delete from the `### Phase 6: Canary Deploy (Optional)` heading down to but not including the `### Phase 7: Wrapup` heading. Then a separate edit renumbers the Phase 7 heading.
- After all edits, re-read the file and grep for `Phase 7`, `Phase 6`, `7.5`, `canary`, and `Canary` to verify nothing was missed.
- This REQ is informed by REQ-380 (which removed the same anti-pattern from `/proceed`). The renumbering pattern mirrors REQ-380's collapse of Phase 7 → Phase 7.5 → Phase 8 into Phase 7 → Phase 8.
- No tests to run — this is a markdown-only edit. Verification is by inspection + the grep ACs above.
