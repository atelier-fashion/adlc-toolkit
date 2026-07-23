---
id: TASK-002
title: "Dogfood the recheck fence under bash+zsh and lint proceed/SKILL.md"
status: draft
parent: REQ-545
created: 2026-07-23
updated: 2026-07-23
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

Verify the added recheck block executes correctly and passes the skill linter.
Because "code is markdown" in this repo, the test IS dogfooding: extract the
fence, substitute real values, and run it under both operator shells against a
throwaway git remote fixture (LESSON-329).

## Files to Create/Modify

- None (verification only). A scratch fixture repo is created under a temp dir and
  removed afterward; nothing is committed from it.

## Acceptance Criteria

- [ ] The extracted fence runs without error under `bash -c` AND `zsh -c`.
- [ ] Clean remote (no matching branch/artifact): recheck returns success, flow
      continues (AC-3, AC — clean path).
- [ ] Remote holds `feat/REQ-545-<identical slug>` from a prior/crashed session:
      no collision halt (self via exact-full-name match) (BR-3 / AC-5, AC-6).
- [ ] Remote holds `feat/REQ-545-<different slug>` (same id, different slug):
      collision halt fires (BR-3 / AC-6).
- [ ] Prefix-sibling safety: rechecking `REQ-120` against a remote holding
      `feat/REQ-1200-*` does NOT halt (inherited from `id-recheck.sh` exact
      equality; AC-7).
- [ ] Degraded/unreachable remote: warns and continues, never halts (BR-4).
- [ ] `tools/lint-skills/check.py` passes on `proceed/SKILL.md` — no
      `cross-fence-fn` and no `forge-direct-gh` finding (AC-9).

## Technical Notes

Read `tools/lint-skills/check.py` first to learn its invocation and the exact
`cross-fence-fn` rule, then run it against `proceed/SKILL.md`. For the dogfood,
stand up a bare git repo as `origin` inside a mktemp dir, push synthetic
`feat/REQ-545-*` / `feat/REQ-1200-*` branches to exercise each case, and source
`partials/id-recheck.sh` from the worktree. Set `ADLC_REPOS_ROOT` to the fixture
parent so `adlc_recheck_id`'s repo walk sees the fixture.
