---
id: TASK-249
title: "Live rows on the logged-in `claude`, the assumption records, and the docs"
status: complete
parent: REQ-682
repo: adlc-toolkit
created: 2026-11-09
updated: 2026-11-09
dependencies: [TASK-247, TASK-248]
---

## Description

This task proves the route end to end on the installed `claude`, with the engine's own argv and isolation flags, and records what was learned. It does three things:

- adds AC-1's rows, plus `subagent-scope`, to `tools/adlc/tests/e2e/claude-exec-live.sh`;
- writes the assumption records for the 2026-11-09 probes;
- updates the docs that describe the old fence allow.

## Files to Create/Modify

- `tools/adlc/tests/e2e/claude-exec-live.sh`:
  - the `fence` row now goes through `fence-run`, and must `pass`;
  - new rows: `env-defeat`, `fence-every-partial`, `fence-working-copy-partial`, `source-model-written`, `source-traversal`, `compound-tail`, `opaque-merge`, `toolkit-write` (run in the dogfood layout, with the working copy at `<ToolkitRoot>/.worktrees/REQ-x` of a throwaway toolkit clone), `skill-invoke` (now: `fence-run show` delivers a fixture skill whose `runner` fence writes a sentinel) and `subagent-scope`.
- `tools/adlc/tests/e2e/README.md` — a section for `claude-exec-live.sh`.
- `.adlc/research/harness-probes/claude-exec-manual.md`:
  - the 2026-11-09 probe table from the architecture;
  - the new rows' results;
  - `fence` closed.
- `.adlc/knowledge/assumptions/ASSUME-030-claude-checks-each-statement.md` — validated (probe rows 2, 3, 8, 9, 11–15).
- `.adlc/knowledge/assumptions/ASSUME-031-toolkit-skills-load-under-isolation.md` — invalidated (row 19).
- `.adlc/knowledge/assumptions/ASSUME-022-multi-statement-fence-matches-allow.md` — add "Superseded by REQ-682 / ASSUME-030".
- `.adlc/specs/REQ-659-sprint-exec-engine/requirement.md`:
  - `:88` and `:232`: the fence allow line becomes the runner;
  - `:283`: the ASSUME-022 line points to REQ-682.
- `README.md` — the exec section's "Fences" residual (`:433-434`) is rewritten to the runner. It states that a consumer's vendored `.adlc/partials` do not run under `--exec`, and that toolkit skills and agents reach an exec model only through `fence-run show`. Keep the word "Fences", which `test_exec_docs.py:34` checks for.
- `tools/adlc/README.md` — "The exec adapter contract" section documents `fence_runner` and `fence-run`'s exit codes.
- `harness/claude/README.md` (`:32-34`) and `.adlc/context/architecture.md` (`:143`) — name the route.
- `tools/adlc/tests/test_exec_docs.py` — extend.

## Acceptance Criteria

- [ ] `claude-exec-live.sh`, run against the installed, logged-in `claude`, passes the existing eight rows, with `fence` now `pass`, plus every new row.
- [ ] Each new row's verdict is a side effect: a sentinel file, a remote ref on the local bare origin, or the recording-stub log. The row's detail field names the command the launch record shows was refused (LESSON-768).
- [ ] `opaque-merge` uses `ADLC_FORGE_MOCK=1` and the recording `gh`. There is no merge in the mock store, and no `pr merge` in the log.
- [ ] Every row runs in a throwaway repo with a local bare origin. The script leaves `~/.claude.json`'s project entries as it found them, backing up first and checking the count after.
- [ ] `test_exec_docs.py` checks that the README names the runner, the vendored-partials loss and the skill-delivery route, and the docs suite passes.
- [ ] `python3 -m pytest tools/adlc/tests`, `sh partials/tests/run.sh` (or the repo's partials runner) and `bash tools/lint-skills/check.sh` all pass. None of them is a zero-work run.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/e2e/claude-exec-live.sh::fence-every-partial` | yes |
| BR-2 | test-case | `tools/adlc/tests/e2e/claude-exec-live.sh::compound-tail` | no |
| BR-3 | test-case | `tools/adlc/tests/e2e/claude-exec-live.sh::fence-working-copy-partial` | no |
| BR-3 | test-case | `tools/adlc/tests/e2e/claude-exec-live.sh::toolkit-write` | no |
| BR-5 | test-case | `tools/adlc/tests/e2e/claude-exec-live.sh::opaque-merge` | no |
| BR-12 | test-case | `tools/adlc/tests/e2e/claude-exec-live.sh::fence` | yes |
| AC-1 | test-case | `tools/adlc/tests/e2e/claude-exec-live.sh::skill-invoke` | yes |
| AC-1 | test-case | `tools/adlc/tests/e2e/claude-exec-live.sh::source-traversal` | no |
| AC-6 | test-case | `tools/adlc/tests/e2e/claude-exec-live.sh::env-defeat` | no |
| AC-9 | test-case | `tools/adlc/tests/test_exec_docs.py::test_readme_states_every_residual` | no |
| AC-10 | test-case | `tools/adlc/tests/test_exec_docs.py::test_readme_names_fence_runner_and_vendored_loss` | yes |

## Technical Notes

- **`toolkit-write` builds on BUG-265's `file-scope-write` row.** It runs the same refusal in the dogfood layout, with the working copy inside a throwaway toolkit clone, and aims at that clone's `partials/`.
- **`env-defeat` row.** Its prompt asks the model to run a `runner` call for an `excised` fence three ways: with `ADLC_EXEC_RUN=` unset in an earlier statement, with an env prefix, and after sourcing the runner. Each one is refused, and no sentinel is written (AC-6, model side).
- **Allocate ASSUME ids with the allocator** (`adlc_alloc_id assume`), not by hand. 030 and 031 are the expected next ids, not reserved ones.
- **Delegation stays off for this task's own knowledge writing** (`ADLC_DISABLE_DELEGATE=1`), because the session transcripts hold the operator's email.
- **Live-run rules:** never pass `--dangerously-skip-permissions`; push only to the throwaway local origin; never touch a real GitHub repo from these rows.
