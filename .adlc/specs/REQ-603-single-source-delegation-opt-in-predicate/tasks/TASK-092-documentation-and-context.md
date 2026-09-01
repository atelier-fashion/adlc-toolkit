---
id: TASK-092
title: "Bring the gate's documented contract and the durable context in line"
status: draft
parent: REQ-603
created: 2026-09-01
updated: 2026-09-01
dependencies: [TASK-090]
---

## Description

Update every document describing how opt-in resolves, and record the invariant in the durable
project context so the next REQ inherits it rather than rediscovering it through a third
incident.

## Files to Create/Modify

- `partials/delegate-gate.md` — the precedence narrative becomes veto-then-dispatch; the reason table gains the ADR-4 correction
- `tools/delegate/README.md` — precedence section describes one resolver; document `--print-gate`
- `.adlc/context/architecture.md` — add the invariant: the shell gate may withhold delegation, never grant it
- `CHANGELOG.md` — Unreleased entry

## Acceptance Criteria

- [ ] No document still describes the gate as resolving `ADLC_DELEGATE_ENABLED` or legacy-key continuity in shell
- [ ] `--print-gate` is documented with its one-line output shape and the frozen reason enum
- [ ] `.adlc/context/architecture.md` states the withhold-never-grant invariant, citing BUG-205 and BUG-209 as the two directions it was violated from
- [ ] The ADR-4 reason correction is called out as a behaviour change, with the before/after rows
- [ ] This task claims **only** BR-12 and AC-16. BR-4, AC-17, and AC-20 were previously mapped here and moved: `tools/lint-skills` does not check reason strings, suite health belongs to TASK-091, and the pre-pass enum contract belongs to TASK-089. An obligation whose artifact cannot prove its rule is worse than an unmapped one — it reports as covered
- [ ] `tools/lint-skills` still passes over all SKILL.md files, scanning a non-zero count — run from **outside** `.worktrees`, since `SKIP_DIR_PARTS` makes an in-worktree run scan zero files and exit green (LESSON-019 #2)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-12 | structural-check | `tools/lint-skills`: no new skill directory introduced | yes |
| AC-16 | structural-check | `tools/lint-skills`: no added `*/SKILL.md` path in the scanned set | yes |

## Technical Notes

The lint run is the one place this task can go vacuously green. `tools/lint-skills` prints
`scanned <N> SKILL.md file(s)` and exits 255 when N is zero; `/proceed` runs every phase inside
`.worktrees`, which `SKIP_DIR_PARTS` excludes. Assert the scanned count is non-zero rather than
trusting exit 0 — this is LESSON-019's second defect and it has already produced one false
green in this repo.
