#!/bin/sh
# Shared Kimi delegation gate predicate (REQ-416 BR-3, ADR-2).
#
# Sourceable POSIX shell function. Each call site reads $? IMMEDIATELY into a
# local variable (gate=$?) before any other command, because $? is clobbered
# by every subsequent command. See partials/kimi-gate.md for the full protocol.
#
# Return-code contract:
#   0 — delegated:    ask-kimi is on PATH AND ADLC_DISABLE_KIMI is not "1"
#   1 — disabled:     ADLC_DISABLE_KIMI=1 explicitly opts out
#   2 — unavailable:  ask-kimi is not on PATH
#
# No `set -eu` here — return codes ARE the contract.
adlc_kimi_gate_check() {
  if ! command -v ask-kimi >/dev/null 2>&1; then return 2; fi
  if [ "${ADLC_DISABLE_KIMI:-0}" = "1" ]; then return 1; fi
  return 0
}
