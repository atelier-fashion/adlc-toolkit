# Fixture: retired shapes left in COMMENTS — no finding (REQ-609 verify D3)

The benign twin of `read-bin-comment-guard`. Everything that runs here is the
post-REQ-609 shape; what is commented out is the history of how it got there,
which is the ordinary way a call site is edited. A comment is not an
invocation and not a second resolver: it hands nothing to anything.

Both retired shapes appear below, each behind a `#`, so this fixture is a real
control for the comment rule rather than a restatement of `read-bin-guarded`.
The `:-` default is deliberately not the bare name — REQ-609 AC-8 greps the
repo for that spelling and a fixture is not exempt from the grep.

```sh
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
case "$ADLC_READ_BIN" in /*) ;; *) echo "/example: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing" >&2; exit 1 ;; esac
# was: "${ADLC_READ_BIN:-/opt/adlc/bin/reader}" --no-warn --paths ./notes.md
#      "$ADLC_READ_BIN" --no-warn --paths ./notes.md --question "summarize"
command "$ADLC_READ_BIN" --no-warn --paths ./notes.md --question "summarize"
```

Expect zero findings of any kind.
