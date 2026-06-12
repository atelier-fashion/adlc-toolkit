# Fixture: full delegate gate present (new provider-neutral spelling, REQ-515).

Uses the generalized gate + tools-path partials and the new disable anchor.
The canonical check must accept these new spellings (dual-literal rule, ADR-9):

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
. .adlc/partials/delegate-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-tools-path.sh
adlc_delegate_gate_check; gate=$?
case $gate in
  0) ;;  # delegated
  1) ;;  # disabled via ADLC_DISABLE_DELEGATE=1
  2) ;;  # unavailable
esac
start_s=$(date -u +%s)
"$DELEGATE_TOOLS"/emit-telemetry.sh some-skill Some-Step REQ-xxx pass delegated ok 123
duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))
```

No findings expected.
