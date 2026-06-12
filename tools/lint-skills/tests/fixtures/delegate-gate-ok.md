# Fixture: full delegate gate + flag-file telemetry present (REQ-522 shape).

Uses the de-branded gate + tools-path partials, the new disable anchor, and the
flag-file-derived telemetry (start_s marked to the sidecar, the shared resolver
call, and the emit-telemetry exec in the partial). The canonical check must
accept these spellings with zero findings.

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
. .adlc/partials/delegate-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-tools-path.sh
flag=$("$DELEGATE_TOOLS"/skill-flag.sh create)
"$DELEGATE_TOOLS"/skill-flag.sh mark "$flag" start_s "$(date -u +%s)"
adlc_delegate_gate_check; gate=$?
case $gate in
  0) ;;  # delegated
  1) ;;  # disabled via ADLC_DISABLE_DELEGATE=1
  2) ;;  # unavailable
esac
. .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh
_adlc_emit_step_telemetry some-skill Some-Step
```

The `"$DELEGATE_TOOLS"/emit-telemetry.sh ` literal lives in the sourced
`emit-step-telemetry.sh` partial (partial-aware canonical rule). No findings expected.
