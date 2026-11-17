---
id: TASK-265
title: "The Codex exec block, its refreshed facts, and its census golden"
status: draft
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-259, TASK-264]
---

## Description

Write `harness/codex.yml`'s exec block as architecture ADR-11 states it, bring the file's stale facts up to the result on `main`, and add the Codex census golden. This is the task that makes Codex exec-capable.

## Files to Create/Modify

- `harness/codex.yml` — the exec block; the header's date; `accepted_fidelity` (the `exec` verdicts, and the comment that still cites a `routine-only` pass); `deny_under_allow` (`prefix` a `pass` with mechanism `deny`, `git-c` a `fail`); `fence_broad_spelling` dropped if the loader no longer requires it; `exec.probes` copied from the result file.
- `harness/codex/exec-fence-census.json` (new) — written by `fence_census --write`.
- `harness/codex/rendered/*` — regenerated only if a render changes; say in the commit whether it did.
- `README.md` — only the `harness-loss: codex` rows the `harness-loss-table` lint forces (the full exec section is TASK-268).
- `tools/adlc/tests/test_harness_codex.py`, `tools/adlc/tests/test_exec_adapter.py` (`test_no_exec_block_names_the_sibling_req` now names an unstaged adapter).

## Acceptance Criteria

- [ ] `harness/codex.yml` loads at exec schema 2 and `exec_verify.verdict` over the committed `codex.json` reads `verified`.
- [ ] The same block with `context_delivery: hooks` reads `unverified`, naming `trust-then-headless` and `session-start-context`.
- [ ] The rendered launch argv is `codex exec --json --sandbox workspace-write -C <wt> -o <file>`, snapshot-tested, and holds no forbidden flag.
- [ ] The exec rule file holds the fence-runner allow, a `forbidden` decision for every deny-tier entry, and no `git push`, `git branch` or `git -C` allow.
- [ ] Every fidelity finding at `exec` scope is declared in `accepted_fidelity`, so the pre-flight passes.
- [ ] The declared strategy agrees with `sandbox_can_reach_common_gitdir` and with `git-write-worktree` in `codex.json`; a fixture where they disagree refuses the adapter naming both.
- [ ] The committed `harness/codex/exec-fence-census.json` equals a fresh census, holds no `direct` route and no `unrouted` one.
- [ ] `bash tools/lint-skills/check.sh` is clean, including `harness-loss-table`, `render-parity` and `allowlist-fidelity`.
- [ ] `harness/copilot.yml`, `harness/cursor.yml` and `harness/antigravity.yml` are unchanged and still refused by name.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| AC-9 | test-case | `tools/adlc/tests/test_harness_codex.py::test_strategy_agrees_with_the_gitdir_record_and_the_probe` | yes |
| AC-24 | test-case | `tools/adlc/tests/test_harness_codex.py::test_codex_census_golden_is_fresh_and_has_no_direct_route` | yes |
| AC-25 | test-case | `tools/adlc/tests/test_harness_codex.py::test_codex_declares_prompt_delivery_and_is_verified` | yes |
| AC-11 | test-case | `tools/adlc/tests/test_harness_codex.py::test_codex_declares_prompt_delivery_and_is_verified` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_harness_codex.py::test_codex_launch_argv_snapshot` | no |
| BR-9 | test-case | `tools/adlc/tests/test_harness_codex.py::test_strategy_agrees_with_the_gitdir_record_and_the_probe` | yes |

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- Every value in the block comes from `.adlc/research/harness-probes/codex.json` or the installed CLI's help. Guess nothing; a value no evidence supports is `unknown` or `unverified`.
- `forbidden_flags` for Codex is the list in architecture ADR-7.
- The `resume` template is ADR-7's and is provisional until TASK-266's record; if that record fails, this block drops `resume`.
- Keep the yml the source: enumerations in prose stay out (BR-14).
- Lessons in play: LESSON-868 (model a deny only where it was seen to refuse), LESSON-755 (decide a capability from the installed binary, not the docs).
