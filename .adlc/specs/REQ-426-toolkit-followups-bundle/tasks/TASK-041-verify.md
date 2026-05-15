---
id: TASK-041
title: "End-to-end verification for REQ-426 bundle"
status: complete
parent: REQ-426
created: 2026-05-15
updated: 2026-05-15
dependencies: [TASK-037, TASK-038, TASK-039, TASK-040]
---

## Description

Verification gate for REQ-426. Runs after all four parallel tasks land.

## Files to Create/Modify

- `.adlc/specs/REQ-426-toolkit-followups-bundle/verification.md` — NEW.
  Captures the test plan, commands, outputs, pass/fail.

(No production code changes — pure verification.)

## Acceptance Criteria

- [ ] `pytest tools/kimi/tests/ -v` reports 53/53 passing (46 pre-existing
      + 7 new partials tests).
- [ ] install.sh hash-mismatch test (tamper claude-md-routing.txt without
      updating .sha256, run install.sh, verify exit non-zero + CLAUDE.md
      unchanged).
- [ ] install.sh happy-path test (clean state, run install.sh, verify
      idempotent marker-guarded append).
- [ ] `grep -l 'reason="disabled-via-env"' */SKILL.md` returns empty
      (BR-2 enforcement: no remaining inline reason-string derivation).
- [ ] `/template-drift` invoked against a sandbox with partial drift
      reports `stale` for the differing partial.
- [ ] `/template-drift` against fully-synced sandbox reports `synced`.
- [ ] BR-7: no SKILL.md regressed to inline gate predicate OR inline
      ethos macro. Verify with REQ-416's grep checks:
      - `grep -l "cat .adlc/ETHOS.md" */SKILL.md` empty
      - `grep -l 'command -v ask-kimi.*ADLC_DISABLE_KIMI' */SKILL.md` empty

## Technical Notes

- Run pytest from the worktree root with the venv that
  `tools/kimi/install.sh` provisions: `~/.claude/kimi-venv/bin/pytest`.
- For the install.sh tests, use a sandbox HOME so the real
  `~/.claude/CLAUDE.md` is not touched.
- Document any environmental skips (e.g., `test_kimi_gate_available`
  skipped because `ask-kimi` not on PATH in this sandbox) explicitly in
  verification.md.
