---
id: TASK-047
title: "Create partials/emit-step-telemetry.sh + companion .md (relocated POSIX helper)"
status: complete
parent: REQ-436
created: 2026-05-16
updated: 2026-05-16
dependencies: []
---

## Description

Create the new sourceable partial holding `_adlc_emit_step_telemetry`, relocated
verbatim-in-behavior from `analyze/SKILL.md` lines 43-65, rewritten POSIX-clean
(no `local`), self-resolving `$KIMI_TOOLS`. Add the companion contract doc.
Implements ADR-1, ADR-2 (item 1), ADR-3.

## Files to Create/Modify

- `partials/emit-step-telemetry.sh` — NEW. `#!/bin/sh`. Header comment in the
  style of `partials/kimi-tools-path.sh` / `partials/kimi-gate.sh`. First
  executable line sources the resolver with the canonical two-level fallback:
  `. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh`.
  Then define `_adlc_emit_step_telemetry()` with the exact logic of current
  `analyze/SKILL.md` lines 43-65, substituting `local`-declared names with
  `_aest_`-prefixed plain assignments (`_aest_step`, `_aest_duration_ms`,
  `_aest_mode`, `_aest_reason`, `_aest_gate_result`). Preserve every branch, the
  `"$KIMI_TOOLS"/skill-flag.sh clear` ordering/count, the `duration_ms`
  arithmetic, and the final `"$KIMI_TOOLS"/emit-telemetry.sh analyze "$_aest_step"
  unknown "$_aest_gate_result" "$_aest_mode" "$_aest_reason" "$_aest_duration_ms"`.
- `partials/emit-step-telemetry.md` — NEW companion. Document: `$1` step-label
  arg; caller-env vars read (`start_s`, `ASK_KIMI_INVOKED`, `KIMI_EXIT`, `flag`,
  `ADLC_KIMI_GATE_REASON`); that it self-sources `kimi-tools-path.sh`; the exact
  emitted record (`skill=analyze`, `step`, `req=unknown`, `gate_result`, `mode`,
  `reason`, `duration_ms`); the BR-4 telemetry-never-blocks invariant
  (LESSON-008); and the call-site protocol — source with the two-level fallback
  **in the same fenced block as the invocation**, never define-here-call-there.

## Acceptance Criteria

- [ ] `partials/emit-step-telemetry.sh` starts with `#!/bin/sh`; `grep -c '_adlc_emit_step_telemetry() {' partials/emit-step-telemetry.sh` == 1.
- [ ] `grep -nE '(^|;|&&|\|\||\bthen\b|\bdo\b|\{)[[:space:]]*local[[:space:]]' partials/emit-step-telemetry.sh` returns nothing (no `local`).
- [ ] The partial sources `kimi-tools-path.sh` with the exact two-level fallback string before the function definition.
- [ ] `sh -n partials/emit-step-telemetry.sh` (POSIX syntax check) passes; no bashisms (no `[[`, `local`, `function` keyword, arrays).
- [ ] `partials/emit-step-telemetry.md` exists and documents all five caller-env vars, the argument, the emitted record, and the same-fenced-block call protocol.
- [ ] The emitted `emit-telemetry.sh` argv and the `skill-flag.sh clear` sequence are byte-identical in behavior to current `analyze/SKILL.md` lines 43-65 for all four modes (verified behaviorally in TASK-050 AC-7 harness).

## Technical Notes

- Source of truth for the body: post-REQ-433 `analyze/SKILL.md` lines 41-66
  (read it; do not reconstruct from memory).
- `$KIMI_TOOLS` must be available to the function body — sourcing
  `kimi-tools-path.sh` at the top of the partial guarantees it (it `export`s a
  defensive `tools/kimi` default, so telemetry never blocks — LESSON-008).
- POSIX only (LESSON-012 #5, LESSON-013): `.` not `source`; no `local`; no `[[`.
- Do NOT change the `emit-telemetry.sh` argument order or add/remove a
  `skill-flag.sh clear` call — BR-4 / AC-7 require byte-equivalent telemetry.
