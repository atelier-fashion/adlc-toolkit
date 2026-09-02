# Fixture: the resolved path handed to `eval` — must be flagged (REQ-609 verify D3)

`eval` re-parses its argument as shell source, which undoes every property the
resolver established: the path is word-split and glob-expanded, any character
in it is syntax again, and function lookup is back in play regardless of a
`command` prefix written inside the string. The guard above it is correct, so
this fixture isolates the `eval` hand-off.

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
case "$ADLC_READ_BIN" in /*) ;; *) echo "/example: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing" >&2; exit 1 ;; esac
eval "$ADLC_READ_BIN --no-warn --paths ./notes.md --question 'summarize'"
```

Expect exactly one `read-bin-fallback` finding, on the `eval` line.
