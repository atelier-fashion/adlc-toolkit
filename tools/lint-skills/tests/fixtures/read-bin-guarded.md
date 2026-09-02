# Fixture: the post-REQ-609 call-site shape — no `read-bin-fallback` finding

The gate is sourced in the SAME fence as the check and the invocation (fenced
blocks do not share shell state), the empty case refuses before any corpus is
handed over, and the invocation reads the resolver's answer verbatim. This is
the shape `read-bin-fallback` exists to protect, so it must be clean.

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
[ -n "$ADLC_READ_BIN" ] || { echo "/example: ADLC_READ_BIN is empty — refusing to hand over the corpus (re-run install.sh --with-delegation)" >&2; exit 1; }
"$ADLC_READ_BIN" --no-warn --paths ./notes.md --question "summarize"
```

Expect zero findings of any kind.
