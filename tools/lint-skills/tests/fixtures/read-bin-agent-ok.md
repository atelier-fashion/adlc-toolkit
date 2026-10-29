---
name: fixture-agent-ok
description: A fixture agent file whose delegate fence is the post-REQ-609 shape.
---

# Fixture: a clean `agents/*.md` delegate fence (REQ-609)

Guard first, `command` on the invocation, no `:-` default. It also carries a
`local` in an `sh` fence, which a `SKILL.md` would draw a `posix-fence` finding
for — the positive control proving the agents walk really is scoped to
`read-bin-fallback` rather than being a second skill walk in disguise.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi
case "$ADLC_READ_BIN" in /*) ;; *) echo "/example: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing" >&2; exit 1 ;; esac
command "$ADLC_READ_BIN" --no-warn --paths ./notes.md --question "summarize"
```

```sh
helper() {
    local unused=1
    echo "$unused"
}
```

Expect zero findings.
