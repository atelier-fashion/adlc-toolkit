#!/bin/sh
# Resolve-and-emit the per-step delegation telemetry record for the delegating
# skills (analyze, spec, proceed, wrapup) via _adlc_emit_step_telemetry
# (REQ-436 ADR-1/2/3; flag-file-derived state added REQ-522 ADR-3/ADR-4).
#
# SOURCED, not executed — call sites source this and then call
# `_adlc_emit_step_telemetry <skill> <step>` in the SAME fenced block. Sourcing
# first runs the delegate-tools-path resolver below (so the function body's
# "$DELEGATE_TOOLS" references resolve regardless of which fenced block / shell
# calls it — SKILL.md fenced blocks do not share shell state across steps),
# then defines the function.
#
# Why flag-file-derived (REQ-522 BR-4, ADR-3): the create -> gate -> invoke
# steps and this resolve step live in SEPARATE SKILL.md fenced blocks, and
# fenced blocks do not share shell state. Reading caller shell vars (start_s,
# invoked, exit) therefore always saw empty values, so every run resolved to
# mode=fallback,gate=fail and the ghost-skip branch was unreachable (the
# inert-telemetry bug). The skill now PERSISTS that state to
# the flag-file sidecar via `skill-flag.sh mark` in the same fence as each
# operation, and this resolver READS it back via `skill-flag.sh read`. No shell
# variable crosses a fenced-block boundary.
#
# Caller contract — the function reads ONLY:
#   $1                  skill name, e.g. "analyze" / "spec" / "proceed" / "wrapup"
#   $2                  step label, e.g. "Step-1.5" / "Step-1.6" / "Phase-5"
#   $flag               flag path from skill-flag.sh create (the ONLY caller var;
#                       it is a literal the skill threads through, not state)
# Everything else (start_s, invoked, exit, reason) is read from the flag-file
# sidecar that the skill `mark`ed. $DELEGATE_TOOLS is resolved by the source
# below (defensive "tools/delegate" default → telemetry never blocks:
# LESSON-008 / BR-4).
#
# Sidecar keys the skill marks (REQ-522 ADR-3):
#   start_s   epoch seconds, marked at create time
#   reason    the gate's ADLC_DELEGATE_GATE_REASON, marked right after the gate
#   invoked   "1", marked immediately BEFORE the delegate call (absent if the
#             call site was never reached)
#   exit      the delegate's exit status, marked immediately AFTER the call
#             returns (absent if the call was announced via `invoked` but never
#             actually run — the ghost-skip signature)
#
# Resolution precedence (REQ-424 shape, now derived purely from sidecar facts —
# no reliance on flag-file presence, which fenced blocks cannot share):
#   invoked unset                  -> fallback,  gate=fail, reason=<gate reason>/not-invoked
#   invoked set, exit unset         -> ghost-skip, gate=pass, reason=gate-passed-no-call
#   invoked set, exit==0            -> delegated, gate=pass, reason=ok
#   invoked set, exit!=0            -> fallback,  gate=pass, reason=api-error
#   no sidecar at all (lost path)   -> fallback,  gate=fail, reason=no-flag
#
# POSIX sh only: no set -eu, no bashisms, no `local`, no `[[`, no arrays, no
# `function` keyword, no GNU-only utilities (LESSON-012 #5, LESSON-013).
# Underscore-prefixed `_aest_*` globals stand in for the former `local`s; each
# call site sources this in its own short-lived block shell, so namespace
# leakage is a non-issue (REQ-436 ADR-3).

. .adlc/partials/delegate-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-tools-path.sh
_adlc_emit_step_telemetry() {
    # $1 = skill name, $2 = step label. All telemetry state is read from the
    # flag-file sidecar — NEVER from caller shell vars (REQ-522 BR-4).
    _aest_skill="$1"
    _aest_step="$2"

    _aest_start=$("$DELEGATE_TOOLS"/skill-flag.sh read "$flag" start_s 2>/dev/null || true)
    _aest_invoked=$("$DELEGATE_TOOLS"/skill-flag.sh read "$flag" invoked 2>/dev/null || true)
    _aest_exit=$("$DELEGATE_TOOLS"/skill-flag.sh read "$flag" exit 2>/dev/null || true)
    _aest_reason=$("$DELEGATE_TOOLS"/skill-flag.sh read "$flag" reason 2>/dev/null || true)

    # Duration: only meaningful if start_s was marked. A missing start_s yields
    # "-" rather than a garbage arithmetic result.
    if [ -n "$_aest_start" ]; then
        _aest_duration_ms=$(( ($(date -u +%s) - $_aest_start) * 1000 ))
    else
        _aest_duration_ms="-"
    fi

    if [ -z "$flag" ] || { [ ! -f "$flag.state" ] && [ ! -e "$flag" ]; }; then
        # Flag path was lost entirely (no sidecar, nothing marked).
        _aest_mode="fallback"; _aest_reason="no-flag"; _aest_gate_result="fail"
    elif [ -z "$_aest_invoked" ]; then
        _aest_mode="fallback"
        # Preserve the gate's reason when we have it; else a generic marker.
        [ -n "$_aest_reason" ] || _aest_reason="not-invoked"
        _aest_gate_result="fail"
    elif [ -z "$_aest_exit" ]; then
        # invoked was marked but no exit was ever recorded — the call site was
        # announced but the real delegate call never ran (ghost-skip signature).
        _aest_mode="ghost-skip"; _aest_reason="gate-passed-no-call"
        _aest_gate_result="pass"
    elif [ "$_aest_exit" -eq 0 ] 2>/dev/null; then
        _aest_mode="delegated"; _aest_reason="ok"; _aest_gate_result="pass"
    else
        _aest_mode="fallback"; _aest_reason="api-error"; _aest_gate_result="pass"
    fi

    # REQ id from whichever var the calling skill uses (spec/proceed: REQ_NUM;
    # wrapup: REQ_ID), else "unknown".
    _aest_req="${REQ_NUM:-${REQ_ID:-unknown}}"
    "$DELEGATE_TOOLS"/emit-telemetry.sh "$_aest_skill" "$_aest_step" "$_aest_req" "$_aest_gate_result" "$_aest_mode" "$_aest_reason" "$_aest_duration_ms"
    # Canonical clear-point for the resolver: remove the flag AND its sidecar so
    # no flag file remains after a normal run (REQ-522 AC-3).
    "$DELEGATE_TOOLS"/skill-flag.sh clear "$flag"
}
