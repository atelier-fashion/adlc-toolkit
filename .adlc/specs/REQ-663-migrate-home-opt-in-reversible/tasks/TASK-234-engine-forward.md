---
id: TASK-234
title: "The engine: preflight, plan, stage, flip, undo"
status: complete
parent: REQ-663
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-231, TASK-232, TASK-233]
repo: adlc-toolkit
---

## Description

Write `migrate_home.py`: the forward move and a repair, with every BR-2 and BR-3 refusal, the dry run, staging, the flip of ADR-4 and its undo.

## Files to Create/Modify

- `tools/adlc/migrate_home.py` — the engine
- `tools/adlc/tests/migrate_box.py` — the sandbox: clone, home, wheel, stub launchctl, hook
- `tools/adlc/tests/test_migrate_home.py` — AC-1, AC-3, AC-5, AC-6, AC-7, AC-8, AC-10, AC-11 and the leak probe

## Acceptance Criteria

- [ ] Every refusal changes nothing and prints its fix
- [ ] A counter bumped after staging is carried
- [ ] An injected flip failure restores the pre-migration state
- [ ] A second run reports zero actions

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | tools/adlc/tests/test_migrate_home.py::test_forward_moves_exactly_the_owned_state | no |
| BR-2 | test-case | tools/adlc/tests/test_migrate_home.py::test_dir_refusals | yes |
| BR-3 | test-case | tools/adlc/tests/test_migrate_home.py::test_a_stale_project_layer_alone_does_not_refuse | yes |
| BR-3 | test-case | tools/adlc/tests/test_migrate_home.py::test_unverified_baseline_refuses | yes |
| BR-4 | test-case | tools/adlc/tests/test_migrate_home.py::test_counter_bumped_after_staging_is_carried | no |
| BR-4 | test-case | tools/adlc/tests/test_migrate_home.py::test_flip_failure_restores | no |
| BR-5 | test-case | tools/adlc/tests/test_migrate_home.py::test_compat_symlinks_and_no_ledger_link | no |
| BR-6 | test-case | tools/adlc/tests/test_migrate_home.py::test_old_locks_are_tombstones | no |
| BR-7 | test-case | tools/adlc/tests/test_migrate_home.py::test_stamped_files_carry_the_new_home | no |
| BR-10 | test-case | tools/adlc/tests/test_migrate_home.py::test_dry_run_changes_nothing | yes |
| BR-11 | test-case | tools/adlc/tests/test_migrate_home.py::test_repair_and_plain_install_honour_the_home | yes |
| AC-1 | test-case | tools/adlc/tests/test_migrate_home.py::test_forward_with_a_real_venv | no |
| AC-2 | test-case | tools/adlc/tests/test_migrate_home.py::test_forward_with_a_real_venv (sandbox stand-in with a stub launchctl; the AC itself needs a real login session and stays owed to the operator) | no |
| AC-3 | test-case | tools/adlc/tests/test_migrate_home.py::test_doctor_resolves_through_pointer_and_rc | yes |
| AC-5 | test-case | tools/adlc/tests/test_migrate_home.py::test_stale_partial_refuses_and_a_resync_passes | yes |
| AC-6 | test-case | tools/adlc/tests/test_migrate_home.py::test_dry_run_changes_nothing | yes |
| AC-7 | test-case | tools/adlc/tests/test_migrate_home.py::test_a_held_lock_refuses_within_budget | yes |
| AC-8 | test-case | tools/adlc/tests/test_migrate_home.py::test_flip_failure_restores | no |
| AC-10 | test-case | tools/adlc/tests/test_migrate_home.py::test_repair_and_plain_install_honour_the_home | yes |
| AC-11 | test-case | tools/adlc/tests/test_migrate_home.py::test_home_layout_fail_and_remediation | yes |

## Technical Notes

Read the pointer raw: this code runs when the resolver would refuse. Children get a scrubbed `ADLC_HOME`. `chdir` to the clone before the consumer gate. Deletions go through one guard that takes a known relative name under a known root. Python 3.9.
