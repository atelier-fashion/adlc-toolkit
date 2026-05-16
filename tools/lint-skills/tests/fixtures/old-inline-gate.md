# Fixture: pre-REQ-416 inline gate form — must fire exactly one finding.

This skill still inlines the old gate predicate instead of sourcing the
shared `kimi-gate.sh` partial. It has the three telemetry literals and the
`ADLC_DISABLE_KIMI` anchor, but is missing the post-REQ-416 gate-source
line, so the linter MUST report exactly one `canonical-helper` finding —
for the missing source-line literal #4, and only that one.

```sh
if command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]; then
    start_s=$(date -u +%s)
    duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))
    tools/kimi/emit-telemetry.sh some-skill Some-Step REQ-xxx pass delegated ok "$duration_ms"
fi
```

Exactly one finding expected (missing literal #4 — the gate-source line).
