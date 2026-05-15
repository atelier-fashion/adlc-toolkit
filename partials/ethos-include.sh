#!/bin/sh
# Emits the project ETHOS.md content with a fallback chain.
# Consumer-project copy wins; toolkit copy is the fallback; "No ethos found"
# only if both reads fail. The `||` chain tolerates each cat failing.
cat .adlc/ETHOS.md 2>/dev/null \
  || cat ~/.claude/skills/ETHOS.md 2>/dev/null \
  || echo "No ethos found"
