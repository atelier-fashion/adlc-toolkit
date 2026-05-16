# Fixture: full Kimi gate present.

Uses the post-REQ-416 sourced gate and includes the canonical helpers:

```sh
. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh
. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh
adlc_kimi_gate_check; gate=$?
case $gate in
  0) ;;  # delegated
  1) ;;  # disabled via ADLC_DISABLE_KIMI=1
  2) ;;  # unavailable
esac
start_s=$(date -u +%s)
"$KIMI_TOOLS"/emit-telemetry.sh some-skill Some-Step REQ-xxx pass delegated ok 123
duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))
```

No findings expected.
