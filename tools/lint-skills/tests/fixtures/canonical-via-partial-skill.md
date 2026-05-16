# Fixture: post-REQ-436 analyze shape — helper body moved into a partial.

This SKILL.md mentions `ADLC_DISABLE_KIMI`, so `check_canonical` fires. It
keeps canonical literals **L1 / L4 / L5 inline** (the before-gate +
gate-source lines REQ-436 ADR-2 left byte-untouched) but **deliberately omits
L2 / L3** — the `duration_ms` arithmetic and the `emit-telemetry.sh`
invocation moved into `partials/emit-step-telemetry.sh` (REQ-436 ADR-1/ADR-4).

With a sibling telemetry partial supplying L2/L3 → **zero** `canonical-helper`
findings (post-REQ-436 shape is clean). Without that partial → exactly the
**two** missing-canonical findings for L2 and L3 (proves the partial is what
satisfies them — ADR-4 is genuinely load-bearing, not vacuous).

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
. .adlc/partials/emit-step-telemetry.sh 2>/dev/null || . ~/.claude/skills/partials/emit-step-telemetry.sh
_adlc_emit_step_telemetry Step-1.5
```

L2/L3 intentionally absent from this text — they live in the partial.
