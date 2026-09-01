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
# Cost (REQ-603): one fork on every path that could AUTHORIZE. The veto and
# no-binary paths stay fork-free, so the emergency stop is as cheap as it ever
# was. Measured: the probe is ~21ms against a ~104s median delegated step.
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

# --- the dispatcher --------------------------------------------------------
adlc_delegate_gate_check() {
  # Re-resolve at call time — PATH may have changed since the partial was
  # sourced, and a caller may invoke the gate long after sourcing.
  ADLC_READ_BIN="$(_adlc_resolve_read_bin)"
  export ADLC_READ_BIN
  # (1) no-binary stays in shell: it is the one question the probe cannot answer,
  #     and it can only WITHHOLD delegation, never grant it (REQ-603 BR-5).
  #     Resolved BEFORE the veto, preserving the pre-REQ order — binary-missing
  #     plus veto-set yields 2, not 1.
  if [ -z "$ADLC_READ_BIN" ]; then
    export ADLC_DELEGATE_GATE_REASON="no-binary"
    return 2
  fi
  # (2) the veto: the one deliberate duplication (REQ-603 BR-2). A veto arm can
  #     only ever return "disabled", so the shell and Python copies can agree or
  #     abstain but never contradict — PROVIDED Python recognises at least every
  #     input this test does. Both test the literal "1"; widening one alone is
  #     the defect, and tests/test_cross_layer_veto.py is what enforces it.
  #     Kept here so the emergency stop stays fork-free: it is the control most
  #     likely to be reached when something has already gone wrong.
  if [ "${ADLC_DISABLE_DELEGATE:-0}" = "1" ]; then
    export ADLC_DELEGATE_GATE_REASON="disabled-via-env"
    return 1
  fi
  # (3) everything that could AUTHORIZE is Python's (REQ-603 BR-1). One probe,
  #     never two: two invocations could straddle an env change and report an
  #     incoherent pair (BR-7).
  #
  #     `_probe_rc=$?` MUST be the very next statement — command substitution
  #     discards the exit code, so a probe that printed a verdict and THEN failed
  #     would otherwise be read as consent (the shape BUG-205 was).
  # Bounded where a timeout(1) exists: the fork is now unconditional on every
  # non-vetoed call, so a wedged adlc-read would otherwise hang the calling skill
  # with no fallback. Expiry is a non-zero exit and therefore fails closed. Where
  # timeout(1) is absent (stock macOS), this degrades to the unbounded call
  # rather than failing — an unavailable hardening must not become an outage.
  # 10s: an emergency bound, not a tunable — the probe is ~21ms in practice.
  # Duplicated across both branches deliberately: building a "timeout 10"
  # prefix variable would require unquoted word-splitting to inject it as two
  # argv words, which is IFS-dependent and fragile (LESSON-329).
  if command -v timeout >/dev/null 2>&1; then
    _probe="$(timeout 10 "$ADLC_READ_BIN" --print-gate 2>/dev/null)"
  else
    _probe="$("$ADLC_READ_BIN" --print-gate 2>/dev/null)"
  fi
  _probe_rc=$?
  if [ "$_probe_rc" -ne 0 ]; then
    export ADLC_DELEGATE_GATE_REASON="not-opted-in"
    unset _probe _probe_rc
    return 1
  fi
  # Parse "<enabled> <reason>". The probe's stdout is untrusted input to shell
  # (LESSON-008): take exactly two fields and validate the reason against the
  # frozen enum before exporting it. An unrecognised value is a fail-closed
  # condition, not a pass-through.
  _verdict=${_probe%% *}
  _reason=${_probe#* }
  # Validate the PAIR, not the reason alone. Validating separately let "0 ok"
  # (and "\n1 ok", whose leading newline shifts the fields) export reason=ok
  # alongside return 1 — an inconsistent record forwarded verbatim into telemetry
  # and to agents/delegate-pre-pass.md, i.e. a withheld run logged as ok. Only
  # the four legal pairs are accepted; anything else fails closed.
  # Safe only because no frozen reason contains a space: the concatenation
  # "$_verdict $_reason" is unambiguous. Adding a reason with a space would
  # silently break this match — keep the enum space-free.
  case "$_verdict $_reason" in
    "1 ok")
      export ADLC_DELEGATE_GATE_REASON="ok"
      unset _probe _probe_rc _verdict _reason
      return 0 ;;
    "0 disabled-via-env"|"0 disabled-via-config"|"0 not-opted-in")
      export ADLC_DELEGATE_GATE_REASON="$_reason"
      unset _probe _probe_rc _verdict _reason
      return 1 ;;
    *)
      export ADLC_DELEGATE_GATE_REASON="not-opted-in"
      unset _probe _probe_rc _verdict _reason
      return 1 ;;
  esac
}
