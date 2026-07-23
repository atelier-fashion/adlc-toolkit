---
id: TASK-001
title: "Add the REQ-kind pre-push recheck call site to proceed/SKILL.md Step 0 item 4"
status: draft
parent: REQ-545
created: 2026-07-23
updated: 2026-07-23
dependencies: []
repo: adlc-toolkit
---

## Description

Insert the missing `adlc_recheck_id req "REQ-xxx"` call site into
`proceed/SKILL.md`, closing the REQ-518 BR-4 gap for the REQ kind. The call site
is a labeled prose paragraph + one `bash` fence, placed inside Step 0 item 4,
after the origin fetch / manifest advisory and before item `4a`
(so it is unambiguously after the fetch and before the `4b` worktree scan and the
item-5 `git worktree add -b`).

## Files to Create/Modify

- `proceed/SKILL.md` — add the recheck sub-block between the manifest advisory
  (end of item 4, current line ~197) and the `4a.` line (current line ~198).

## Acceptance Criteria

- [ ] Sources `partials/id-recheck.sh` (two-level fallback: `.adlc/partials/`
      then `~/.claude/skills/partials/`) and calls `adlc_recheck_id req "REQ-xxx"`
      **in the same fenced block** (BR-1).
- [ ] A collision (`adlc_recheck_id` returns non-zero) halts before any worktree /
      branch / push, surfacing the partial's `adlc renumber REQ-xxx REQ-yyy`
      message (BR-2).
- [ ] Self-exemption guard (BR-3): an exact-full-name `git ls-remote --heads
      origin refs/heads/feat/REQ-xxx-<slug>` probe short-circuits the recheck when
      the remote already carries this run's own branch (resume or crash-recovery);
      a same-id/different-slug branch or a merged-artifact hit still halts.
- [ ] Degraded remote proceeds (BR-4) — inherited from the partial; the call site
      treats only a non-zero return as a halt.
- [ ] Runs identically in solo `/proceed` and `/sprint` subagent mode; explicitly
      NOT skipped in subagent mode (BR-5), in contrast to the manifest advisory.
- [ ] Portable shell (BR-6): no `\b` in `grep -E`, no bare `$<digit>`, no `[0]`
      indexing, no `status=` var, no unquoted word-splitting loop, no arithmetic.
- [ ] Rationale-pointer comments present (BR-7): why the recheck exists, REQ-518
      BR-4 provenance, pointer to `partials/id-recheck.sh`.
- [ ] No existing Step 0 item is renumbered or reordered (AC-3).

## Technical Notes

Mirror the `/bugfix` (`bugfix/SKILL.md:46-54`) and `/wrapup`
(`wrapup/SKILL.md:297-305`) call-site pattern for the source + call + halt shape.
The `BRANCH` value is `feat/REQ-xxx-<slug>` — the SAME slug step 4b derives
(spec Assumption: no new slug logic). Use `<repo-path>` placeholder consistent
with item 4's `git -C <repo-path> fetch origin`. The self-exemption uses
`[ -n "$(git -C <repo-path> ls-remote --heads origin "refs/heads/$BRANCH" 2>/dev/null)" ]`
— exact-ref matching, no grep pattern needed.
