# Fixture: a BRACED invocation with no guard — must be flagged (REQ-609 verify D3)

The braced spelling `${ADLC_READ_BIN}` names the same variable as
`$ADLC_READ_BIN`, so invoking it is the same invocation — and a check that
recognises one spelling and not the other is a check the next call site can
step around by accident. This fence carries the `command` prefix and correct
quoting but NO absolute-path guard, so the only thing it can draw is the guard
finding, which it can only draw if the braced form is recognised as an
invocation in the first place.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi
command "${ADLC_READ_BIN}" --no-warn --paths ./notes.md --question "summarize"
```

Expect exactly one `read-bin-fallback` finding, on the invocation line.
