---
id: TASK-182
title: "Run-and-read context blocks, the ethos-line check, and the allowlist additions"
status: complete
parent: REQ-666
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Replace the 41 non-ETHOS preamble lines in 14 skills with one `# adlc-context`
fence each under `## Context` (ADR-2); merge `/template-drift`'s toolkit fence
into its context fence; respell its prose mention of a bang line. Add the
`ethos-line` lint check and its fixtures. Add the allow entries to
`templates/claude-settings-template.json`. Add the BR-16 execution test.

## Files to Create/Modify

- `analyze/SKILL.md` — context fence
- `architect/SKILL.md` — context fence
- `bugfix/SKILL.md` — context fence
- `canary/SKILL.md` — context fence
- `manifest/SKILL.md` — context fence
- `optimize/SKILL.md` — context fence
- `reflect/SKILL.md` — context fence
- `review/SKILL.md` — context fence
- `spec/SKILL.md` — context fence
- `sprint/SKILL.md` — context fence
- `status/SKILL.md` — context fence
- `template-drift/SKILL.md` — context fence (merged with the toolkit listing)
- `validate/SKILL.md` — context fence
- `wrapup/SKILL.md` — context fence
- `templates/claude-settings-template.json` — allow entries
- `tools/lint-skills/check.py` — `ethos-line`
- `tools/lint-skills/tests/test_ethos_line.py` — new: missing, altered-by-one-byte, duplicated, clean tree
- `tools/lint-skills/tests/test_skill_text_portability.py` — context fences run under four shells in repo and consumer

## Acceptance Criteria

- [ ] `grep -n '!\`' */SKILL.md` returns exactly one line per skill, byte-identical to today's ETHOS line
- [ ] each of the 14 skills has exactly one `# adlc-context` fence; each exits 0 under bash, zsh, `/bin/sh` and dash in this repo and in a consumer without `.adlc/templates/`, printing the notices
- [ ] `ethos-line` fires once on each of the three bad fixtures and is clean on the tree
- [ ] the template's allow list gains the commands the fences use

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_context_fences_run_everywhere` | yes |
| BR-15 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_context_commands_are_allowlisted` | no |
| BR-16 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_context_fences_run_everywhere` | yes |
| AC-3 | test-case | `tools/lint-skills/tests/test_ethos_line.py::test_bad_fixtures_fire_once_each` | yes |

## Technical Notes

`/proceed`, `/init` and `/adversary` have no non-ETHOS preamble lines and get no
fence. Check `harness_probe`'s routine-set pin still holds after the template
edit (it asserts a subset).
