---
id: TASK-003
title: "Catalog /adversary in README + dogfood/lint shell-safety gate"
status: complete
parent: REQ-517
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-001, TASK-002]
repo: adlc-toolkit
---

## Description

Add `/adversary` to the README Skills catalog (AC) and run the BR-7 shell-safety
verification over the authored SKILL.md: `lint-skills` clean pass plus dogfooding
the fenced blocks under `zsh -c` and `bash -c` (macOS + Linux parity).

## Files to Create/Modify

- `README.md` — add a `/adversary` row to the Skills table

## Acceptance Criteria

- [ ] README Skills table includes a `/adversary` entry positioned near `/review` /
      `/reflect` (the sibling review skills).
- [ ] `python3 tools/lint-skills/check.py` passes clean (exit 0) with the new SKILL.md
      present.
- [ ] The fenced shell blocks in `adversary/SKILL.md` execute correctly under both
      `zsh -c` and `bash -c` (no GNU-only flags; Linux parity AC).
- [ ] The skills listing / catalog mentions `/adversary` (README AC satisfied).

## Technical Notes

- This task is the verification-and-documentation closer; it depends on both the agent
  (TASK-001) and the skill (TASK-002) being authored.
- Dogfooding the fenced blocks: extract each ```sh / ```bash block's body and run it
  under `zsh -c '...'` and `bash -c '...'` to confirm BSD/zsh parity (LESSON-329,
  LESSON-335, LESSON-013). Token-validation blocks should be exercised with both a
  valid and a hostile (`../`) input to prove the sanitization rejects traversal.
