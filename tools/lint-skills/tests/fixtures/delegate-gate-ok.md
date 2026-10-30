# Fixture: full delegate gate + flag-file telemetry present (REQ-522 shape).

Uses the de-branded gate + tools-path partials, the new disable anchor, and the
flag-file-derived telemetry (start_s marked to the sidecar, the shared resolver
call, and the emit-telemetry exec in the partial). The canonical check must
accept these spellings with zero findings.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi
if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh"; fi
flag=$("$DELEGATE_TOOLS"/skill-flag.sh create)
"$DELEGATE_TOOLS"/skill-flag.sh mark "$flag" start_s "$(date -u +%s)"
adlc_delegate_gate_check; gate=$?
case $gate in
  0) ;;  # delegated
  1) ;;  # disabled via ADLC_DISABLE_DELEGATE=1
  2) ;;  # unavailable
esac
if [ -f .adlc/partials/emit-step-telemetry.sh ]; then . .adlc/partials/emit-step-telemetry.sh; else . "$ADLC_TOOLKIT_ROOT/partials/emit-step-telemetry.sh"; fi
_adlc_emit_step_telemetry some-skill Some-Step
```

The `"$DELEGATE_TOOLS"/emit-telemetry.sh ` literal lives in the sourced
`emit-step-telemetry.sh` partial (partial-aware canonical rule). No findings expected.
