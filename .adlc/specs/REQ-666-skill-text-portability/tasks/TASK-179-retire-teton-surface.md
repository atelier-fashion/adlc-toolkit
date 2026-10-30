---
id: TASK-179
title: "Retire the Teton-only surface: lint checks, skill lines, partial and convention sections"
status: complete
parent: REQ-666
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Remove everything built for Teton Code's shell-provenance classifier (ADR-3), in
one change so the lint and the text never disagree: the `harness-skip` and
`provenance-safe-fence` checks and the `missing-harness-line` rule, their
constants, wiring, fixtures and tests; every BUG-228/BUG-230 provenance line in
skill, companion and agent text; `/analyze`'s skill-wide shell rule and its
Step 1.8/1.9/1.10 skips; every `# provenance-safe` marker (git spellings kept);
the Teton Grep alternatives in `/review` and `/spec`; the
"Provenance-classifying harnesses" sections of `partials/delegate-gate.md` and
`partials/lesson-check.md` (the timeout guidance moves under
`### What a call site does with it`); the Teton lines of `partials/README.md`;
conventions.md's BUG-220 preamble-grammar and BUG-228 delegating-step paragraphs
(timeout guidance kept in the Delegation pattern section).

## Files to Create/Modify

- `tools/lint-skills/check.py` — drop the two checks, the rule, the constants and their wiring
- `tools/lint-skills/tests/test_check.py` — drop their tests
- `tools/lint-skills/tests/fixtures/harness-skip-ok.md` — delete (and the other `harness-skip-*`, `provenance-safe-*` and `lesson-check-order/*harness-line*` fixtures)
- `tools/lint-skills/tests/fixtures/lesson-check-order/bugfix-good.md` — drop the harness line from the remaining lesson-check-order fixtures
- `analyze/SKILL.md` — drop the shell rule, the skips and the markers
- `proceed/SKILL.md` — drop the provenance lines
- `proceed/phases-1-3-validation.md` — drop the provenance lines, if any
- `proceed/phases-6-8-ship.md` — drop the provenance lines, if any
- `proceed/phases-lite.md` — drop the provenance lines, if any
- `agents/pipeline-runner.md` — drop the provenance lines
- `spec/SKILL.md` — drop the provenance lines and the Teton Grep alternative
- `review/SKILL.md` — drop the Teton Grep alternative
- `wrapup/SKILL.md` — drop the provenance lines
- `bugfix/SKILL.md` — drop the provenance line
- `sprint/SKILL.md` — drop the provenance line
- `template-drift/SKILL.md` — drop the Teton harness mention (keep the teton-code repo example)
- `partials/delegate-gate.md` — drop the section, move the timeout guidance
- `partials/lesson-check.md` — drop the section
- `partials/README.md` — drop the Teton lines
- `.adlc/context/conventions.md` — drop the two paragraphs, keep the timeout guidance

## Acceptance Criteria

- [ ] `grep -rni 'teton\|provenance-safe\|provenance-classifying\|harness-skip' */SKILL.md agents/ partials/ tools/ README.md` returns only the repo-name lines ADR-3 lists
- [ ] no fixture exists for the retired checks, and no test references them
- [ ] `python3 tools/lint-skills/check.py --root .` exits 0 and never names a retired check
- [ ] `pytest tools/lint-skills/tests` passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_retired_harness_surface_is_gone` | yes |
| AC-5 | test-case | `tools/lint-skills/tests/test_skill_text_portability.py::test_retired_harness_surface_is_gone` | yes |
| BR-6 | structural-check | `tools/lint-skills`: no `harness-skip`/`provenance-safe-fence` in `check.py` | no |

## Technical Notes

`lesson-check-order` keeps every other finding id; only `missing-harness-line`
and its README row go. The `/analyze` Step 2a fences keep their git commands;
only the `# provenance-safe (BUG-230)` first lines go.
