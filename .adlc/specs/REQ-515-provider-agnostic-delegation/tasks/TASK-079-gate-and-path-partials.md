---
id: TASK-079
title: "Generalized delegate-gate.sh / delegate-tools-path.sh + legacy wrappers"
status: draft
parent: REQ-515
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-078]
---

## Description

Implement BR-4 + BR-11 at the gate layer (ADR-5). New canonical partials with the
generalized predicate; old partials become thin source-through wrappers so every
existing SKILL.md source-line keeps working.

## Files to Create/Modify

- `partials/delegate-gate.sh` (new) — `adlc_delegate_gate_check()`, 0/1/2 contract,
  exports `ADLC_DELEGATE_GATE_REASON`. Gates on `command -v adlc-read`,
  `ADLC_DISABLE_DELEGATE`/`ADLC_DISABLE_KIMI`, and the BR-11 opt-in signals.
- `partials/kimi-gate.sh` (rewrite) — sources `delegate-gate.sh`, defines
  `adlc_kimi_gate_check()` mapping the new reason onto legacy
  `ADLC_KIMI_GATE_REASON` (`ok`/`disabled-via-env`/`no-binary`).
- `partials/delegate-tools-path.sh` (new) — resolves `$DELEGATE_TOOLS` (and keeps
  exporting `$KIMI_TOOLS` for back-compat) to the telemetry-exec dir.
- `partials/kimi-tools-path.sh` (rewrite) — source-through wrapper.
- `partials/kimi-gate.md` (doc) — neutralize, document the wrapper.

## Acceptance Criteria

- [ ] `adlc_delegate_gate_check` returns 0 delegated / 1 disabled / 2 unavailable;
      exports a reason on every path.
- [ ] `ADLC_DISABLE_DELEGATE=1` and legacy `ADLC_DISABLE_KIMI=1` both yield the
      disabled path (return 1).
- [ ] Opt-in (BR-11): with no opt-in signal the gate returns the disabled path;
      with `delegate.enabled:true` / `ADLC_DELEGATE_ENABLED=1` / legacy key in env
      it returns delegated (if available + not disabled).
- [ ] `adlc_kimi_gate_check` (via wrapper) preserves the exact legacy 0/1/2 return
      codes AND `ADLC_KIMI_GATE_REASON` values for existing SKILL.md callers.
- [ ] `$KIMI_TOOLS` still resolves identically via the wrapper (no emit call site
      changes).
- [ ] All shell is POSIX/BSD/zsh-safe: no `set -eu` in the predicate, no bashisms,
      no `\b` in grep, no bare `$<digit>`, no unmatched globs (BR-8).

## Technical Notes

- Mirror the existing defensive-default export pattern (`=unset`) on both reasons.
- The opt-in check must NOT parse YAML in shell (ADR-3): use the env signals
  (`ADLC_DELEGATE_ENABLED`, legacy keys) directly; for the config-`enabled:true`
  signal, probe via the resolved tooling (a `adlc-read --print-enabled`-style
  cheap check) OR keep config-opt-in resolution in Python and have the gate trust
  only env signals + key presence — pick the simplest that satisfies BR-11 ACs
  without shell YAML. Document the choice in `kimi-gate.md`.
