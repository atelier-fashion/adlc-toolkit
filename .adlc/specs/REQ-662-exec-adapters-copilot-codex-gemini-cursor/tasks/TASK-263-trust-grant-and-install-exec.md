---
id: TASK-263
title: "Per-run trust in the user config, and `adlc harness install --exec`"
status: complete
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-18
dependencies: [TASK-262]
---

## Description

Implement architecture ADR-5. For `trust_grant: user-config-entry` the engine writes one project-trust block into the adapter's user config before launch and removes exactly that block afterwards. Add the `install --exec` verb that writes the user policy file.

## Files to Create/Modify

- `tools/adlc/exec_trust.py` (new) — the path checks, the additive write, `pre_existing`, the surgical revoke, the lock, and the refusal while REQ-664's recovery marker exists.
- `tools/adlc/sprint_exec.py` — `grant_trust` and `revoke_trust` call it for the working copy and for the close-out working copy; `preflight` accepts `user-config-entry`; `exec.trustGrantedAt`, `trustRevokedAt` and `trustMechanism`.
- `tools/adlc/harness_cli.py` — `adlc harness install --exec --harness <name>` writes the user policy file through `exec_surfaces`.
- `tools/adlc/tests/test_exec_trust.py` (new), `tools/adlc/tests/test_exec_launch.py`, `tools/adlc/tests/test_exec_approve.py`.

## Acceptance Criteria

- [x] Under a sandbox `HOME`, before launch the user config gains exactly one `[projects."<working copy>"]` block and every other byte is unchanged.
- [x] After a successful run, a failed run, and a run whose fake is killed mid-phase, the block is gone and `exec.trustGrantedAt` and `trustRevokedAt` are set.
- [x] A path the sandbox already trusted is reported `pre_existing` and survives revoke.
- [x] Two engine runs started concurrently both end with correct files.
- [x] With a REQ-664 recovery marker present the engine refuses to launch, naming it. Without one it launches (the must-not-refuse case).
- [x] A relative path, an empty path and a symlink resolving outside the working-copy root are refused before any file is written.
- [x] The close-out working copy gets its own grant and revoke.
- [x] No write touches `hooks.state` or any other hook-review key: a fixture config holding one is byte-identical in that table afterwards.
- [x] `adlc harness install --exec` writes the policy file whole and atomically, and a second run is a no-op.
- [x] The block's spelling equals what `harness_probe.codex_trust_edit` writes, held by a test.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | `tools/adlc/tests/test_exec_trust.py::test_grant_is_additive_and_revoke_is_surgical` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_exec_trust.py::test_grant_is_additive_and_revoke_is_surgical` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_exec_launch.py::test_recovery_marker_refuses_the_launch` | yes |
| AC-15 | test-case | `tools/adlc/tests/test_exec_trust.py::test_trust_file_writes_are_serialized` | yes |
| AC-22 | test-case | `tools/adlc/tests/test_exec_trust.py::test_install_exec_writes_the_policy_file` | yes |
| AC-25 | test-case | `tools/adlc/tests/test_exec_trust.py::test_no_write_touches_hook_review_state` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_exec_launch.py::test_trust_is_granted_before_launch_and_revoked_at_every_exit` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_exec_launch.py::test_two_engine_runs_share_the_user_config` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_exec_launch.py::test_a_supervisor_that_dies_after_the_grant_is_cleaned_up` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_exec_approve.py::test_close_out_gets_its_own_trust_grant` | yes |
| BR-18 | test-case | `tools/adlc/tests/test_exec_approve.py::test_allow_unverified_on_answer_is_the_answering_invocations` | yes |
| BR-1 | test-case | `tools/adlc/tests/test_exec_launch.py::test_a_recovered_denial_halts_and_a_denied_code_blocks` | yes |
| BR-16 | test-case | `tools/adlc/tests/test_exec_launch.py::test_an_argv_refused_after_the_grant_ends_that_run` | yes |

The engine's grant is tested against the file the harness reads, the user config expanded with the run's own HOME, and each test reads what the fake saw at its launch (LESSON-777). The Claude-only branches (the exit order, `spawn`'s refusals) each have a `none` case beside the file-writing one (LESSON-756).

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No code under `tools/adlc` may compare a harness name (conventions, "Harness adapters are data"); a difference is an adapter field.
- No test writes outside a sandbox `HOME` and `ADLC_HOME` (`conftest.py`'s autouse fixtures). Never read `~/.codex/auth.json`.
- Do not import `harness_probe`: it is pinned to the standard library alone, and its restore is whole-file. The recovery marker's path is `harness_probe`'s; read where it lives from that module's constant by path, or mirror it with a test that holds the two equal.
- The lock is a directory made with `mkdir`, as the id allocator's is, with a symlink pre-check (LESSON-014, LESSON-110).
- Refuse a path holding `"` or `\`, as the probe does.
- Lessons in play: LESSON-777 (test a per-path grant against the key the harness reads), LESSON-787 (a sandboxed HOME does not sandbox everything: no real `launchctl`, no real user config).
