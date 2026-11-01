---
id: TASK-236
title: "Migrated-layout fixtures in the shell harness and the lint"
status: complete
parent: REQ-663
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-234]
repo: adlc-toolkit
---

## Description

Prove allocation on a migrated sandbox under every shell, from a current copy and from the frozen pre-REQ-654 copy, and show the literal lint fires on migration code.

## Files to Create/Modify

- `partials/tests/migrate-home.test.sh` — AC-4 under `$ADLC_TEST_SHELL`
- `partials/tests/fixtures/id-alloc-pre-req-654.sh` — byte-exact copy of the pre-REQ-654 allocator
- `partials/tests/run.sh` — register the harness
- `tools/lint-skills/tests/test_adlc_home_lint.py` — the check fires on a literal in migration code

## Acceptance Criteria

- [ ] A current copy allocates and fast-forwards the migrated counter, leaving no directory at the old lock path
- [ ] The stale copy aborts within six seconds, allocates nothing, and leaves the counter and its symlink alone

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | partials/tests/migrate-home.test.sh::stale_copy_fails_loud | no |
| BR-6 | test-case | partials/tests/migrate-home.test.sh::stale_copy_fails_loud | no |
| BR-13 | test-case | partials/tests/run.sh under bash, zsh, /bin/sh and dash | yes |
| BR-15 | test-case | partials/tests/migrate-home.test.sh::current_copy_allocates | yes |
| BR-15 | test-case | tools/lint-skills/tests/test_adlc_home_lint.py::test_fires_on_migration_code | yes |
| AC-4 | test-case | partials/tests/migrate-home.test.sh::current_copy_allocates | yes |
| AC-12 | test-case | partials/tests/run.sh; pytest tools/adlc/tests tools/lint-skills/tests; tools/lint-skills/check.sh | yes |

## Technical Notes

The harness keeps its sandbox out of the real home by construction: explicit `HOME`, `ADLC_REPOS_ROOT` and a stub `launchctl` first on `PATH`. A failing case must not leave a process running.
