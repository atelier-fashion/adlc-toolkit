---
id: TASK-003
title: "Insert /analyze Step 1.9 (skill-md-corruption audit dimension)"
status: complete
parent: REQ-425
created: 2026-05-15
updated: 2026-05-15
dependencies: [TASK-001]
---

## Description

Insert a new Step 1.9 in `analyze/SKILL.md` between Step 1.8
(delegation-fidelity) and Step 2. The step runs
`tools/lint-skills/check.sh`, parses findings, and surfaces them as a
`skill-md-corruption` audit dimension — mirroring the silent-skip /
happy-path / failure-mode pattern Step 1.8 established.

## Files to Create/Modify

- `analyze/SKILL.md` — add a new `### Step 1.9: SKILL.md corruption audit`
  section between the existing Step 1.8 and Step 2 sections.

## Acceptance Criteria

- [ ] Step 1.9 is inserted directly before `### Step 2: Launch Audit Agents
      + Repo Hygiene Scan (parallel)`.
- [ ] Step 1.9 silent-skips when `tools/lint-skills/check.sh` is absent
      (older installs) — emits nothing, raises no warning, continues.
- [ ] Happy path: emits `/analyze: skill-md-corruption clean (0 findings)`.
- [ ] On findings, emits each line of the linter output under a
      `skill-md-corruption` block.
- [ ] Failure mode (linter exits non-zero with no usable output): emits
      `/analyze: skill-md-corruption audit unavailable (check.sh failed)`
      and continues — never blocks the audit.
- [ ] Step 2's intro paragraph still reads correctly (no broken numbering
      or stale "between Step 1.8 and Step 2" references in surrounding
      prose).
- [ ] No other SKILL.md is edited.

## Technical Notes

- Mirror Step 1.8's structure exactly — gate block, parse block, finding
  format, happy-path line, failure-mode line. The reader should
  experience Step 1.9 as a parallel sibling to 1.8.
- Use the same gate idiom: `if [ -x tools/lint-skills/check.sh ]; then ...`.
- Do NOT reference Step 1.9 from Step 2's intro paragraph; the agents
  don't need to know.
- Place the section header at the same heading level (`###`).
