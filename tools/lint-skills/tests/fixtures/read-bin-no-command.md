# Fixture: an invocation missing its `command` prefix — must be flagged (REQ-609 ADR-3)

The absolute-path guard is present and correct, so this fixture isolates the
`command` half of the contract. bash and zsh both permit a function whose NAME
is an absolute path, so a bare `"$ADLC_READ_BIN" --paths …` runs that function
instead of the file the resolver proved is on disk — and the function is handed
the corpus. `command` bypasses function and alias lookup, which is why the
gate's own probe already used it; the call sites did not.

This prose spells `"$ADLC_READ_BIN" --no-warn` outside any fence and must NOT be
flagged (fences only, same posture as `forge-direct-gh`).

```sh
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
case "$ADLC_READ_BIN" in /*) ;; *) echo "/example: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing" >&2; exit 1 ;; esac
"$ADLC_READ_BIN" --no-warn --paths ./notes.md --question "summarize"
```

Expect exactly one `read-bin-fallback` finding, on the invocation line.
