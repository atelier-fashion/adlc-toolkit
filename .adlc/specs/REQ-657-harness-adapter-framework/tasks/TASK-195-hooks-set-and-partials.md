---
id: TASK-195
title: "hooks.yml, hooks render, ethos-inject and session-record stub partials"
status: complete
parent: REQ-657
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-194]
repo: adlc-toolkit
---

## Description

The canonical hook set, its per-harness render, the two partials the hook commands
source, and their cross-shell harness (BR-10, BR-16).

## Files to Create/Modify

- `templates/hooks.yml` — ethos-inject, session-record
- `partials/ethos-inject.sh` — `adlc_ethos_inject`
- `partials/session-record.sh` — stub `adlc_session_record` (REQ-660 replaces it)
- `tools/adlc/harness_render.py` — hooks render
- `partials/tests/hooks.test.sh` — the rendered commands under each shell
- `partials/tests/run.sh` — harness list gains hooks.test.sh

## Acceptance Criteria

- [ ] The claude render carries SessionStart with and without the compact matcher, timeouts in seconds
- [ ] The fake (ms) render writes 10000 for timeout_s 10
- [ ] Rendered ethos-inject prints ETHOS under sh/bash/zsh/dash and nothing without it; session-record exits 0 silently with the partial absent

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-10 | test-case | `partials/tests/hooks.test.sh::case_ethos_inject_prints` | yes |
| BR-16 | test-case | `partials/tests/hooks.test.sh::case_session_record_absent_partial` | yes |
| AC-8 | test-case | `tools/adlc/tests/test_harness_framework.py::test_hooks_render` | yes |
| AC-14 | test-case | `partials/tests/run.sh` | yes |

## Technical Notes

ADR-10. Hook commands are never loaded by `lane_check.py`.
