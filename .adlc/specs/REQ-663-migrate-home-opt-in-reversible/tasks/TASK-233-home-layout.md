---
id: TASK-233
title: "The layout module and the home-layout doctor check"
status: complete
parent: REQ-663
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-230]
repo: adlc-toolkit
---

## Description

Write `home_layout.py`, the one statement of what a migrated machine looks like, register `home-layout`, and let doctor report a broken pointer or a conflict instead of exiting before any check runs.

## Files to Create/Modify

- `tools/adlc/home_layout.py` — inventory constants, `machine_facts`, `traced_home`, `inspect`, rc helpers
- `tools/adlc/checks.py` — `check_home_layout`, registry entry, `_COUNTERS` from the module
- `tools/adlc/doctor.py` — `home-layout` alone on a pointer problem; `home=` on the profile line
- `tools/adlc/tests/test_home_layout.py` — the rc edit, the pointer reads and the module's dependency rule; the check's PASS, SKIP and every FAIL run end to end in `test_migrate_home.py`

## Acceptance Criteria

- [ ] SKIP on an unmigrated machine and on a REQ-654 override with no pointer
- [ ] PASS on a built layout
- [ ] Each spec item produces a FAIL naming it
- [ ] A dangling pointer and a conflict are reported as `home-layout` with exit 1

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-12 | test-case | tools/adlc/tests/test_migrate_home.py::test_home_layout_fail_and_remediation | yes |
| BR-12 | test-case | tools/adlc/tests/test_migrate_home.py::test_home_layout_skips_on_a_req_654_override | yes |
| AC-3 | test-case | tools/adlc/tests/test_migrate_home.py::test_a_conflicting_variable_is_refused_by_name | yes |
| BR-13 | test-case | tools/adlc/tests/test_home_layout.py::test_module_imports_only_stdlib | no |

## Technical Notes

No literal `.claude` in this module: the default comes from `adlc_home.default_home()`. It reads, it never writes. It may not import `_machine_config` (LESSON-395).
