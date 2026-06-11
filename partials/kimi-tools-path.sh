#!/bin/sh
# Back-compat alias (REQ-515 ADR-5) for delegate-tools-path.sh.
#
# The canonical resolver is partials/delegate-tools-path.sh. This file resolves
# the SAME directory with the SAME logic and exports BOTH $KIMI_TOOLS (legacy)
# and $DELEGATE_TOOLS, so the existing source-line
#   . .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh
# keeps working byte-identically. The resolution is INLINED rather than sourced
# from the canonical file because a partial sourced by absolute path cannot
# reliably locate a sibling ($0 is the caller's path when sourced) — duplicating
# ~10 lines is the lesser evil and keeps both files independently correct.
#
# The executables still physically live under tools/kimi/ (the directory rename
# is a deferred staged follow-up, REQ-515 ADR-1), so the paths are unchanged.
#
# SOURCED, not executed. POSIX sh only. Emits nothing on stdout/stderr.

# Defensive default so a caller that sources this but skips the branching
# still has both vars set.
export KIMI_TOOLS="tools/kimi"
export DELEGATE_TOOLS="tools/kimi"

if [ -x "tools/kimi/emit-telemetry.sh" ]; then
  KIMI_TOOLS="tools/kimi"
elif [ -x "${HOME:-}/.claude/skills/tools/kimi/emit-telemetry.sh" ]; then
  KIMI_TOOLS="${HOME:-}/.claude/skills/tools/kimi"
else
  KIMI_TOOLS="tools/kimi"
fi
export KIMI_TOOLS
DELEGATE_TOOLS="$KIMI_TOOLS"
export DELEGATE_TOOLS
