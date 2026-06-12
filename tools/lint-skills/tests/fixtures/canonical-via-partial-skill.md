# Fixture: post-REQ-522 skill shape — emit-telemetry literal lives in a partial.

This SKILL.md mentions `ADLC_DISABLE_DELEGATE`, so `check_canonical` fires. It
keeps the gate-source, tools-path-source, start_s-mark, and resolver-call
literals **inline**, but **deliberately omits** the `"$DELEGATE_TOOLS"/emit-telemetry.sh`
literal — that one lives in `partials/emit-step-telemetry.sh` (REQ-436 ADR-1/ADR-4,
preserved by REQ-522's flag-file restructure).

With a sibling telemetry partial supplying that literal → **zero** `canonical-helper`
findings (post-restructure shape is clean). Without that partial → exactly **one**
missing-canonical finding for the emit-telemetry literal (proves the partial is what
satisfies it — ADR-4 is genuinely load-bearing, not vacuous).

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

The emit-telemetry literal is intentionally absent from this text — it lives in the partial.
