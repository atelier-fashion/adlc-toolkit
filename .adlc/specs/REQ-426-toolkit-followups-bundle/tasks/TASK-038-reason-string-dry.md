---
id: TASK-038
title: "DRY Kimi gate reason-string via ADLC_KIMI_GATE_REASON"
status: complete
parent: REQ-426
created: 2026-05-15
updated: 2026-05-15
dependencies: []
---

## Description

Resolve REQ-426 BR-2 (ADR-2). The post-gate reason-string derivation (`if
disabled then "disabled-via-env" else "no-binary"`) duplicated across 4
delegating skills becomes a single export from `partials/kimi-gate.sh`.

## Files to Create/Modify

- `partials/kimi-gate.sh` — MODIFIED. `adlc_kimi_gate_check` now sets and
  exports `ADLC_KIMI_GATE_REASON` to one of: `"ok"` (return 0),
  `"disabled-via-env"` (return 1), `"no-binary"` (return 2). Behavior:
  ```sh
  adlc_kimi_gate_check() {
    if ! command -v ask-kimi >/dev/null 2>&1; then
      export ADLC_KIMI_GATE_REASON="no-binary"
      return 2
    fi
    if [ "${ADLC_DISABLE_KIMI:-0}" = "1" ]; then
      export ADLC_KIMI_GATE_REASON="disabled-via-env"
      return 1
    fi
    export ADLC_KIMI_GATE_REASON="ok"
    return 0
  }
  ```
- `partials/kimi-gate.md` — MODIFIED. Document `ADLC_KIMI_GATE_REASON` as
  part of the contract: when callers need to know WHY the gate denied,
  they read this var rather than re-interrogating `ADLC_DISABLE_KIMI` and
  `command -v ask-kimi`. Update the protocol example to show the var read.
- `analyze/SKILL.md` — MODIFIED at the 2 telemetry blocks (~lines 90, 165).
  Replace the inline `if [ "${ADLC_DISABLE_KIMI:-0}" = "1" ]; then reason="disabled-via-env"; else reason="no-binary"; fi`
  with `reason="$ADLC_KIMI_GATE_REASON"`. Same edit for both blocks.
- `proceed/SKILL.md` — MODIFIED at Phase 5 telemetry block (~line 379).
  Same replacement.
- `spec/SKILL.md` — MODIFIED at the telemetry block (~line 168). Same
  replacement.
- `wrapup/SKILL.md` — MODIFIED at the telemetry block (~line 288). Same
  replacement.

## Acceptance Criteria

- [ ] `partials/kimi-gate.sh` exports `ADLC_KIMI_GATE_REASON` set to one
      of `"ok"` / `"disabled-via-env"` / `"no-binary"` on every code path.
- [ ] Function-level test: source the partial, invoke
      `adlc_kimi_gate_check`, verify both the return code and
      `$ADLC_KIMI_GATE_REASON` match the expected pair for each of the 3
      cases (covered by TASK-040 tests).
- [ ] No SKILL.md still contains the inline reason-derivation pattern.
      Verify: `grep -l 'reason="disabled-via-env"' */SKILL.md` returns
      empty (or contains only files that read the var, never write it
      directly).
- [ ] `partials/kimi-gate.md` documents the var as part of the contract.
- [ ] Adding a hypothetical fourth gate condition would require editing
      ONLY `partials/kimi-gate.sh` and `partials/kimi-gate.md` — no
      per-skill edits. Architect this mentally and confirm in the PR
      description.
- [ ] REQ-413 pytest suite still passes (BR-8).

## Technical Notes

- `export` is intentional (not just assignment) so the variable is visible
  to child processes the skill spawns. Most call sites read it in the same
  shell, but exporting is the safer default — a child `ask-kimi` invocation
  could read it for self-documentation if useful.
- The reason var must be set BEFORE the function returns, even in the
  return-2 (no-binary) case where `command -v` short-circuits. Verify the
  code path order matches the function template above.
- No backward-compat shim needed — REQ-416 already DRY-ed the gate
  predicate, so any caller reaching the post-gate telemetry block already
  knows it's running against the new partial.
