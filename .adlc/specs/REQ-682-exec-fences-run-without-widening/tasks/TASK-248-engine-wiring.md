---
id: TASK-248
title: "Wire the route into the engine: rewritten prompts, the runner allow, retired inert allows, `exec_prompt_refused`"
status: complete
parent: REQ-682
repo: adlc-toolkit
created: 2026-11-09
updated: 2026-11-09
dependencies: [TASK-243, TASK-244, TASK-246]
---

## Description

This task makes the exec engine use the route.

- **The prompt build** (`pipeline_prompt` and `closeout_prompt`) rewrites every fence it delivers into its route's form, using the same function `fence-run show` uses. It raises `ExecPromptRefused` on an unrouted fence or an uninvoked-skill mismatch.
- **The unattended notes** say that toolkit skills and agents are not loaded, and tell the model to use `fence-run show`, including for agents' checklists, run inline.
- **`harness/claude.yml`** gains `exec.fence_runner` and drops the two inert allows (architecture ADR-8).
- **`tiers()`** spells the runner allow from `toolkit_root()`.
- **`sprint_exec.py`** records `exec_prompt_refused` at its three prompt call sites, and launches nothing.

## Files to Create/Modify

- `tools/adlc/exec_prompt.py`:
  - fence rewrite in `_finish`'s input path;
  - `ExecPromptRefused(PromptRefused)`;
  - the `_EXEC_NOTES` additions;
  - the `PIPELINE_ALLOW` entries for the new note text.
- `tools/adlc/sprint_exec.py` — catch `ExecPromptRefused` at `:483`, `:1036` and `:1448`, and record `exec_prompt_refused` with the fence id and the refused statement.
- `harness/claude.yml`:
  - drop `allow_extra: [ADLC_TOOLKIT_ROOT=]`;
  - add `fence_runner: tools/adlc/fence-run`;
  - set `capabilities.fence_unmatchable: "yes"` and drop `fence_broad_spelling`;
  - update `accepted_fidelity.fence.partial-source.exec`;
  - reword the fence residual.
- `tools/adlc/harness_adapter.py` — add `fence_runner` to `_EXEC_KEYS`, and validate it as a toolkit-relative path.
- `tools/adlc/harness_render.py` — the exec branch of `_render_fence` (`:480-489`) renders no allow when `fence_unmatchable` is set, and reports `inexpressible:runner`, not `widened`.
- `tools/adlc/exec_adapter.py` — `tiers()` adds `Bash(<root>/tools/adlc/fence-run:*)` after vetting the path (absolute, charset, regular file under the root after `realpath`).
- Tests to update:
  - `tools/adlc/tests/test_exec_prompt.py`: widen the `install` fixture to hold `EXEC_FILES`, `partials/` and `agents/`;
  - `test_exec_adapter.py`, `test_exec_launch.py`;
  - `test_harness_framework.py:177-182`, `:278-285` and `:343-356`;
  - `test_harness_adapters.py:819-821`.

## Acceptance Criteria

- [ ] The delivered pipeline and close-out prompts hold no fence that sources a partial. Every `runner` fence appears as a `<root>/tools/adlc/fence-run run <id>` call, and `fence_census` re-reads the prompt with no unrouted fence.
- [ ] Adding the TASK-244 fixture fence to a copy of `proceed/phase-4-implementation.md` makes `pipeline_prompt` raise `ExecPromptRefused`, naming that fence. `sprint_exec` records `exec_prompt_refused` and starts no harness process.
- [ ] Benign path: the unmodified tree builds both prompts with no refusal, and `test_prompt_is_stable_bytes` is updated to the new bytes in this task only.
- [ ] The rendered exec allow set holds `Bash(<root>/tools/adlc/fence-run:*)`, and holds neither `Bash(ADLC_TOOLKIT_ROOT=:*)` nor `Bash(if [ -f .adlc/partials/:*)`. `test_launch_refused_without_config_isolation` and `test_prefix_extra_sharing_a_deny_base_is_refused` pass unchanged.
- [ ] Project scope is byte-identical before and after: `adlc harness render --harness claude`, `.claude/settings.json` and the `harness/claude/rendered/` goldens. `test_harness_lints.py:30` still reads `exact=81, inexpressible=1, residual=2`. If `fence_unmatchable` would move the project verdict, apply it at exec scope only, and keep the key for project scope, as ADR-8 says.
- [ ] `ADLC_DELEGATE_*` is not in `env_passthrough`, and the child's recorded environment holds no delegation opt-in the engine added.
- [ ] `python3 -m pytest tools/adlc/tests` and `bash tools/lint-skills/check.sh` pass.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_delivered_fences_are_all_routed` | no |
| BR-7 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_inert_fence_allows_retired` | no |
| BR-7 | test-case | `tools/adlc/tests/test_exec_launch.py::test_launch_refused_without_config_isolation` | no |
| BR-8 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_unrouted_fence_refuses_the_build` | no |
| BR-8 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_pipeline_prompt_real_tree` | yes |
| BR-9 | test-case | `tools/adlc/tests/test_exec_launch.py::test_exec_prompt_refused_launches_nothing` | no |
| BR-10 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_allowlist_fidelity_counts` | yes |
| BR-11 | test-case | `tools/adlc/tests/test_exec_launch.py::test_child_env_adds_no_delegation_opt_in` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_exec_prompt.py::test_unrouted_fence_refuses_the_build` | no |
| AC-7 | test-case | `tools/adlc/tests/test_harness_framework.py::test_project_render_unchanged_by_fence_runner` | yes |
| AC-8 | test-case | `tools/adlc/tests/test_exec_launch.py::test_child_env_adds_no_delegation_opt_in` | yes |
| AC-9 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_prefix_extra_sharing_a_deny_base_is_refused` | no |

## Technical Notes

- **Built on BUG-265.** Start from a main that holds BUG-265. BUG-265 changed `ExecAdapter.tiers()` to `tiers(branch, config_extra, write_roots, read_roots)` and moved the file tools into `exec.file_rules`. The runner allow is added beside those rules, and `test_launch_scopes_file_tools` must stay green: the runner adds no `Edit` rule.

- **Rewrite then scan.** The rewrite runs before `scan()`, so the BR-24 token scan reads the bytes the model actually receives. An `excised` fence's replacement line must not itself contain a BR-24 token, so name the reason, not the command.
- **The note text** for agents names the inline fallback, matching the dispatch paragraph's own wording (`dispatch-has-fallback` lint), so the prompt and the skills say the same thing.
- **AC-7 counts.** Each exec-scope test fixture that changes on purpose (`fence_broad_spelling`, the `widened:` string) is listed in the PR body (spec AC-7).
- **Out of scope.** Leave `harness/codex.yml` and `harness/copilot.yml` alone: REQ-662 owns their exec routes.
