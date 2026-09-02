# Fixture: the resolved path copied into another variable (REQ-609 verify D3)

One hop is all it takes to leave the contract. Assigning the resolver's answer
to a second name — `READER` below — puts it somewhere nothing guards, nothing
re-checks, and nothing else in this file knows about, and every check written
against `ADLC_READ_BIN` then reads the invocation that follows as clean. The
guard here is correct and the invocation goes through `command`, which is
exactly the point: the copy is what the finding is about.

```sh
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
case "$ADLC_READ_BIN" in /*) ;; *) echo "/example: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing" >&2; exit 1 ;; esac
READER="$ADLC_READ_BIN"
command "$READER" --no-warn --paths ./notes.md --question "summarize"
```

Expect exactly one `read-bin-fallback` finding, on the assignment line.
