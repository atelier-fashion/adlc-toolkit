#!/bin/sh
# Resolve-and-emit the per-step Kimi delegation telemetry record for /analyze
# via _adlc_emit_step_telemetry (REQ-436 ADR-1/ADR-2/ADR-3; relocated verbatim
# in behavior from analyze/SKILL.md's inline Step-1.5 helper, REQ-428).
#
# SOURCED, not executed — call sites source this and then call
# `_adlc_emit_step_telemetry <Step-label>`. Sourcing first runs the
# kimi-tools-path resolver below (so the function body's "$KIMI_TOOLS"
# references resolve regardless of which fenced block / shell calls it —
# SKILL.md fenced blocks do not share shell state across steps), then defines
# the function. Mirrors how partials/kimi-gate.sh / kimi-tools-path.sh are
# sourced per call site.
#
# Caller-environment contract — the function reads, and does NOT define:
#   $1                     step label, e.g. "Step-1.5" / "Step-1.6"
#   $start_s               epoch seconds captured before the gate check
#   $ASK_KIMI_INVOKED       "" iff ask-kimi was never invoked this step
#   $KIMI_EXIT             ask-kimi's exit status (0 == clean)
#   $flag                  skill-invocation flag id from skill-flag.sh create
#   $ADLC_KIMI_GATE_REASON exported by partials/kimi-gate.sh
# It uses $KIMI_TOOLS, resolved/exported by the kimi-tools-path source below
# (defensive "tools/kimi" default → telemetry never blocks: LESSON-008 / BR-4).
#
# POSIX sh only: no set -eu, no bashisms, no `local`, no `[[`, no arrays, no
# `function` keyword, no GNU-only utilities (LESSON-012 #5, LESSON-013).
# Underscore-prefixed `_aest_*` globals stand in for the former `local`s; each
# call site sources this in its own short-lived block shell, so namespace
# leakage is a non-issue (REQ-436 ADR-3).

. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh
_adlc_emit_step_telemetry() {
    # $1 = step label (e.g. "Step-1.5" or "Step-1.6")
    # Reads caller's $start_s, $ASK_KIMI_INVOKED, $KIMI_EXIT, $flag, $ADLC_KIMI_GATE_REASON.
    _aest_step="$1"
    _aest_duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))
    if [ -z "$ASK_KIMI_INVOKED" ]; then
        "$KIMI_TOOLS"/skill-flag.sh clear "$flag"
        _aest_mode="fallback"
        _aest_reason="$ADLC_KIMI_GATE_REASON"
        _aest_gate_result="fail"
    elif "$KIMI_TOOLS"/skill-flag.sh check "$flag" >/dev/null 2>&1; then
        _aest_mode="ghost-skip"; _aest_reason="gate-passed-no-call"
        "$KIMI_TOOLS"/skill-flag.sh clear "$flag"
        _aest_gate_result="pass"
    elif [ "$KIMI_EXIT" -eq 0 ]; then
        _aest_mode="delegated"; _aest_reason="ok"; _aest_gate_result="pass"
    else
        _aest_mode="fallback"; _aest_reason="api-error"; _aest_gate_result="pass"
    fi
    "$KIMI_TOOLS"/emit-telemetry.sh analyze "$_aest_step" unknown "$_aest_gate_result" "$_aest_mode" "$_aest_reason" "$_aest_duration_ms"
    "$KIMI_TOOLS"/skill-flag.sh clear "$flag"
}
