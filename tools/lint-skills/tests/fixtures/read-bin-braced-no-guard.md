# Fixture: a BRACED invocation with no guard — must be flagged (REQ-609 verify D3)

The braced spelling `${ADLC_READ_BIN}` names the same variable as
`$ADLC_READ_BIN`, so invoking it is the same invocation — and a check that
recognises one spelling and not the other is a check the next call site can
step around by accident. This fence carries the `command` prefix and correct
quoting but NO absolute-path guard, so the only thing it can draw is the guard
finding, which it can only draw if the braced form is recognised as an
invocation in the first place.

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
command "${ADLC_READ_BIN}" --no-warn --paths ./notes.md --question "summarize"
```

Expect exactly one `read-bin-fallback` finding, on the invocation line.
