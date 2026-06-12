# Fixture: delegate gate present but the delegate-tools-path resolver-source line is missing.

Has the `ADLC_DISABLE_DELEGATE` anchor and 4 of the 5 canonical literals — the
`. .adlc/partials/delegate-tools-path.sh …` resolver-source line is deliberately
absent while a `"$DELEGATE_TOOLS"/…` invocation remains. Exactly one
`canonical-helper` finding expected (the missing resolver-source literal) —
this is the precise REQ-433 corruption vector the linter must catch.

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
flag=$("$DELEGATE_TOOLS"/skill-flag.sh create)
"$DELEGATE_TOOLS"/skill-flag.sh mark "$flag" start_s "$(date -u +%s)"
adlc_delegate_gate_check; gate=$?
case $gate in
  0) ;;  # delegated
  1) ;;  # disabled via ADLC_DISABLE_DELEGATE=1
  2) ;;  # unavailable
esac
"$DELEGATE_TOOLS"/emit-telemetry.sh some-skill Some-Step REQ-xxx pass delegated ok 123
_adlc_emit_step_telemetry some-skill Some-Step
```

One finding expected: missing required literal `. .adlc/partials/delegate-tools-path.sh …`.
