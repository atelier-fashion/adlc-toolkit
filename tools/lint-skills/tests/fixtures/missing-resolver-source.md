# Fixture: Kimi gate present but the kimi-tools-path resolver-source line is missing.

Has the `ADLC_DISABLE_KIMI` anchor and 4 of the 5 canonical literals — the
`. .adlc/partials/kimi-tools-path.sh …` resolver-source line is deliberately
absent while a `"$KIMI_TOOLS"/…` invocation remains. Exactly one
`canonical-helper` finding expected (the missing resolver-source literal) —
this is the precise REQ-433 corruption vector the linter must catch.

```sh
. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh
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

One finding expected: missing required literal `. .adlc/partials/kimi-tools-path.sh …`.
