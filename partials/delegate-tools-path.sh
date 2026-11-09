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
#   2. ToolkitRoot     "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/delegate"
#      (every downstream repo — the installed toolkit: the plugin's cache copy, or
#      the clone behind the ~/.claude/skills symlink when ADLC_TOOLKIT_ROOT is unset;
#      REQ-669 ADR-2). The default arm reads a bare $HOME, so this tier is probed
#      only when ADLC_TOOLKIT_ROOT or HOME is set: an unset HOME under a `set -u`
#      caller degrades to 3, not aborts)
#   3. neither → tools/delegate (defensive default; existing 2>/dev/null / || true
#      guards at call sites keep this a silent no-op — telemetry must never block
#      a skill: REQ-424 / LESSON-008 BR-4)
#
# Under `fence-run` (ADLC_FENCE_TOOLKIT_ONLY=1, REQ-682 ADR-4) neither cwd-relative
# arm is taken, because the working copy is the exec model's to write: tier 1 is
# skipped, and tier 3 names ToolkitRoot's directory instead of `tools/delegate`.
# Unset, the resolution is exactly the three tiers above.
#
# POSIX sh only: no set -eu, no bashisms, no GNU-only utilities, no python/node.
# Emits nothing on stdout/stderr on any path.

# Defensive default so a caller that sources this but skips the branching
# still has the var set.
export DELEGATE_TOOLS="tools/delegate"

if [ "${ADLC_FENCE_TOOLKIT_ONLY:-0}" != 1 ] && [ -x "tools/delegate/emit-telemetry.sh" ]; then
  DELEGATE_TOOLS="tools/delegate"
elif [ -n "${ADLC_TOOLKIT_ROOT:-}${HOME+x}" ] && [ -x "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/delegate/emit-telemetry.sh" ]; then
  DELEGATE_TOOLS="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/delegate"
elif [ "${ADLC_FENCE_TOOLKIT_ONLY:-0}" = 1 ]; then
  DELEGATE_TOOLS="${ADLC_TOOLKIT_ROOT:-/nonexistent}/tools/delegate"
else
  DELEGATE_TOOLS="tools/delegate"
fi
export DELEGATE_TOOLS
