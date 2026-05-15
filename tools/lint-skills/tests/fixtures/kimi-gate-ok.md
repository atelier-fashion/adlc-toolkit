# Fixture: full Kimi gate present.

Uses ADLC_DISABLE_KIMI and includes the canonical helpers:

```sh
start_s=$(date -u +%s)
duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))
tools/kimi/emit-telemetry.sh some-skill Some-Step REQ-xxx pass delegated ok 123
```

No findings expected.
