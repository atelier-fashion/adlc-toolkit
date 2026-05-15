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
# Reason-string contract (REQ-426 BR-2, ADR-2):
#   The function ALSO exports ADLC_KIMI_GATE_REASON on every code path, so
#   callers can emit telemetry without re-interrogating the environment.
#   Canonical values (paired with the return code):
#     return 0 → ADLC_KIMI_GATE_REASON="ok"
#     return 1 → ADLC_KIMI_GATE_REASON="disabled-via-env"
#     return 2 → ADLC_KIMI_GATE_REASON="no-binary"
#   `export` is intentional — a child `ask-kimi` invocation may read it.
#
# No `set -eu` here — return codes ARE the contract.

# Defensive default: a caller that reads $ADLC_KIMI_GATE_REASON without first
# invoking adlc_kimi_gate_check (e.g., a partial sourced but the function
# never called) gets "unset" rather than empty — making telemetry visibly
# wrong instead of silently empty (REQ-426 verify H2). Callers that DO invoke
# the function will overwrite this with one of the canonical values below.
export ADLC_KIMI_GATE_REASON="unset"

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
