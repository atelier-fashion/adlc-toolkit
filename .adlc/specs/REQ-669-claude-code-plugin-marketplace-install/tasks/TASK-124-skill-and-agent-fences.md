---
id: TASK-124
title: "Rewrite skill, phase and agent fences to the ToolkitRoot spelling"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-123]
---

## Description

Apply the TASK-122 contract to the corpus. Every fence that sources a partial or reaches a toolkit-owned file gets the root line once, before its first use, and the new guarded operand. The explorers counted 57 guarded lines in SKILL.md and about 15 in phases, partials docs and agents. That count is a starting point, not the oracle. The lint and a dash run are the oracle (LESSON-618). Prose that tells the model to read a toolkit file names it under `$ADLC_TOOLKIT_ROOT`. Once nothing uses the REQ-610 operand, this task retires it: TASK-122's `TRANSITIONAL_OLD_OPERAND` acceptance is removed, so the old form becomes an `unguarded-source` finding. `/init`, `/template-drift` and the agent-dispatch paragraphs are out of scope here; they belong to TASK-125 and TASK-126.

## Files to Create/Modify

- `spec/SKILL.md` — 18 lines: guarded sources and `delegate-tools-path.sh` sites, plus the prose at the template-read step.
- `wrapup/SKILL.md` — 14 lines.
- `analyze/SKILL.md` — 14 lines, including the retired-spelling prose in Step 1.5.
- `proceed/SKILL.md` — 10 lines.
- `proceed/phase*.md` — every guarded source in the phase companions.
- `bugfix/SKILL.md` — 7 lines.
- `architect/SKILL.md` — 1 to 2 lines.
- `status/SKILL.md` — 1 line.
- `manifest/SKILL.md` — 1 line.
- `agents/delegate-pre-pass.md` — fallback fences at the gate and tools-path sources, and the prose describing the fallback.
- `partials/tests/source-guard.test.sh` — two corpus-extraction cases: symlink-only and substituted root.
- `agents/pipeline-runner.md` — the `conflict-bound.sh` fence. A new opening "root banner" fence (the root line, then `echo "$ADLC_TOOLKIT_ROOT"`) so the repo-relative toolkit files the agent reads, such as `proceed/phases-lite.md` and `agents/lite-reviewer.md`, are read under the printed root.
- `tools/lint-skills/check.py` — remove `TRANSITIONAL_OLD_OPERAND` acceptance. The old operand is now a finding whose message names the new spelling.
- `tools/lint-skills/tests/test_check.py` — the old-operand case flips from pass to fire. Add a repo-root case asserting zero findings.
- `tools/lint-skills/tests/fixtures/guarded-source-ok.md` — drop the old-operand form.
- `tools/lint-skills/tests/fixtures/unguarded-source-fence.md` — add the old operand as a must-fire example.

## Acceptance Criteria

- [x] `tools/lint-skills/check.sh` reports zero `unguarded-source` and zero `toolkit-root-line` findings on the repo. Its `scanned` count equals the number of `*/SKILL.md` files.
- [x] Every rewritten fence is extracted and run under dash and zsh in a sandbox `HOME` with only the symlink install, and again with only `ADLC_TOOLKIT_ROOT` substituted. Each sources its partials without error. Do this as two new cases in `partials/tests/source-guard.test.sh` that run its extraction over the whole corpus, not a sample.
- [x] No SKILL.md instruction changes meaning on the symlink route. The diff is limited to the root line, the operand, and toolkit-file prose naming `$ADLC_TOOLKIT_ROOT` (BR-3).
- [x] `pytest tools/lint-skills/tests/ -q` and `sh partials/tests/run.sh` pass.
- [x] `grep -c` of the old operand `else . ~/.claude/skills/partials/` across `*/SKILL.md`, `proceed/phase*.md` and `agents/*.md` is 0.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/lint-skills/tests/test_check.py::test_repo_root_unguarded_source_and_root_line_clean` | no |
| BR-2 | test-case | `tools/lint-skills/tests/test_check.py::test_old_operand_now_fires` | no |
| BR-3 | test-case | `partials/tests/source-guard.test.sh::case_corpus_extraction_symlink_only` | yes |
| BR-4 | test-case | `partials/tests/source-guard.test.sh::case_corpus_extraction_substituted_root` | no |
| BR-10 | test-case | `tools/lint-skills/tests/test_check.py::test_repo_root_unguarded_source_and_root_line_clean` (skill references untouched; `canonical` and `sentinels` pass) | no |

## Technical Notes

- Mechanical rewrite with a reviewed script is fine, but certify it by execution, not by count (LESSON-618). Multi-line and continuation variants are exactly what a regex rewrite misses.
- Place the root line immediately before the first guarded source in the fence. Do not hoist it into a fence that does not use it; `toolkit-root-line` only requires it where `$ADLC_TOOLKIT_ROOT` is referenced.
- `${CLAUDE_PLUGIN_ROOT}` must appear in the text exactly as `${CLAUDE_PLUGIN_ROOT}`. Claude Code substitutes that braced token in plugin skill and agent bodies (architecture ADR-1).
- Skill-to-skill references such as "run `/validate`" are not edited (architecture ADR-5).
