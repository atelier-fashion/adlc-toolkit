---
id: TASK-006
title: "README install rewrite (two commands), tools/adlc/README.md, BR-8 audit note"
status: draft
parent: REQ-519
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-004, TASK-005]
repo: adlc-toolkit
---

## Description

Documentation: rewrite the README install section to exactly two commands
(BR-10), write `tools/adlc/README.md`, and record the BR-8 sibling-skill
preflight audit finding.

## Files to Create/Modify

- `README.md` — replace the "Install" section with the two-command happy path:
  1. `git clone …`
  2. `./install.sh`
  Everything else (verify, remediation, delegation opt-in) is discoverable via
  `adlc doctor`. Move the detailed manual symlink steps into an "Under the hood
  / manual install" appendix so the knowledge is preserved but off the happy
  path. Add `adlc` / `adlc doctor` to the tools section.
- `tools/adlc/README.md` — document the `adlc` umbrella CLI, the `doctor`
  subcommand, the full check list with what each verifies and its remediation,
  the `--checks <subset>` skill pre-flight contract (BR-8), and the install.sh
  idempotency/dry-run/repair test notes (the dogfood procedure for the ACs).
- The BR-8 audit note (in `tools/adlc/README.md` or architecture.md): record
  that sibling skills (`/sprint`, `/proceed`) currently express preflight probes
  in prose, not concrete duplicated shell, so there is no duplicated executable
  probe to delete in this REQ; the `--checks` contract is now available for them
  to converge on going forward.

## Acceptance Criteria

- [ ] README "Install" happy path is exactly two commands (BR-10).
- [ ] Manual/detailed steps preserved in an appendix, not deleted.
- [ ] `tools/adlc/README.md` lists every doctor check with its remediation and
      documents the `--checks` filter (BR-8).
- [ ] The BR-8 audit finding is recorded (no duplicated probe shell exists to
      remove; contract is forward-available).
- [ ] No fenced shell block added to any SKILL.md (README is not a skill, so
      lint-skills does not apply) — but if any is, it passes `tools/lint-skills`.

## Technical Notes

- Keep the README example commands copy-pasteable and BSD/zsh-safe.
- Cross-link: README install → `adlc doctor`; `tools/adlc/README.md` →
  `/template-drift` for the template-version check; → `tools/kimi/README.md` for
  the delegation opt-in.
- Run `tools/lint-skills/check.py` if any skill file was touched (none expected
  in this task).
