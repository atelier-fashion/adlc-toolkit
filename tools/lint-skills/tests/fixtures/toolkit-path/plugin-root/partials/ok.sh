#!/bin/sh
# ok.sh reads the toolkit through the default-expansion spelling, whose default
# is ~/.claude/skills on the symlink route.
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/forge.sh"; fi
adlc_ok_engine="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/lane_check.py"
    # An indented comment: $HOME/.claude/skills
