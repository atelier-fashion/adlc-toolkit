---
id: TASK-006
title: "Rename/update delegation tests, add BR-1 brand-creep guard, CHANGELOG + context docs"
status: complete
parent: REQ-522
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-002, TASK-004, TASK-005]
---

## Description

Update the test suite to the renamed surface, add the BR-1 brand-creep guard test
(ADR-8), verify the telemetry fix under both executor shells (BR-6), and land the
CHANGELOG migration table + context-doc de-brand.

## Files to Create/Modify

- `tools/delegate/tests/test_kimi_tools_path.py` →
  `tools/delegate/tests/test_delegate_tools_path.py` — `git mv`; assert
  `delegate-tools-path.sh` resolves `tools/delegate` and exports `DELEGATE_TOOLS`
  (and that `kimi-tools-path.sh` / `KIMI_TOOLS` are gone).
- `tools/delegate/tests/test_emit_step_telemetry_equivalence.py` — update to drive the
  flag-file-derived `_adlc_emit_step_telemetry <skill> <step>`; assert under BOTH
  `zsh -c` and `bash -c`: invoked+exit0+flag-cleared → `mode=delegated,gate=pass,
  duration_ms>0`; invoked+flag-present → `ghost-skip`; no-invoke → `fallback,fail`; and
  NO flag file remains after (AC-2, AC-3).
- `tools/delegate/tests/test_partials.py`, `test_shim_equivalence.py`,
  `test_resolve_provider.py`, `test_common.py`, `test_cli_warn.py`, `test_telemetry.py`,
  `test_extract_chat.py`, `conftest.py` — update path/var references; `test_cli_warn.py`
  and `test_shim_equivalence.py` lose the `ask-kimi`/`kimi-write` shim cases (shims
  removed); `test_common.py`/`test_cli_warn.py` drop `KIMI_MODEL`/`KIMI_NO_WARN`
  expectations, keep `KIMI_API_KEY`/`MOONSHOT_API_KEY` continuity assertions.
- `tools/delegate/tests/test_no_kimi_brand.py` — NEW (ADR-8, AC-1). `grep -ri kimi`
  over the distribution surface; assert every hit is in the BR-1 allow-list
  (provider-preset data, the key-env continuity reads, the `kimi-delegation:start`
  legacy anchor in install.sh). Fail on any other hit. `.adlc/` is excluded (historical).
- `tools/delegate/check-delegation.sh` — confirm it still parses the unchanged schema
  (no code change expected; covered by an existing/updated test reading a pre-REQ
  fixture line — AC-5).
- `CHANGELOG.md` — add the REQ-522 entry with the one-line migration table
  (old → new): `tools/kimi/`→`tools/delegate/`, `kimi-gate.sh`→`delegate-gate.sh`,
  `kimi-tools-path.sh`→`delegate-tools-path.sh`, `KIMI_TOOLS`→`DELEGATE_TOOLS`,
  `ask-kimi`/`kimi-write`→removed (use `adlc-read`/`adlc-write`), `ADLC_DISABLE_KIMI`
  →`ADLC_DISABLE_DELEGATE`, `KIMI_MODEL`→`ADLC_DELEGATE_MODEL`, `KIMI_NO_WARN`→
  `ADLC_DELEGATE_NO_WARN`, `com.adlc-toolkit.kimi-setenv`→`...delegate-setenv`.
- `README.md` — de-brand the 2 references.
- `.adlc/context/conventions.md`, `.adlc/context/architecture.md` — de-brand the
  delegation-pattern prose (tools/kimi, kimi-gate.sh, "Kimi pre-pass", KIMI_TOOLS) to
  the new identifiers. (Context docs are not BR-1 distribution surface but document the
  renamed pattern; keep them accurate.)

## Acceptance Criteria

- [ ] All renamed tests pass; `pytest tools/delegate/tests` is green.
- [ ] `test_no_kimi_brand.py` passes and FAILS if a Kimi-named identifier is
      reintroduced (verified by a temporary planted hit during development).
- [ ] The telemetry equivalence test asserts the `delegated` AND `ghost-skip` branches
      under both `zsh -c` and `bash -c`, and no leftover flag file.
- [ ] `check-delegation.sh` parses a pre-REQ telemetry log line (AC-5).
- [ ] CHANGELOG migration table lists every old→new rename / removal.
- [ ] `grep -ri kimi` over the distribution surface matches only the BR-1 allow-list.

## Technical Notes

- Run the full `pytest` suite from the repo root; the renamed dir means import paths
  may need `conftest.py` path fixes.
- The brand-guard test is the AC-1 "check added as a test/lint rule so the brand cannot
  creep back" deliverable.
- Depends on TASK-002 (telemetry partial), TASK-004 (installer/_common), TASK-005 (lint)
  all landing so the suite reflects the final shape.
