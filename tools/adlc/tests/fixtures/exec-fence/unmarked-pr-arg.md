<!-- REQ-719 TASK-273 fixture: appended to a copy of validate/SKILL.md by
     tools/adlc/tests/test_fence_census.py. The fence hands `<n>`, a placeholder without the
     PR mark, to adlc_forge_pr_edit as its PR: the runner would never check that number is the
     caller's PR, so the census must leave the fence unrouted (BR-13, AC-11). -->

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
adlc_forge_pr_edit "<n>" --title "<short title>"
```
