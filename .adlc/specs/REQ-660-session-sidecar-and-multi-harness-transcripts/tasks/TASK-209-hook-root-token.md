---
id: TASK-209
title: "Make the rendered hooks run: the unbraced plugin root"
status: complete
parent: REQ-660
created: 2026-10-30
updated: 2026-10-30
dependencies: [TASK-204]
repo: adlc-toolkit
---

## Description

Added in Phase 4. The real binary never ran a hook carrying the braced plugin-root
token, so AC-1 could not pass (BR-8, ADR-8).

## Files to Create/Modify

- `templates/hooks.yml` — the root line unbraced, in both hooks
- `harness/claude/rendered/settings.json` — re-rendered golden
- `.claude/settings.json` — re-rendered
- `tools/lint-skills/check.py` — `HOOK_ROOT_LINE`, its exception, the `unguarded-source` arm
- `tools/lint-skills/tests/test_harness_lints.py` — the refusal and the real tree
- `tools/lint-skills/tests/test_toolkit_path.py` — the pinned exception set
- `tools/lint-skills/README.md` — document the arm

## Acceptance Criteria

- [x] `claude -p` with the committed render writes a full sidecar under a throwaway `HOME`
- [x] `--resume` keeps `started_at`
- [x] `adlc harness render --check` passes
- [x] The lint fails the braced token and passes the real tree

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-8 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_hook_command_must_not_hold_the_braced_plugin_root` | yes |
| AC-1 | test-case | `tools/lint-skills/tests/test_harness_lints.py::test_real_hook_sources_hold_no_braced_plugin_root` | yes |

## Technical Notes

Lessons: LESSON-755, LESSON-747. The live run is recorded in `verification.md` (TASK-208).

## Dependencies

TASK-204
