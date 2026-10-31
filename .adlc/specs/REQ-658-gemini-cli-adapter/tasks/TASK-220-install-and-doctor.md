---
id: TASK-220
title: "Install, render-currency and the session record"
status: complete
parent: REQ-658
created: 2026-10-31
updated: 2026-10-31
dependencies: [TASK-219]
repo: adlc-toolkit
---

## Description

Make `adlc harness install --harness antigravity` write the user surfaces and print the permission step, add `skills` to `--surface` and render-currency, SKIP a harness with nothing rendered, and teach `session-record` the name.

## Files to Create/Modify

- `tools/adlc/harness_cli.py` — `skills`, the printed step
- `tools/adlc/harness_doctor.py` — `skip_reason`, user surfaces
- `tools/adlc/checks.py` — `_row_check` uses `skip_reason`
- `partials/session-record.sh`, `partials/session-transcript.sh`, `tools/delegate/extract-chat` — the name, in the one set a test holds equal; no parser
- `tools/delegate/tests/test_extract_chat.py` — the name, as an unproven format
- `tools/adlc/tests/test_session_record_table.py` — a row per adapter still holds
- `tools/adlc/tests/test_harness_antigravity.py` — install and doctor

## Acceptance Criteria

- [ ] `/init --harness antigravity` writes `.agents/hooks.json` and `AGENTS.md` and runs no `agy plugin`
- [ ] Install writes the user surfaces, prints the rule set, and runs no `agy plugin`
- [ ] `render-currency:antigravity` SKIPs with nothing rendered, FAILs naming a deleted file, and its remediation returns it to PASS
- [ ] Removing a `doctor_rows` entry removes its row with no code change

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-4 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_install_runs_no_plugin_command | yes |
| AC-4 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_install_runs_no_plugin_command | yes |
| BR-10 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_render_currency_cycle | yes |
| AC-10 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_render_currency_cycle | yes |
| BR-12 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_no_writes_without_a_command | yes |
| AC-12 | test-case | tools/adlc/tests/test_harness_antigravity.py::test_no_writes_without_a_command | yes |

## Technical Notes

ADR-3, ADR-10. A stale vendored `session-record.sh` records `harness=unknown`, which is benign. The partial's Python text must hold no single quote.
