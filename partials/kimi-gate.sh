#!/bin/sh
# Back-compat alias (REQ-515 ADR-5) for delegate-gate.sh.
#
# The canonical, provider-agnostic predicate is partials/delegate-gate.sh
# (adlc_delegate_gate_check + ADLC_DELEGATE_GATE_REASON). This file preserves the
# legacy surface so every existing SKILL.md source-line
#   . .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh
# keeps working byte-identically: it defines adlc_kimi_gate_check() with the
# IDENTICAL 0/1/2 contract and the legacy ADLC_KIMI_GATE_REASON values
# (ok / disabled-via-env / no-binary).
#
# The predicate logic is INLINED here rather than sourced from delegate-gate.sh
# because a partial sourced by absolute path cannot reliably locate a sibling
# ($0 is the caller's path when sourced). Both files implement the same checks;
# keep them in sync. The BR-11 "not-opted-in" condition maps onto the legacy
# "disabled-via-env" reason so existing callers' disabled branch (which runs the
# fallback) fires correctly on a fresh, un-opted-in install.
#
# Return-code contract (UNCHANGED from the historical kimi-gate.sh):
#   0 — delegated   1 — disabled   2 — unavailable
#
# No `set -eu` here — return codes ARE the contract.

# Defensive default mirrors the historical kimi-gate.sh contract.
export ADLC_KIMI_GATE_REASON="unset"

# Opt-in (BR-11): pure-shell fast paths first; config probe last (only when a
# config file is present). Echoes "1" if opted in, "" otherwise.
_adlc_kimi_opted_in() {
  if [ "${ADLC_DELEGATE_ENABLED:-}" = "1" ]; then echo 1; return 0; fi
  if [ -n "${MOONSHOT_API_KEY:-}" ] || [ -n "${KIMI_API_KEY:-}" ]; then echo 1; return 0; fi
  _cfg="${ADLC_CONFIG:-${HOME:-}/.claude/adlc/config.yml}"
  if [ -n "$_cfg" ] && [ -f "$_cfg" ] && command -v adlc-read >/dev/null 2>&1; then
    if [ "$(adlc-read --print-enabled 2>/dev/null)" = "1" ]; then echo 1; return 0; fi
  fi
  echo ""
}

adlc_kimi_gate_check() {
  # Probe adlc-read (the canonical CLI); the legacy ask-kimi shim also lands on
  # PATH and resolves, but adlc-read is the contractual probe.
  if ! command -v adlc-read >/dev/null 2>&1; then
    export ADLC_KIMI_GATE_REASON="no-binary"
    return 2
  fi
  if [ "${ADLC_DISABLE_DELEGATE:-0}" = "1" ] || [ "${ADLC_DISABLE_KIMI:-0}" = "1" ]; then
    export ADLC_KIMI_GATE_REASON="disabled-via-env"
    return 1
  fi
  if [ -z "$(_adlc_kimi_opted_in)" ]; then
    # BR-11 fresh-install posture: surfaced as the legacy disabled reason so the
    # caller's existing disabled branch runs the fallback.
    export ADLC_KIMI_GATE_REASON="disabled-via-env"
    return 1
  fi
  export ADLC_KIMI_GATE_REASON="ok"
  return 0
}
