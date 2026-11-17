---
id: TASK-260
title: "BR-11 as one function: the verdict, version equality, `--allow-unverified`, and the doctor line"
status: draft
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-258]
---

## Description

Implement architecture ADR-2. `exec_verify.verdict` recomputes `verified` or `unverified` from the probe result file, the adapter's declarations and the installed binary's version. The engine calls it at launch, resume, close-out and `approve`; `adlc harness doctor` prints it.

## Files to Create/Modify

- `tools/adlc/exec_verify.py` (new) — `verdict(adapter, result, installed_version)`, the result-file reader rooted at ToolkitRoot, and the rules of ADR-2.
- `tools/adlc/sprint_exec.py` — the verdict in `preflight`, before resume, at close-out and in `approve`; `--allow-unverified` on `run`, with its loud one-line notice on every launch.
- `tools/adlc/exec_ledger.py` — the ledger records the invocation that received `--allow-unverified`.
- `tools/adlc/harness_doctor.py`, `tools/adlc/harness_cli.py` — `exec: verified` / `exec: unverified (<probe ids>)` per installed harness with an exec block.
- `tools/adlc/tests/test_exec_verify.py` (new), `tools/adlc/tests/test_exec_launch.py`, `tools/adlc/tests/test_exec_approve.py`, `tools/adlc/tests/fixtures/probe-results/` (new).

## Acceptance Criteria

- [ ] Every hard probe `pass` and every declaration-bound probe agreeing reads `verified` (the must-not-refuse case).
- [ ] An `unknown` or `n/a` hard or declaration-bound entry, a `stdin-prompt` whose `prompt_variant` variant is not `pass`, a `fence-vs-allowlist` whose `runner-prefix` is not `pass`, and a `pass` under another `harness_version` each read `unverified`, naming the probe.
- [ ] A `fail` that agrees with a fallback declaration reads `verified`: `git-write-worktree: fail` with `clone`, `shell-timeout: fail` with `delegate: unsupported`, `ask-tier-deny: fail` with `deny_render: none`. Each disagreement refuses, naming the declared value and the verdict.
- [ ] `working_copy.strategy: worktree` with no `pass` `git-write-worktree` refuses the adapter naming the probe. A `sandbox_can_reach_common_gitdir` that disagrees with that probe refuses, naming both.
- [ ] With the `baseline` control's sentinel present, `deny-under-allow` `pass` allows `verified`, and `fail`, `unknown` or `n/a` reads `unverified` even where `fail` agrees with `deny_render: none`.
- [ ] `context_delivery: prompt` with `hooks-loaded` `fail`, `allowlist-loaded` `pass` and `session-start-context` `fail` is `verified`; the same result with `hooks` is `unverified`, naming both probes; with `allowlist-loaded` `fail` the `prompt` adapter is `unverified`.
- [ ] A hand-set `status: verified` with no matching result file reads `unverified`, and the engine refuses to launch.
- [ ] A fake binary whose version differs from `exec.harness_version` is refused at launch, at resume and at close-out without `--allow-unverified`.
- [ ] A result file edited to `pass` in the working copy while ToolkitRoot's copy says `fail` reads `unverified`.
- [ ] `--allow-unverified` in config, in `pipeline-state.json` or in the environment has no effect. On the CLI it launches with a loud notice, and a forbidden flag, a failed pre-flight and a missing approval gate still refuse. A later `launch`, `resume` or `approve` invocation does not honour it, and an adapter launched under it and approved without it refuses at `approve` before the forge mock sees a merge call.
- [ ] `verification: recorded` skips the probe set and still compares the version.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-11 | test-case | `tools/adlc/tests/test_exec_verify.py::test_verdict_table` | yes |
| AC-11 | test-case | `tools/adlc/tests/test_exec_verify.py::test_verdict_table` | yes |
| AC-16 | test-case | `tools/adlc/tests/test_exec_verify.py::test_baseline_present_makes_deny_under_allow_hard` | yes |
| AC-17 | test-case | `tools/adlc/tests/test_exec_verify.py::test_version_bound_and_read_from_toolkit_root` | yes |
| AC-25 | test-case | `tools/adlc/tests/test_exec_verify.py::test_context_delivery_prompt_requires_only_allowlist_loaded` | yes |
| BR-9 | test-case | `tools/adlc/tests/test_exec_verify.py::test_worktree_needs_a_passing_probe` | yes |
| BR-18 | test-case | `tools/adlc/tests/test_exec_approve.py::test_allow_unverified_is_per_invocation` | yes |
| AC-15 | test-case | `tools/adlc/tests/test_exec_launch.py::test_allow_unverified_is_cli_only` | yes |
| AC-21 | test-case | `tools/adlc/tests/test_exec_approve.py::test_allow_unverified_is_per_invocation` | yes |
| BR-14 | test-case | `tools/adlc/tests/test_exec_verify.py::test_doctor_prints_the_recomputed_verdict` | yes |

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No code under `tools/adlc` may compare a harness name (conventions, "Harness adapters are data"); a difference is an adapter field.
- No test writes outside a sandbox `HOME` and `ADLC_HOME` (`conftest.py`'s autouse fixtures). Never read `~/.codex/auth.json`.
- The result is read from `<ToolkitRoot>/.adlc/research/harness-probes/<name>.json`, never from a working copy. The result file's shape is in `tools/adlc/README.md` ("harness probe").
- The installed version comes from REQ-654's lookup (`tools/adlc/harness.py:_version`).
- The nested-launch refusal of BR-18 already exists (`sprint_exec.py`, `caller_guard`); add the test AC-21 asks for if none covers a live exec pid in the ancestry.
- Lessons in play: LESSON-718 (a gate must not load anything the change can edit), LESSON-847 (a `fail` is evidence only with proof).
