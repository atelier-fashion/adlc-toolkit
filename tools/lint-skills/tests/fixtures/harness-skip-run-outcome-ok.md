# Fixture: REQ-648 run-outcome fence with the BUG-228 harness line (clean).

A second fence only mentions the wrapper in a comment, which is not a call.

**Provenance-classifying harness (BUG-228):** on such a harness, run none of this fence and reply `run-outcome skipped: provenance-classifying harness`.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh"; fi
"$DELEGATE_TOOLS"/emit-run-outcome.sh --state "<state>" --terminal merged --engine solo
```

Padding line 0.
Padding line 1.
Padding line 2.
Padding line 3.
Padding line 4.
Padding line 5.
Padding line 6.
Padding line 7.
Padding line 8.
Padding line 9.
Padding line 10.
Padding line 11.
Padding line 12.
Padding line 13.
Padding line 14.
Padding line 15.
Padding line 16.
Padding line 17.
Padding line 18.
Padding line 19.
Padding line 20.
Padding line 21.
Padding line 22.
Padding line 23.
Padding line 24.
Padding line 25.
Padding line 26.
Padding line 27.
Padding line 28.
Padding line 29.
Padding line 30.

```sh
# emit-run-outcome.sh is retired here
true
```
