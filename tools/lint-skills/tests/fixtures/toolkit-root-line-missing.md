# Fixture: a fence reads ToolkitRoot with no root line above the read (REQ-669 ADR-1)

Every fence below except the first reads `$ADLC_TOOLKIT_ROOT` before any root
line in that fence. Each is one `toolkit-root-line` finding, on its first read.

No root line at all: on the symlink route the operand is `/partials/forge.sh`.

```sh
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
```

The root line is there, but only after the first read.

```sh
echo "root is $ADLC_TOOLKIT_ROOT"
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
```

The braced read, with no root line:

```bash
python3 "${ADLC_TOOLKIT_ROOT}/tools/adlc/adlc.py" doctor
```

Across fences. This one is clean: it carries the root line.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/intake.sh ]; then . .adlc/partials/intake.sh; else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi
```

This later fence leans on it. Fenced blocks share no shell state, and the
export does not cross them either, so the read is empty at run time:

```sh
ls "$ADLC_TOOLKIT_ROOT/templates/across-fences"
```

Expect exactly four `toolkit-root-line` findings and no other finding of any
kind.
