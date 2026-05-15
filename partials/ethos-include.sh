#!/bin/sh
# Emits the project ETHOS.md content with a fallback chain.
# Consumer-project copy wins; toolkit copy is the fallback; "No ethos found"
# only if both reads fail OR both files are empty.
#
# We use `[ -s file ]` (file exists AND is non-empty) rather than just letting
# `cat` succeed on an empty file — an empty `.adlc/ETHOS.md` would otherwise
# silently swallow the ethos block (REQ-416 verify finding H1).
if [ -s .adlc/ETHOS.md ]; then
    cat .adlc/ETHOS.md
elif [ -s "$HOME/.claude/skills/ETHOS.md" ]; then
    cat "$HOME/.claude/skills/ETHOS.md"
else
    echo "No ethos found"
fi
