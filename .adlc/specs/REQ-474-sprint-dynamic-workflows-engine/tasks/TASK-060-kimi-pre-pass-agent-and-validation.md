---
id: TASK-060
title: "kimi-pre-pass agent + Phase-5 wiring + script-side LESSON-008 validation"
status: complete
parent: REQ-474
created: 2026-05-29
updated: 2026-05-30
dependencies: [TASK-058, TASK-056]
---

## Description

Build the **target** Kimi pre-pass: the new per-repo `kimi-pre-pass` leaf agent (I/O), the deterministic script-side citation validation (LESSON-008), and the Phase-5 wiring that feeds advisory candidates to the 5 reviewers. Gated on the TASK-056 (OQ-1) verdict. (ADR-8)

## Files to Create/Modify

- `agents/kimi-pre-pass.md` — CREATE. `model: haiku`, `tools: Bash`. Protocol: source helpers up front, gate, diff+`--name-only` from the worktree, redact (REQ-415 chain), `ask-kimi`, parse → `CANDIDATES`, `emit-telemetry.sh`. Returns the schema; never throws; treats Kimi stdout as untrusted.
- `workflows/adlc-sprint.workflow.js` — MODIFY. Add `validateCitations()` (pure JS) + the per-repo `pipeline(repos, prePass, panel)` stage + `candidates ⇒ invoked` assertion.
- `workflows/schemas.js` — MODIFY only if `CANDIDATES` needs adjustment.

## Acceptance Criteria

- [x] The agent returns `CANDIDATES` (gate/diff/redact/ask-kimi); on gate-fail or non-zero `ask-kimi` it returns the degraded object (empty `candidates`) and never throws.
- [x] `validateCitations()` drops any candidate whose `path` contains `..`, is absent from `changedFiles`, or fails the `^[A-Za-z0-9_./-]+$` check; descriptions are sanitized; nothing dropped is forwarded.
- [x] The script asserts `candidates.length > 0 ⇒ invoked`; a violation is treated as a ghost-skip (rejected + recorded).
- [x] The **reflector receives no** advisory candidates; only the 5 reviewers get their per-dimension slice.
- [x] The agent emits unified telemetry via `emit-telemetry.sh` (`skill=kimi-pre-pass`) so `check-delegation.sh` counts it.
- [x] N/A — TASK-056 (OQ-1) found `ask-kimi` REACHABLE (GO), so the Phase-5 wiring is ON (not flagged off). The agent additionally enforces the OQ-1 key-presence refinement (`[ -n "$MOONSHOT_API_KEY" ]`) and degrades gracefully (candidate-less panel) if gate/key is unavailable at runtime. The agent + `validateCitations` land regardless.

## Technical Notes

- Reuse partials per their confirmed interfaces: `kimi-gate.sh` (source, `adlc_kimi_gate_check`, read `$?` immediately + `ADLC_KIMI_GATE_REASON`), `kimi-tools-path.sh` (source → `$KIMI_TOOLS`), `emit-telemetry.sh` (subprocess, 7 args), per integration-explorer. **Source `kimi-tools-path.sh` first** so `$KIMI_TOOLS` exists on gate-fail/api-error telemetry paths (the cross-block-state bug class — LESSON-020).
- The untrusted surface is Kimi's stdout, NOT the agent; `changedFiles` is trusted git output (LESSON-008, LESSON-010).
- No `skill-flag.sh` dance needed — the script's schema assertion replaces it (ADR-8, LESSON-012).
