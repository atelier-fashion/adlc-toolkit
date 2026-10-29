---
name: fixture-agent
description: Fixture agent for the toolkit-path lint tests.
---

# fixture-agent

When neither agent form is listed, run `$ADLC_TOOLKIT_ROOT/agents/<name>.md` inline.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
cat "$ADLC_TOOLKIT_ROOT/agents/fixture-agent.md"
```
