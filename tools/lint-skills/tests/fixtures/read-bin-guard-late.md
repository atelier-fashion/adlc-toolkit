# Fixture: the guard placed AFTER the invocation — must be flagged (REQ-609 BR-12)

The correct literal is present, so a presence-only check would call this clean.
It is not: with an unusable `ADLC_READ_BIN` the invocation fails on its own and
the stub is never reached, which makes every runtime assertion pass while the
actual contract — refuse BEFORE the corpus is handed over — is broken. Only the
ORDER distinguishes the two.

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
command "$ADLC_READ_BIN" --no-warn --paths ./notes.md --question "summarize"
case "$ADLC_READ_BIN" in /*) ;; *) echo "/example: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing" >&2; exit 1 ;; esac
```

Expect exactly one `read-bin-fallback` finding, on the invocation line.
