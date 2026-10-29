# Fixture: the guard is COMMENTED OUT — must be flagged (REQ-609 verify D3)

A `#` at the start of a line is not a refusal. The guard literal is present in
this fence character-for-character, and it runs on exactly no machine — so a
check that reads the line without noticing the comment marker reports a fence
that hands the corpus to an unguarded value as clean, and the ordering half of
the contract becomes satisfiable by pasting a comment above the invocation.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi
# case "$ADLC_READ_BIN" in /*) ;; *) echo "/example: refusing" >&2; exit 1 ;; esac
command "$ADLC_READ_BIN" --no-warn --paths ./notes.md --question "summarize"
```

Expect exactly one `read-bin-fallback` finding, on the invocation line.
