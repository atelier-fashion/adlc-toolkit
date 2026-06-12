#!/bin/sh
# Resolve the directory holding the delegation telemetry executables
# (emit-telemetry.sh, skill-flag.sh, check-delegation.sh) into $DELEGATE_TOOLS.
#
# SOURCED, not executed — call sites use "$DELEGATE_TOOLS"/<script>.sh. Sourcing
# runs the resolution below and exports $DELEGATE_TOOLS into the caller's shell,
# mirroring how partials/delegate-gate.sh exports ADLC_DELEGATE_GATE_REASON.
#
# Resolution order:
#   1. project-local  tools/delegate                          (canonical repo / dogfooding)
#   2. global symlink  ${HOME:-}/.claude/skills/tools/delegate  (every downstream
#      repo — ~/.claude/skills is symlinked to the canonical toolkit repo root;
#      ${HOME:-} so an unset HOME under a `set -u` caller degrades, not aborts)
#   3. neither → tools/delegate (defensive default; existing 2>/dev/null / || true
#      guards at call sites keep this a silent no-op — telemetry must never block
#      a skill: REQ-424 / LESSON-008 BR-4)
#
# POSIX sh only: no set -eu, no bashisms, no GNU-only utilities, no python/node.
# Emits nothing on stdout/stderr on any path.

# Defensive default so a caller that sources this but skips the branching
# still has the var set.
export DELEGATE_TOOLS="tools/delegate"

if [ -x "tools/delegate/emit-telemetry.sh" ]; then
  DELEGATE_TOOLS="tools/delegate"
elif [ -x "${HOME:-}/.claude/skills/tools/delegate/emit-telemetry.sh" ]; then
  DELEGATE_TOOLS="${HOME:-}/.claude/skills/tools/delegate"
else
  DELEGATE_TOOLS="tools/delegate"
fi
export DELEGATE_TOOLS
