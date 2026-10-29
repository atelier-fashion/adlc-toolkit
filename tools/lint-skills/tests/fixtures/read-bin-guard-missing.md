# Fixture: the retired `[ -n … ]` guard — must be flagged (REQ-609 BR-12)

`command` is present and there is no `:-` default, so this fixture isolates the
guard half of the contract. `[ -n "$ADLC_READ_BIN" ]` is satisfied by ANY
non-empty value — including the BARE NAME a consumer repo's stale vendored
`delegate-gate.sh` still exports on a `$PATH` hit, which the invocation then
hands back to the shell's lookup machinery. That is the resolution the canonical
gate walks `$PATH` precisely to avoid (BUG-209), so the guard must test for an
absolute path.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi
[ -n "$ADLC_READ_BIN" ] || { echo "/example: ADLC_READ_BIN is empty — refusing" >&2; exit 1; }
command "$ADLC_READ_BIN" --no-warn --paths ./notes.md --question "summarize"
```

Expect exactly one `read-bin-fallback` finding, on the invocation line.
