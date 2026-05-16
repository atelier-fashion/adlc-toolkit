# Fixture: full Kimi gate present.

Uses ADLC_DISABLE_KIMI and sources the shared gate predicate (post-REQ-416),
then includes the canonical telemetry helpers:

```sh
. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh
adlc_kimi_gate_check; gate=$?
start_s=$(date -u +%s)
case $gate in
  0)
    duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))
    tools/kimi/emit-telemetry.sh some-skill Some-Step REQ-xxx pass delegated ok "$duration_ms"
    ;;
  1) ;;  # disabled via ADLC_DISABLE_KIMI=1
  2) ;;  # unavailable (ask-kimi not on PATH)
esac
```

No findings expected.
