# ok.sh

The engine is `"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/lane_check.py"`.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/ok.sh ]; then . .adlc/partials/ok.sh; else . "$ADLC_TOOLKIT_ROOT/partials/ok.sh"; fi
```
