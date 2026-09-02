---
name: fixture-agent-ok
description: A fixture agent file whose delegate fence is the post-REQ-609 shape.
---

# Fixture: a clean `agents/*.md` delegate fence (REQ-609)

Guard first, `command` on the invocation, no `:-` default. It also carries a
`local` in an `sh` fence, which a `SKILL.md` would draw a `posix-fence` finding
for — the positive control proving the agents walk really is scoped to
`read-bin-fallback` rather than being a second skill walk in disguise.

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
case "$ADLC_READ_BIN" in /*) ;; *) echo "/example: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing" >&2; exit 1 ;; esac
command "$ADLC_READ_BIN" --no-warn --paths ./notes.md --question "summarize"
```

```sh
helper() {
    local unused=1
    echo "$unused"
}
```

Expect zero findings.
