---
name: fixture-agent
description: A fixture agent file that hands a corpus to the delegate.
---

# Fixture: an `agents/*.md` fence carrying the retired shape (REQ-609)

`agents/delegate-pre-pass.md` hands a redacted diff to the delegate exactly as a
skill does, and it is not a `SKILL.md`, so before this the structural guard could
not see the very fences BR-12 was written for. This fixture is staged under
`agents/` and must draw findings from `read-bin-fallback`.

It also carries a `local` declaration in an `sh` fence — a `posix-fence` finding
on a `SKILL.md`, and deliberately NOT one here: the agents walk is scoped to the
one check, not a widening of the skill walk.

```sh
"${ADLC_READ_BIN:-/opt/adlc/bin/reader}" --no-warn --paths ./notes.md --question "summarize"
```

```sh
helper() {
    local unused=1
    echo "$unused"
}
```

Expect exactly one `read-bin-fallback` finding and nothing else. The default is
deliberately not the bare name: REQ-609 AC-8 greps the repo for the bare-name
spelling outside `partials/tests/fixtures/` and `.adlc/specs/`, and a fixture is
not exempt from that grep.
