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
#   0 — delegated:    adlc-read resolvable AND not disabled AND opt-in satisfied
#   1 — disabled:     ADLC_DISABLE_DELEGATE=1,
#                     OR opt-in NOT satisfied (BR-11 fresh-install posture)
#   2 — unavailable:  adlc-read is not resolvable (not on PATH and no
#                     executable at $HOME/bin/adlc-read)
#
# Reason-string contract:
#   The function exports ADLC_DELEGATE_GATE_REASON on every code path. Canonical
#   values (paired with the return code):
#     return 0 → "ok"
#     return 1 → "disabled-via-env"    (an explicit disable flag) OR
#                "disabled-via-config" (delegate.enabled: false — BUG-205) OR
#                "not-opted-in"         (BR-11: no opt-in signal)
#     return 2 → "no-binary"
#   `export` is intentional — a child delegate invocation may read it.
#
# Opt-in (BR-11) is resolved in the SAME precedence order as the provider fields
# (BR-2), highest first. Before BUG-205 `enabled` did not follow that order — it
# was a flat OR in which the legacy-key arm outranked the config file:
#   1. ADLC_DELEGATE_ENABLED=1 in the environment            → opted in
#   2. delegate.enabled in the config file, when the key is PRESENT → decisive
#      in BOTH directions. `true` opts in; `false` opts OUT and outranks the
#      continuity arm below. Resolved in Python, never parsed in shell
#      (REQ-515 ADR-3).
#   3. a legacy key in env (KIMI_API_KEY / MOONSHOT_API_KEY) — key continuity is
#      provider-preset data, not branding (REQ-522 BR-1/BR-3). Reached ONLY when
#      no config file exists, which is the pre-config install BR-11 wrote it for.
#   4. otherwise                                             → not opted in
#
# An ABSENT `enabled` key is not the same as `enabled: false`: absence is a
# default and yields to continuity, a written `false` is an instruction and does
# not. Collapsing the two is what BUG-205 was.
#
# Cost: one fork when a config file exists and ADLC_DELEGATE_ENABLED is unset.
# The no-config path stays pure-shell and fork-free.
#
# No `set -eu` here — return codes ARE the contract.

# Defensive default: a caller that reads the reason without invoking the
# function gets "unset", making telemetry visibly wrong instead of silently
# empty.
export ADLC_DELEGATE_GATE_REASON="unset"

# --- binary resolution ------------------------------------------------------
# GUI-launched Claude Code sessions may run with a PATH that lacks ~/bin (only
# .zshrc adds it), so `command -v adlc-read` alone reports "no-binary" on
# machines where ~/bin/adlc-read is installed and working. Resolution order:
#   1. `adlc-read` on PATH (echoed as the bare name — PATH wins)
#   2. an executable at $HOME/bin/adlc-read (echoed as the absolute path)
#   3. neither → empty string
_adlc_resolve_read_bin() {
  if command -v adlc-read >/dev/null 2>&1; then
    echo "adlc-read"
    return 0
  fi
  if [ -n "${HOME:-}" ] && [ -x "${HOME}/bin/adlc-read" ]; then
    echo "${HOME}/bin/adlc-read"
    return 0
  fi
  echo ""
}

# Resolve at source time so a fenced block that only sources this partial
# (e.g. a delegated-invocation fence that never calls the gate function) still
# gets $ADLC_READ_BIN. Call sites invoke "${ADLC_READ_BIN:-adlc-read}" — the
# bare-name default keeps them working against a stale vendored copy of this
# partial that predates the variable.
ADLC_READ_BIN="$(_adlc_resolve_read_bin)"
export ADLC_READ_BIN

# --- opt-in helper (BR-11) -------------------------------------------------
# Echoes "1" if delegation is opted in, "" otherwise. Pure-shell fast paths
# first; config probe last (only when a config file is present).
_adlc_delegate_opted_in() {
  # 1. explicit env opt-in. Rank 2 in the BR-2 precedence table, so it outranks
  #    the config file and needs no probe.
  if [ "${ADLC_DELEGATE_ENABLED:-}" = "1" ]; then
    echo 1
    return 0
  fi
  # 2. config file, when one exists — DECISIVE IN BOTH DIRECTIONS (BUG-205).
  #    `--print-enabled` runs the full Python predicate (env + config + legacy
  #    key), so when a config file is present its answer is the whole answer and
  #    the gate defers to it rather than second-guessing with shell arms.
  #
  #    This probe used to sit BELOW the legacy-key arm, as a pure-shell
  #    fast path that avoided the fork. That was sound for `enabled: true` (every
  #    arm agrees) and wrong for `enabled: false` (the arms disagree and the cheap
  #    one won), which silently overrode the operator's opt-out. The fork is the
  #    correct price for a governance decision; the no-config path below still
  #    pays nothing.
  #
  #    Failure is closed: a probe that errors, prints nothing, or prints anything
  #    other than "1" counts as NOT opted in. A gate that cannot establish consent
  #    must not assume it.
  _cfg="${ADLC_CONFIG:-${HOME:-}/.claude/adlc/config.yml}"
  if [ -n "$_cfg" ] && [ -f "$_cfg" ]; then
    # Status AND output are both checked. Command substitution captures stdout
    # and discards the exit code, so a probe that printed "1" and then FAILED
    # would otherwise be read as consent — the same shape of cheap assumption
    # that BUG-205 was. `_probe_rc=$?` must be the very next statement.
    if [ -n "${ADLC_READ_BIN:-}" ]; then
      _probe=$("$ADLC_READ_BIN" --print-enabled 2>/dev/null)
      _probe_rc=$?
    else
      _probe=""; _probe_rc=127
    fi
    if [ "$_probe_rc" -eq 0 ] && [ "$_probe" = "1" ]; then
      echo 1
    else
      echo ""
    fi
    return 0
  fi
  # 3. no config file at all: legacy key continuity (rank 4) — BR-11's exception
  #    for pre-config installs, which is the only place it was ever meant to act.
  if [ -n "${MOONSHOT_API_KEY:-}" ] || [ -n "${KIMI_API_KEY:-}" ]; then
    echo 1
    return 0
  fi
  echo ""
}

# Distinguishes an operator opt-out from a fresh install, for the reason string.
# Echoes "1" when the config file is what turned delegation off.
#
# The inference is sound rather than a re-parse: this is only consulted after the
# opt-in check has already returned false, and a config whose `enabled` is ABSENT
# would have fallen through to the legacy-key arm and opted in. So "not opted in,
# a config file exists, and a legacy key is present" can only mean the config said
# `false` out loud. Without a key present the two cases are indistinguishable and
# equally "not opted in", so the generic reason stays correct there.
_adlc_delegate_disabled_by_config() {
  _cfg="${ADLC_CONFIG:-${HOME:-}/.claude/adlc/config.yml}"
  if [ -n "$_cfg" ] && [ -f "$_cfg" ] &&
     { [ -n "${MOONSHOT_API_KEY:-}" ] || [ -n "${KIMI_API_KEY:-}" ]; }; then
    echo 1
    return 0
  fi
  echo ""
}

adlc_delegate_gate_check() {
  # Re-resolve at call time — PATH may have changed since the partial was
  # sourced, and a caller may invoke the gate long after sourcing.
  ADLC_READ_BIN="$(_adlc_resolve_read_bin)"
  export ADLC_READ_BIN
  if [ -z "$ADLC_READ_BIN" ]; then
    export ADLC_DELEGATE_GATE_REASON="no-binary"
    return 2
  fi
  if [ "${ADLC_DISABLE_DELEGATE:-0}" = "1" ]; then
    export ADLC_DELEGATE_GATE_REASON="disabled-via-env"
    return 1
  fi
  if [ -z "$(_adlc_delegate_opted_in)" ]; then
    if [ -n "$(_adlc_delegate_disabled_by_config)" ]; then
      export ADLC_DELEGATE_GATE_REASON="disabled-via-config"
    else
      export ADLC_DELEGATE_GATE_REASON="not-opted-in"
    fi
    return 1
  fi
  export ADLC_DELEGATE_GATE_REASON="ok"
  return 0
}
