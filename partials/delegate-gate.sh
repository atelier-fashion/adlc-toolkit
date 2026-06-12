#!/bin/sh
# Shared provider-agnostic delegation gate predicate (REQ-515 BR-4/BR-11).
# This is the canonical (and only) gate predicate (REQ-522 retired the legacy
# back-compat alias partial).
#
# Sourceable POSIX shell function. Each call site reads $? IMMEDIATELY into a
# variable (gate=$?) before any other command, because $? is clobbered by every
# subsequent command. See partials/delegate-gate.md for the full protocol.
#
# Return-code contract (UNCHANGED 0/1/2 shape so existing callers' case
# statements keep working):
#   0 — delegated:    adlc-read on PATH AND not disabled AND opt-in satisfied
#   1 — disabled:     ADLC_DISABLE_DELEGATE=1,
#                     OR opt-in NOT satisfied (BR-11 fresh-install posture)
#   2 — unavailable:  adlc-read is not on PATH
#
# Reason-string contract:
#   The function exports ADLC_DELEGATE_GATE_REASON on every code path. Canonical
#   values (paired with the return code):
#     return 0 → "ok"
#     return 1 → "disabled-via-env"   (an explicit disable flag) OR
#                "not-opted-in"        (BR-11: no opt-in signal)
#     return 2 → "no-binary"
#   `export` is intentional — a child delegate invocation may read it.
#
# Opt-in (BR-11) is satisfied by ANY of:
#   * ADLC_DELEGATE_ENABLED=1 in the environment, OR
#   * a legacy key set in env (KIMI_API_KEY / MOONSHOT_API_KEY) — key continuity
#     is provider-preset data, not branding (REQ-522 BR-1/BR-3), OR
#   * delegate.enabled: true in the config file (resolved in Python; the gate
#     shells out to the resolver ONLY when no env opt-in is present AND a config
#     file exists, so the common paths stay pure-shell and fast).
#
# No `set -eu` here — return codes ARE the contract.

# Defensive default: a caller that reads the reason without invoking the
# function gets "unset", making telemetry visibly wrong instead of silently
# empty.
export ADLC_DELEGATE_GATE_REASON="unset"

# --- opt-in helper (BR-11) -------------------------------------------------
# Echoes "1" if delegation is opted in, "" otherwise. Pure-shell fast paths
# first; config probe last (only when a config file is present).
_adlc_delegate_opted_in() {
  # 1. explicit env opt-in
  if [ "${ADLC_DELEGATE_ENABLED:-}" = "1" ]; then
    echo 1
    return 0
  fi
  # 2. legacy key continuity (today's installs)
  if [ -n "${MOONSHOT_API_KEY:-}" ] || [ -n "${KIMI_API_KEY:-}" ]; then
    echo 1
    return 0
  fi
  # 3. config-file enabled: true — resolved by the Python tool, not parsed in
  #    shell (REQ-515 ADR-3). Only probe when a config file actually exists, so
  #    the no-config fast path never forks a subprocess.
  _cfg="${ADLC_CONFIG:-${HOME:-}/.claude/adlc/config.yml}"
  if [ -n "$_cfg" ] && [ -f "$_cfg" ]; then
    if command -v adlc-read >/dev/null 2>&1; then
      # `adlc-read --print-enabled` prints "1" / "0" and exits 0; never errors.
      if [ "$(adlc-read --print-enabled 2>/dev/null)" = "1" ]; then
        echo 1
        return 0
      fi
    fi
  fi
  echo ""
}

adlc_delegate_gate_check() {
  if ! command -v adlc-read >/dev/null 2>&1; then
    export ADLC_DELEGATE_GATE_REASON="no-binary"
    return 2
  fi
  if [ "${ADLC_DISABLE_DELEGATE:-0}" = "1" ]; then
    export ADLC_DELEGATE_GATE_REASON="disabled-via-env"
    return 1
  fi
  if [ -z "$(_adlc_delegate_opted_in)" ]; then
    export ADLC_DELEGATE_GATE_REASON="not-opted-in"
    return 1
  fi
  export ADLC_DELEGATE_GATE_REASON="ok"
  return 0
}
