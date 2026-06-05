---
id: TASK-076
title: "Dogfood the cross-repo footprint round-trip by EXECUTION (publish to 2 repos, /manifest reads back)"
status: complete
parent: REQ-484
created: 2026-06-05
updated: 2026-06-05
dependencies: [TASK-075]
# repo omitted — single-repo project; attributes to primary (adlc-toolkit)
---

## Description

Verify BR-7 by EXECUTING the cross-repo footprint round-trip, not by reading the skill text
(LESSON-329 — dogfood under the executor shell). REQ-483 dogfooded only single-repo; this REQ
must prove the multi-repo path works end to end:

1. Construct a two-repo fixture (simulate two repo-ids, e.g. `repoA` and `repoB`) since this
   repo is single-repo.
2. Execute the new per-repo derivation + publish logic from TASK-075 against the fixture,
   publishing per-repo footprints to ≥2 PR bodies (use real test PRs or a faithful local
   simulation of the `gh pr view`/`gh pr edit` body round-trip).
3. Run `/manifest`'s footprint-parsing logic over both PR bodies and CONFIRM:
   - Each PR's block contains ONLY its own repo's repo-qualified lines.
   - A same-path-different-repo pair (`repoA:src/x` vs `repoB:src/x`) does NOT register as an
     overlap.
   - A genuine same-(repo,path) pair DOES register as an overlap.
4. Confirm the single-repo path still produces output equivalent in intent to REQ-483
   (regression check on a single-repo fixture).
5. Run the new fenced block under BOTH `sh -c` and `zsh -c` (the executor shell on macOS is
   zsh) to catch word-splitting/glob divergence (LESSON-329).

This is a verification task — no production file changes beyond what TASK-075 lands. Capture the
executed evidence in the dogfood notes (commit message / PR body), per the toolkit's
markdown-skill verification model.

## Files to Create/Modify

- (none — verification task) Evidence is captured in the Phase-5/Phase-7 notes and PR body.
  If TASK-075's execution surfaces a bug, the fix lands in `architect/SKILL.md` under TASK-075's
  file scope (re-open TASK-075), not here.

## Acceptance Criteria

- [ ] The cross-repo round-trip is EXECUTED (not just read): per-repo footprints published to
      ≥2 simulated repos' PR bodies, then `/manifest`'s footprint parser run over both.
- [ ] `repoA:x` vs `repoB:x` (same path, different repo) does NOT register as an overlap;
      a genuine same-(repo,path) pair DOES — confirmed by executing the parser.
- [ ] Single-repo fixture produces output equivalent in intent to REQ-483 (no regression).
- [ ] The new fenced block runs cleanly under both `sh -c` and `zsh -c` (LESSON-329) — no
      "no matches found" glob abort, no trailing-space word-split bug.
- [ ] Executed evidence recorded (paths published, parser output, both-shell runs) in the
      dogfood notes.

## Technical Notes

- **Extract the fenced block for execution**:
  `awk '/^```sh$/{f=1;next} f&&/^```$/{exit} f' architect/SKILL.md` to pull the publish block,
  then run it under `sh -c` and `zsh -c` against the fixture.
- **Fixture without real siblings**: this repo has no `.adlc/config.yml`. Build a temp
  `pipeline-state.json` fixture with two `repos` entries (`repoA` primary, `repoB` sibling),
  each with a distinct `prNumber`, plus two task files tagged `repo: repoA` / `repo: repoB`.
  Stub `gh pr view`/`gh pr edit` with local body files (or use real throwaway PRs if cheap) to
  exercise the read-modify-write of the PR body.
- **Manifest parser**: the read-side block is in `manifest/SKILL.md` (the
  `sed -n "/^${tick}adlc-footprint/,/^${tick}/..."` + split-on-`:` + `..`-reject + charset).
  Extract and run it over both fixture PR bodies; assert the overlap result.
- **Do not mutate any real session's PR/branch** (permissions table — write only into THIS
  REQ's own artifacts/fixtures).
