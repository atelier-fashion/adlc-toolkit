#!/bin/sh
# Resolve the directory holding the delegation telemetry executables
# (emit-telemetry.sh, skill-flag.sh, check-delegation.sh) into $DELEGATE_TOOLS,
# and ALSO export the legacy $KIMI_TOOLS alias (REQ-515 ADR-5) so existing
# call sites using "$KIMI_TOOLS"/<script>.sh keep working unchanged.
#
# SOURCED, not executed — call sites use "$DELEGATE_TOOLS"/<script>.sh (or the
# legacy "$KIMI_TOOLS"). Sourcing runs the resolution below and exports both
# variables into the caller's shell, mirroring how partials/delegate-gate.sh
# exports ADLC_DELEGATE_GATE_REASON.
#
# The executables still physically live under tools/kimi/ — the directory rename
# is a deferred staged follow-up (REQ-515 ADR-1), so the resolution paths are
# unchanged from the historical kimi-tools-path.sh.
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
# POSIX sh only: no set -eu, no bashisms, no GNU-only utilities, no python/node.
# Emits nothing on stdout/stderr on any path.

# Defensive default so a caller that sources this but skips the branching
# still has both vars set.
export DELEGATE_TOOLS="tools/kimi"
export KIMI_TOOLS="tools/kimi"

if [ -x "tools/kimi/emit-telemetry.sh" ]; then
  DELEGATE_TOOLS="tools/kimi"
elif [ -x "${HOME:-}/.claude/skills/tools/kimi/emit-telemetry.sh" ]; then
  DELEGATE_TOOLS="${HOME:-}/.claude/skills/tools/kimi"
else
  DELEGATE_TOOLS="tools/kimi"
fi
export DELEGATE_TOOLS
# Legacy alias — kept identical so "$KIMI_TOOLS" call sites are unaffected.
KIMI_TOOLS="$DELEGATE_TOOLS"
export KIMI_TOOLS
