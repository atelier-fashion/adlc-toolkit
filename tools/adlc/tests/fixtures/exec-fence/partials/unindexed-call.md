<!-- REQ-682 TASK-247 fixture: appended to a copy of validate/SKILL.md. The fence calls a
     function no partial defines, so the audit must refuse it: a new verb starts refused. -->

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
adlc_forge_pr_land 1
```
