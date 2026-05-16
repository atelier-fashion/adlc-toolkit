#!/bin/sh
# Resolve the directory holding the Kimi telemetry executables
# (emit-telemetry.sh, skill-flag.sh, check-delegation.sh) into $KIMI_TOOLS.
#
# SOURCED, not executed — call sites use "$KIMI_TOOLS"/<script>.sh. Sourcing
# runs the resolution below and exports KIMI_TOOLS into the caller's shell,
# mirroring how partials/kimi-gate.sh exports ADLC_KIMI_GATE_REASON
# (REQ-416 ADR-2; REQ-433 ADR-1/ADR-2).
#
# Resolution order:
#   1. project-local  tools/kimi                       (canonical repo / dogfooding)
#   2. global symlink  ${HOME:-}/.claude/skills/tools/kimi  (every downstream
#      repo — ~/.claude/skills is symlinked to the canonical toolkit repo root;
#      ${HOME:-} so an unset HOME under a `set -u` caller degrades, not aborts)
#   3. neither → tools/kimi (today's effective behavior; existing
#      2>/dev/null / || true guards at call sites keep this a silent no-op —
#      telemetry must never block a skill: REQ-424 / LESSON-008 BR-4)
#
# POSIX sh only: no set -eu, no bashisms, no GNU-only utilities, no python/node
# (LESSON-012 #5, LESSON-013). Emits nothing on stdout/stderr on any path.

# Defensive default so a caller that sources this but skips the branching
# still has KIMI_TOOLS set (mirrors kimi-gate.sh's defensive export).
export KIMI_TOOLS="tools/kimi"

if [ -x "tools/kimi/emit-telemetry.sh" ]; then
  KIMI_TOOLS="tools/kimi"
elif [ -x "${HOME:-}/.claude/skills/tools/kimi/emit-telemetry.sh" ]; then
  KIMI_TOOLS="${HOME:-}/.claude/skills/tools/kimi"
else
  KIMI_TOOLS="tools/kimi"
fi
export KIMI_TOOLS
