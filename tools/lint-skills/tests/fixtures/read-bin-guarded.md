# Fixture: the post-REQ-609 call-site shape — no `read-bin-fallback` finding

The gate is sourced in the SAME fence as the guard and the invocation (fenced
blocks do not share shell state), the guard refuses anything that is not an
absolute path before any corpus is handed over, and the invocation goes through
`command` so a function named with the resolved absolute path — which bash and
zsh both permit — cannot stand in for the file the resolver proved is there.
This is the shape `read-bin-fallback` exists to protect, so it must be clean.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi
case "$ADLC_READ_BIN" in /*) ;; *) echo "/example: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing to hand over the corpus (re-run install.sh --with-delegation, and /init to refresh the vendored gate)" >&2; exit 1 ;; esac
command "$ADLC_READ_BIN" --no-warn --paths ./notes.md --question "summarize"
```

Expect zero findings of any kind.
