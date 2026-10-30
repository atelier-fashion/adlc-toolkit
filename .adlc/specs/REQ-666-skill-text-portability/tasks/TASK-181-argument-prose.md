---
id: TASK-181
title: "Arguments as prose: no $ARGUMENTS in any SKILL.md"
status: complete
parent: REQ-666
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Rewrite every Input section and every prose `$ARGUMENTS` reference (ADR-1).
`/spec`'s two intake fences take `'<request>'`; `/manifest`'s self-id fence
takes `self_args='<req-ids>'`; `/sprint`'s Workflow call prose says "the
argument". State the substitution rule once in conventions.md "Bash in skills".

## Files to Create/Modify

- `adversary/SKILL.md` — Input prose
- `analyze/SKILL.md` — Input prose
- `architect/SKILL.md` — Input prose
- `bugfix/SKILL.md` — Input prose
- `canary/SKILL.md` — Input prose and service-resolution prose
- `init/SKILL.md` — Input prose
- `manifest/SKILL.md` — Input prose and the self-id fence
- `optimize/SKILL.md` — Input prose
- `proceed/SKILL.md` — Arguments prose
- `reflect/SKILL.md` — Input prose
- `review/SKILL.md` — Input prose
- `spec/SKILL.md` — Input prose, the two intake fences, Step 1.4/1.5 prose
- `sprint/SKILL.md` — Input prose and the Workflow call prose
- `status/SKILL.md` — Input prose
- `template-drift/SKILL.md` — Input prose and the /status note
- `validate/SKILL.md` — Input prose
- `wrapup/SKILL.md` — Input prose
- `.adlc/context/conventions.md` — the substitution rule
- `tools/lint-skills/tests/test_skill_text_portability.py` — new: AC-1 greps, AC-2 hostile-request probe under four shells

## Acceptance Criteria

- [ ] `grep -rnE '\$\{?ARGUMENTS' */SKILL.md` and `grep -rn '\$[0-9]' */SKILL.md` return nothing
- [ ] `/spec`'s gate fence, with a request holding a backtick, `$`, `$(…)` and an apostrophe substituted by the rule, prints `intake_gate=1` under bash, zsh, `/bin/sh` and dash
- [ ] `/spec`'s lane-flag prose still strips `--lite`/`--full` and errors on both

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_no_arguments_placeholder` | no |
| AC-1 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_no_arguments_placeholder` | no |
| AC-2 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_spec_intake_gate_takes_a_hostile_literal` | yes |

## Technical Notes

The test substitutes with the rule (`'` → `'\''`, wrapped in `'…'`) rather than
by a shell-safe helper, so it fails if the rule's spelling is wrong.
