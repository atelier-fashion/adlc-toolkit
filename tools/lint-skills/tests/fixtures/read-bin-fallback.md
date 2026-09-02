# Fixture: a `${ADLC_READ_BIN:-…}` default in a shell fence — must be flagged (REQ-609 BR-12)

`partials/delegate-gate.sh` is the single resolver for `adlc-read`: it walks
`$PATH` itself and exports an absolute path or the empty string. A `:-` default
at the call site resolves the binary a second time by a weaker rule — exactly
what the `read-bin-fallback` check guards against.

This prose mentions `${ADLC_READ_BIN:-/opt/adlc/bin/reader}` outside any fence
and must NOT be flagged (fences only, same posture as `forge-direct-gh`).

The default below is deliberately not the bare name: REQ-609 AC-8 greps the repo
for the bare-name spelling outside `partials/tests/fixtures/` and `.adlc/specs/`,
and a fixture is not exempt from that grep. The check matches the expansion
operator, not one default value, so this shape fires all the same — which is the
point.

```sh
"${ADLC_READ_BIN:-/opt/adlc/bin/reader}" --no-warn --paths ./notes.md --question "summarize"
```

Expect one `read-bin-fallback` finding on the fence line.
