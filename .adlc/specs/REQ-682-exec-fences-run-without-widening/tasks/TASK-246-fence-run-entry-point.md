---
id: TASK-246
title: "`fence-run`: the one admitted entry point — `run` a census fence with values as data, `show` a skill with fences rewritten"
status: complete
parent: REQ-682
repo: adlc-toolkit
created: 2026-11-09
updated: 2026-11-09
dependencies: [TASK-244, TASK-245]
---

## Description

Add `tools/adlc/fence-run` (a POSIX shim) and `tools/adlc/fence_run.py` (stdlib), per architecture ADR-1 to ADR-5.

- **`run <id> [--arg n=v]… [--arg-file n=path]…`**
  1. Recomputes the census from the runner's own realpath root, and refuses any id whose route is not `runner` or whose sha does not match.
  2. Checks every value against its placeholder pattern.
  3. Transforms the fence: the root line becomes the literal root, canonical sourcing becomes the toolkit arm, and placeholders become `"$ADLC_ARG_<name>"`.
  4. Builds the environment: the inherited environment, plus `ADLC_ARG_*`, `ADLC_FENCE_TOOLKIT_ONLY=1` and `ADLC_TOOLKIT_ROOT=<root>`.
  5. Runs `/bin/sh -c` with the preload closure first.
- **`show <file>`** prints a file from `EXEC_FILES` with each fence replaced by its route's form.

## Files to Create/Modify

- `tools/adlc/fence-run` — new executable shim. It finds `fence_run.py` from its own `realpath` and runs it with the ONE interpreter (REQ-609 ADR-2, as `install.sh`'s `adlc` shim does). It has no `python3` first token in any allow.
- `tools/adlc/fence_run.py` — new.
- `tools/adlc/tests/recording_stubs.py` — new shared helper. It writes recording `git`, `gh`, `az` and `curl` stubs first on `PATH`, plus a JSONL log of argv per call.
- `tools/adlc/tests/test_fence_run.py` — new.
- `tools/adlc/exec_safety.py` — `INSTALL_TREES` / `install_files` include the two new files, so the manifest check covers them.

## Acceptance Criteria

- [ ] `run` refuses an id that is unknown, whose sha does not match, or whose route is `direct`, `engine` or `excised`. Each refusal is exit 3 with one stderr line, `opaque_entry_refused: <id>: <reason>`, and nothing runs.
- [ ] Each BR-6 hostile value (`$(touch s)`, a backtick, `;`, a newline, `--force`, `main`, `HEAD:main`, `../`, a leading `-`) is passed as each placeholder of every `runner` fence. It is refused by its pattern, or it reaches the fence only as a quoted value. No sentinel is written, and no recorded argv falls outside the fence's reach record.
- [ ] `--arg-file` refuses a path that resolves outside the working directory (`..`, a symlink out), a non-regular file and a file over 1 MiB. A valid file's bytes reach the fence unchanged.
- [ ] A fence that can reach a one-way action is never `runner`: `adlc_forge_pr_merge` and every `EXCISED` id are refused even when `ADLC_EXEC_RUN` is unset, set to another value, or overridden with an env prefix. The refusal reads only toolkit text.
- [ ] Benign path: `adlc_forge_pr_create` and `adlc_forge_pr_view` fences run under `ADLC_FORGE_MOCK=1` and emit no `opaque_entry_refused`. An `adlc_lessons select` fence with valid values returns its normal output.
- [ ] With `ADLC_DISABLE_DELEGATE=1`, or no opt-in, a delegating fence takes its fallback path. The runner adds no `ADLC_DELEGATE_*` variable to the environment, and resolves `adlc-read` only through `delegate-gate.sh`'s absolute-path walk.
- [ ] `show` refuses a file outside `EXEC_FILES`. For `validate/SKILL.md` it prints every `runner` fence as a runner call, with the root spelled as an unquoted absolute path, and keeps every `direct` fence unchanged.
- [ ] A root path outside `^[A-Za-z0-9_./-]+$` makes `fence-run` refuse to start.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/adlc/tests/test_fence_run.py::test_run_reads_only_toolkit_text` | no |
| BR-5 | test-case | `tools/adlc/tests/test_fence_run.py::test_one_way_fences_refused_whatever_the_env` | no |
| BR-5 | test-case | `tools/adlc/tests/test_fence_run.py::test_safe_forge_fences_run_under_mock` | yes |
| BR-6 | test-case | `tools/adlc/tests/test_fence_run.py::test_hostile_values_never_run_code` | no |
| BR-9 | test-case | `tools/adlc/tests/test_fence_run.py::test_refusal_is_one_loud_line_exit_3` | no |
| BR-9 | test-case | `tools/adlc/tests/test_fence_run.py::test_valid_run_exits_with_fence_status` | yes |
| BR-11 | test-case | `tools/adlc/tests/test_fence_run.py::test_delegation_off_takes_fallback` | no |
| AC-5 | test-case | `tools/adlc/tests/test_fence_run.py::test_hostile_values_never_run_code` | no |
| AC-6 | test-case | `tools/adlc/tests/test_fence_run.py::test_refusal_holds_against_env_defeats` | no |
| AC-6 | test-case | `tools/adlc/tests/test_fence_run.py::test_safe_forge_fences_run_under_mock` | yes |
| AC-8 | test-case | `tools/adlc/tests/test_fence_run.py::test_delegation_off_takes_fallback` | yes |

## Technical Notes

- AC-6's four defeats map to tests as follows:
  - **Unsetting the state in an earlier statement:** a compound command. TASK-243's matcher shows Claude refuses it at the unset.
  - **Unsetting it in the same statement:** an env prefix. Claude does not admit it (row 13), and the runner reads no environment for its refusals anyway.
  - **Overriding it with an env prefix on the call:** same as the previous one.
  - **Re-sourcing the entry:** sourcing is refused (row 9).

  The unit test covers the runner's side: refusals are identical under every environment.
- Do not trust `ADLC_TOOLKIT_ROOT`, `CLAUDE_PLUGIN_ROOT` or `PATH` for the root. Use `toolkit_root.toolkit_root()`.
- The fence runs with cwd unchanged, which is the working copy the model is in.
- Pass the fence's exit code through. Reserve exit 3 for the runner's own refusals, and document that in `--help`.
- Do not print the fence's environment in any error. It holds the scoped GH token.
