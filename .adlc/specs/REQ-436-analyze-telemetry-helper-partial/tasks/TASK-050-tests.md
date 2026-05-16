---
id: TASK-050
title: "Tests: realistic post-change fixtures, posix-fence/cross-fence-fn/root-skip cases, AC-7 telemetry-equivalence harness"
status: complete
parent: REQ-436
created: 2026-05-16
updated: 2026-05-16
dependencies: [TASK-047, TASK-049]
---

## Description

Add/extend the test suites so every guard from TASK-049 has a realistic
post-change test (LESSON-019 #3) and the relocated helper's telemetry is proven
byte-equivalent (AC-7). Implements ADR-8.

## Files to Create/Modify

- `tools/lint-skills/tests/fixtures/`:
  - NEW `canonical-via-partial-skill.md` — contains `ADLC_DISABLE_KIMI` + L1/L4/L5
    inline, **not** L2/L3.
  - NEW `local-in-sh-fence.md` — `local x=1` in a ```sh fence AND the same in a
    ```bash fence (to assert the exemption in one fixture).
  - NEW `cross-fence-fn.md` — function defined in one fence, called in another.
  - (Reuse existing `clean`, `missing-canonical`, `kimi-gate-ok`,
    `missing-resolver-source`.)
- `tools/lint-skills/tests/test_check.py`:
  - Extend `_stage` (or add a helper) to optionally also stage a
    `partials/emit-step-telemetry.sh` next to the fixture root.
  - NEW `test_canonical_satisfied_via_partial` — stage `canonical-via-partial-skill`
    + a partial supplying L2/L3 → returncode 0, no `canonical-helper`.
  - NEW `test_posix_fence_flags_sh_not_bash` — `local-in-sh-fence` → exactly one
    `posix-fence` finding, on the ```sh occurrence's line; assert the ```bash
    line is NOT flagged.
  - NEW `test_cross_fence_fn_flagged` + a same-fence control asserting clean.
  - NEW `test_root_under_worktrees_still_scanned` — stage a corrupt SKILL.md at
    `tmp/.worktrees/x/` and run `--root tmp/.worktrees/x`; assert it IS scanned
    (finding present) — LESSON-019 #2 regression.
  - Verify existing `test_missing_canonical` (==5), `test_kimi_gate_happy_path_is_clean`,
    `test_missing_only_resolver_source` (==1) still pass unchanged (no partials
    staged in those → no behavior change).
- `tools/kimi/tests/` (or `tools/lint-skills/tests/`): NEW
  `test_emit_step_telemetry_equivalence.py` — AC-7 harness: for each mode
  {fallback, ghost-skip, delegated, api-error}, create a tmp `$KIMI_TOOLS` dir
  with stub `skill-flag.sh` + `emit-telemetry.sh` that append `"$@"` to a capture
  file; set the caller-env vars to drive that mode; `sh -c '. partials/emit-step-telemetry.sh;
  _adlc_emit_step_telemetry Step-1.5'`; assert the captured `emit-telemetry.sh`
  argv and the `skill-flag.sh clear` invocation sequence match the documented
  pre-change behavior for that mode.

## Acceptance Criteria

- [ ] `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/ tools/lint-skills/tests/ -q` exits 0 with all new + existing cases passing.
- [ ] `test_canonical_satisfied_via_partial` proves the post-REQ-436 shape (moved literals in partial) is clean.
- [ ] `test_posix_fence_flags_sh_not_bash` asserts both the positive (sh flagged) and the exemption (bash not flagged) with the exact finding line.
- [ ] `test_cross_fence_fn_flagged` + same-fence control both assert correctly.
- [ ] `test_root_under_worktrees_still_scanned` fails on pre-ADR-5 code and passes after.
- [ ] The AC-7 harness asserts byte-equivalent `emit-telemetry.sh` argv for all four modes; POSIX `sh` only.

## Technical Notes

- Mirror existing test style: subprocess against staged tmp roots; compute
  expected lines from fixtures (don't hardcode).
- AC-7 harness must be POSIX `sh` (LESSON-013) — no bash-only test scaffolding.
- Run the venv pytest exactly as the spec mandates:
  `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/ tools/lint-skills/tests/ -q`.
- Per LESSON-019 #4: when Phase 5 verifies AC-5/AC-6, the orchestrator must
  independently confirm the linter scanned a non-empty file set (not trust a
  bare exit 0).
