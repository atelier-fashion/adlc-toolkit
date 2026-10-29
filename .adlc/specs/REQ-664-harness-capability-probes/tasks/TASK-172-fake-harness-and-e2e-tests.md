---
id: TASK-172
title: "Fake harness and end-to-end probe tests"
status: draft
parent: REQ-664
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-171]
repo: adlc-toolkit
---

## Description

Build the fake harness (ADR-2) and the pytest suites that drive the real CLI
against it on a sandbox `HOME`, `PATH`, `TMPDIR` and `ADLC_HOME`: every verdict
path of every probe for all five profiles, the `--only` merge rules, redaction,
the `~` rewrite, the result schema, cleanup, the recovery contract (SIGTERM
restores, SIGKILL leaves the marker, `--recover` from outside a repo with no
binary), fresh state per launch, allow necessity and the witness, the final
message and nonce rules, and the shell-safety of the fake and of every fixture
shell the probe writes.

## Files to Create/Modify

- `tools/adlc/tests/fake_harness/fake-harness` — new: POSIX-sh wrapper
- `tools/adlc/tests/fake_harness/fake_harness_impl.py` — new: the fake's logic
- `tools/adlc/tests/probe_helpers.py` — new: sandbox builder and run helper
- `tools/adlc/tests/test_harness_probe_cli.py` — new: AC-1, AC-14 launch-count order
- `tools/adlc/tests/test_harness_probe_e2e.py` — new: AC-2, AC-3, AC-5–AC-10, AC-15–AC-17
- `tools/adlc/tests/test_harness_probe_recovery.py` — new: AC-4
- `tools/adlc/tests/test_harness_probe_shells.py` — new: AC-12 shell matrix over the fake and the fixtures

## Acceptance Criteria

- [ ] scenarios `perform`, `refuse`, `refuse-silent`, `exit3`, `hang`, `runs-all`, `no-witness`, `abort-on-deny` produce the AC-2/AC-16/AC-17 verdicts on every applicable profile
- [ ] AC-3 before/after listings match except the allowed files
- [ ] AC-4's crash, refusal, `--recover`, surgical and `created_dirs` cases pass
- [ ] the fake and the fixture shell pass `-n` and run under `/bin/bash`, `zsh` and `/bin/sh`
- [ ] `pytest tools/adlc/tests` passes

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-14 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_perform_all_pass` | yes |
| AC-1 | test-case | `tools/adlc/tests/test_harness_probe_cli.py::test_dry_run_lists_launches_and_user_files` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_scenario_verdicts` | yes |
| AC-3 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_cleanup_leaves_home_and_temp_unchanged` | no |
| AC-4 | test-case | `tools/adlc/tests/test_harness_probe_recovery.py::test_marker_refuses_then_recover` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_git_write_decided_from_remote` | no |
| AC-6 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_ask_tier_deny_variants` | yes |
| AC-7 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_trust_and_fence_sub_results` | no |
| AC-8 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_stdin_context_and_args` | no |
| AC-9 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_transcript_fixture_redacted` | no |
| AC-10 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_only_merge_rules` | no |
| AC-12 | test-case | `tools/adlc/tests/test_harness_probe_shells.py::test_fake_and_fixtures_under_each_shell` | no |
| AC-14 | test-case | `tools/adlc/tests/test_harness_probe_cli.py::test_launch_count_precedes_first_launch` | no |
| AC-15 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_fresh_state_per_launch` | yes |
| AC-16 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_allow_necessity_and_witness` | yes |
| AC-17 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_final_message_rules` | yes |

## Technical Notes

The fake never sleeps for `sleep 125` (it runs the command after it); `hang`
sleeps until killed and records its pid so the test can assert it is gone. The
in-process cases (a profile with no extractor, a pre-seeded sentinel) import
`harness_probe` and monkeypatch, with `tempfile.tempdir` pointed at the sandbox.
The fake wrapper uses no `local`, no `[[` and no `case` inside `$( )`
(LESSON-582).
