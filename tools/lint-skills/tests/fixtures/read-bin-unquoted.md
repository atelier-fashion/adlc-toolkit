# Fixture: an UNQUOTED invocation — must be flagged (REQ-609 verify D3)

The guard is correct and the `command` prefix is present, so this fixture
isolates the quoting half of the contract. `command $ADLC_READ_BIN --paths …`
hands the resolved path to the shell's word-splitting and pathname expansion
before it is ever a command name: a resolver that returned
`/Users/a b/bin/adlc-read` becomes two arguments (`/Users/a` runs, `b/bin/…`
is its first argument), and one containing a glob character becomes whatever
happens to match in the current directory, or — under `sh` and `bash` — the
unmatched literal.

This is the shape BUG-209 recorded, written with the guard in place: the
resolver proved a file is on disk, and the call site then asks the shell to
re-derive which file that was.

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
case "$ADLC_READ_BIN" in /*) ;; *) echo "/example: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing" >&2; exit 1 ;; esac
command $ADLC_READ_BIN --no-warn --paths ./notes.md --question "summarize"
```

Expect exactly one `read-bin-fallback` finding, on the invocation line.
