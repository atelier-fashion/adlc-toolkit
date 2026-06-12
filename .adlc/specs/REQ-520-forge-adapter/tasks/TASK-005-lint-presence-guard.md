---
id: TASK-005
title: "lint-skills presence guard — reject new direct gh pr in skills (BR-1)"
status: complete
parent: REQ-520
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-002]
---

## Description

Add a `lint-skills` check that rejects new direct `gh pr <subcommand>` usage in
`*/SKILL.md` fenced blocks, written against the POST-migration shape (LESSON-019:
presence guards rot when indirection moves). Allows `adlc_forge_*` and the explicitly
out-of-scope `gh pr diff` / `gh pr checks`; rejects `gh pr create|ready|edit|view|list|
merge|comment`.

## Files to Create/Modify

- `tools/lint-skills/check.py` — add the `forge-direct-gh` check; anchor to executable
  fenced blocks so prose/lesson mentions are not flagged.
- `tools/lint-skills/tests/` — add fixtures/asserts: a SKILL.md with `gh pr merge` fails;
  one using `adlc_forge_pr_merge` passes; `gh pr diff`/`gh pr checks` pass.

## Acceptance Criteria

- [ ] The check flags `gh pr {create,ready,edit,view,list,merge,comment}` inside a
      `*/SKILL.md` fenced block; allows `adlc_forge_*`, `gh pr diff`, `gh pr checks`.
- [ ] Written against post-migration shapes (no stale literal coupling to pre-migration
      lines); does not flag prose in lessons/agent docs (executable-fence-anchored).
- [ ] The migrated repo passes the new check (no direct `gh pr` op left in skills).
- [ ] Test fixtures cover pass and fail cases; existing lint-skills tests stay green.

## Technical Notes

Follow the existing check structure in `check.py` (and `sentinels.txt` if relevant). The
guard reads each SKILL.md's fenced code blocks and matches the gh-pr-op regex; keep the
allowlist (`diff`, `checks`, `adlc_forge_`) explicit and commented with the BR-1 rationale.
