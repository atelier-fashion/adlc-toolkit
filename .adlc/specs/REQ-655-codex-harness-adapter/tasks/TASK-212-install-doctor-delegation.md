---
id: TASK-212
title: "Install, doctor rows and the delegation installer call"
status: complete
parent: REQ-655
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-211]
repo: adlc-toolkit
---

## Description

Write the user-level surfaces, the explicit `--writable-root`, the doctor rows and the one installer call.

## Files to Create/Modify

- `tools/adlc/harness_cli.py` — `--writable-root`, `--only-if-detected`, the posture message
- `tools/adlc/harness_render.py` — user-scope plans
- `tools/adlc/harness_doctor.py` — `requires`, `unverified` refusal
- `tools/adlc/checks.py` — one check per non-fact row
- `tools/delegate/install.sh` — the call
- `tools/adlc/tests/test_harness_codex.py` — cases

## Acceptance Criteria

- [ ] A sandbox HOME with a fake `codex` gets the routing block and rules once; a second run changes neither
- [ ] Without `codex` on PATH nothing under its home is created and the output says so
- [ ] Doctor rows SKIP without the binary and without delegation

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | tools/adlc/tests/test_harness_codex.py::test_writable_root_is_explicit_union_only | yes |
| BR-8 | test-case | tools/adlc/tests/test_harness_codex.py::test_delegate_installer_routes_codex | yes |
| BR-9 | test-case | tools/adlc/tests/test_harness_codex.py::test_doctor_rows | yes |
| BR-10 | test-case | tools/adlc/tests/test_harness_codex.py::test_doctor_refuses_unverified_gitdir | yes |
| BR-12 | test-case | tools/adlc/tests/test_harness_codex.py | no |
| AC-5 | test-case | tools/adlc/tests/test_harness_codex.py::test_init_config_render | yes |
| AC-8 | test-case | tools/adlc/tests/test_harness_codex.py::test_delegate_installer_routes_codex | yes |
| AC-9 | test-case | tools/adlc/tests/test_harness_codex.py::test_doctor_rows | yes |
| AC-12 | test-case | tools/adlc/tests/test_harness_codex.py | no |

## Technical Notes

ADR-5, ADR-6. `tools/delegate/install.sh` names no path: `grep -n '\.codex'` over it stays empty.
