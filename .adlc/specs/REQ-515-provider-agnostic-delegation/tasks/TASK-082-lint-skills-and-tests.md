---
id: TASK-082
title: "Update lint-skills checks/fixtures + pytest suite (rename + new coverage)"
status: draft
parent: REQ-515
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-079, TASK-081]
---

## Description

Make the linter follow the new indirection (BR-4, ADR-9) and update/extend the
pytest suite to cover the new entrypoints and the new behavior (BR-2/BR-3/BR-1/
BR-11). This is the verification backbone of the REQ.

## Files to Create/Modify

- `tools/lint-skills/check.py` — `KIMI_GATE_ANCHOR` accepts `ADLC_DISABLE_KIMI`
  OR `ADLC_DISABLE_DELEGATE`; each `CANONICAL_LITERALS` source-line is satisfied by
  EITHER the legacy `kimi-gate.sh`/`kimi-tools-path.sh` spelling OR the new
  `delegate-gate.sh`/`delegate-tools-path.sh` spelling.
- `tools/lint-skills/tests/fixtures/*` — update/add fixtures for new spellings;
  keep an old-spelling fixture passing.
- `tools/lint-skills/tests/test_check.py` — assert both spellings pass and a
  SKILL.md mentioning the disable anchor with no telemetry wiring still fails.
- `tools/lint-skills/README.md` — document the dual-anchor / dual-literal rule.
- `tools/kimi/tests/test_common.py` (or new `test_resolve_provider.py`) — cover
  precedence (BR-2), config parse, key-in-config refusal (BR-3), opt-in posture
  (BR-11), Moonshot-default equivalence.
- `tools/kimi/tests/test_shim_equivalence.py` (new) — `ask-kimi`/`kimi-write`
  shim `--help`/`--dry-run` equal `adlc-read`/`adlc-write` (BR-1).
- `tools/kimi/tests/test_partials.py` — add/adjust for `delegate-gate.sh` return
  codes + reasons and the legacy wrapper mapping; cover both disable flags.
- Any test importing the old CLI module paths — update to the new filenames.

## Acceptance Criteria

- [ ] `lint-skills` passes on the full corpus after the rename (AC: no live file
      greps for `ask-kimi`/`kimi-write` except shims/wrappers/labeled back-compat).
- [ ] Full `pytest` under `tools/kimi/tests/` passes (run with the kimi-venv).
- [ ] New tests cover precedence order, key-in-config refusal, shim equivalence,
      and both opt-in postures (fresh-install disabled, env-only opt-in).
- [ ] `check-delegation.sh` processes a pre-change and a post-change telemetry
      record identically (a fixture record asserts this).
- [ ] Linux/bash parity: the partial tests and gate use no GNU-only constructs;
      document the manual-run command if CI cannot run them here.

## Technical Notes

- Run pytest via `~/.claude/kimi-venv/bin/python -m pytest tools/kimi/tests -q`
  from the worktree (the venv has pytest pinned). If the venv is absent in this
  environment, use the system `python3 -m pytest` after `pip install pytest` into
  a scratch venv, or document the exact command for CI. Do not skip the suite.
- The lint dual-literal rule: refactor `check_canonical` so each logical literal
  is a tuple of acceptable spellings; satisfied if ANY spelling is present in text
  or (when the telemetry partial is sourced) in the partials blob.
