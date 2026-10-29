---
name: alpha
description: Fixture skill — catch issues before /review (/adlc:review on the plugin install)
---

# /init — a heading naming the skill is a noun

## Ethos

!`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md || echo No ethos found — run /init, or /adlc:init on the plugin install, to vendor .adlc/ETHOS.md`

## Prerequisites

If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` (`/adlc:init` on the plugin install) first."

| Skill | Description |
|-------|-------------|
| `/init` | Bootstrap `.adlc/` structure in a new repo |
| `/status` | Show current state of all ADLC work |
| `/review` | Multi-agent code review |

The `/init` skill copies the templates. Unlike `/status`, which reads the local checkout, this one does not.
The formal `/review` step comes after this one. Read `$ADLC_TOOLKIT_ROOT/init/SKILL.md` and `init/SKILL.md`.
- If no issues: "Ready for `/review` (`/adlc:review` on the plugin install)"

```sh
case "$ADLC_READ_BIN" in /*) ;; *) echo "/alpha: not absolute (re-run install.sh --with-delegation, and /init (/adlc:init on the plugin install) to refresh the vendored gate)" >&2; exit 1 ;; esac
```
