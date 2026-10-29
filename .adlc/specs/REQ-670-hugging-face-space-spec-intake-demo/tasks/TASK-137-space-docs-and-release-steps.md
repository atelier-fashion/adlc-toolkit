---
id: TASK-137
title: "Docs: Space release and deploy steps, architecture entry, changelog"
status: complete
parent: REQ-670
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-136]
repo: adlc-toolkit
---

## Description

Document how the Space is built, checked and deployed from a tagged release, and
record the Space in the project's architecture context. Deployment itself and the
root README URL wait for the maintainer (architecture ADR-11).

## Files to Create/Modify

- `RELEASING.md` — "Hugging Face Space (REQ-670)" section: run `node space/build.mjs --check` and `node --test 'space/tests/*.test.js'` as release gates; deploy by checking out the tag, building, and pushing `space/` contents to the Space repo; record the URL in `README.md` only once live; add the dataset link to the card only once REQ-671 is live; the manual live check (AC-1).
- `.adlc/context/architecture.md` — a "Hugging Face Space (REQ-670)" entry under Key cross-cutting dependencies, and `space/` in the top-level layout.
- `CHANGELOG.md` — `[Unreleased]` entry.

## Acceptance Criteria

- [ ] `RELEASING.md` lists the two Space gates and the deploy steps, and states that the README gets the Space URL only once it is live.
- [ ] `RELEASING.md` describes the manual live check: the sample source with a real key returns every template section and at least one gap.
- [ ] `tools/lint-skills/check.sh` passes (`RELEASING.md` is a builtin-collision surface).
- [ ] No root README Space link is added in this task.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-13 | structural-check | `tools/lint-skills`: builtin-collision over `RELEASING.md` | no |
| AC-1 | structural-check | `RELEASING.md` manual live-check step, run by the maintainer at deploy | no |
| AC-12 | structural-check | `RELEASING.md` deploy steps; README URL added at deploy with maintainer approval | no |

## Technical Notes

AC-1 and AC-12 need a real key and a live Space. They are maintainer steps at
deploy time, not pipeline steps, and the PR body says so.
