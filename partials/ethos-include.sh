#!/bin/sh
# Emits the project ETHOS.md content with a fallback chain.
# Consumer-project copy wins; toolkit copy is the fallback; "No ethos found"
# only if both reads fail OR both files are empty. The toolkit copy is
# ToolkitRoot's (REQ-669 ADR-2): $ADLC_TOOLKIT_ROOT when the caller exported it,
# else the ~/.claude/skills symlink install. With neither set, that default would
# read a bare $HOME and abort a `set -u` caller, so the toolkit copy is skipped.
#
# We use `[ -s file ]` (file exists AND is non-empty) rather than just letting
# `cat` succeed on an empty file — an empty `.adlc/ETHOS.md` would otherwise
# silently swallow the ethos block (REQ-416 verify finding H1).
if [ -s .adlc/ETHOS.md ]; then
    cat .adlc/ETHOS.md
elif [ -n "${ADLC_TOOLKIT_ROOT:-}${HOME+x}" ] && [ -s "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/ETHOS.md" ]; then
    cat "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/ETHOS.md"
else
    echo "No ethos found"
fi
