# Fixture: every benign ToolkitRoot shape (REQ-669 ADR-1 benign path)

The must-not-fire control for `toolkit-root-line`. Each fence that reads
`$ADLC_TOOLKIT_ROOT` carries the canonical root line, byte-exact, above its
first read.

The root line, then the guarded source with the ToolkitRoot operand:

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
adlc_forge_pr_view 123
```

A `bash` fence that reads the root several times, braced and unbraced, and
hands it to a toolkit file. A comment above the root line names the variable;
comments are not reads.

```bash
# the root this fence resolves is printed below as $ADLC_TOOLKIT_ROOT
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
echo "$ADLC_TOOLKIT_ROOT"
python3 "${ADLC_TOOLKIT_ROOT}/tools/adlc/adlc.py" doctor
```

Indented inside a list item, as fences under numbered steps are:

1. Run the step.

   ```shell
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/id-alloc.sh ]; then . .adlc/partials/id-alloc.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-alloc.sh"; fi
   ```

A second fence that reads the root carries its own root line; it does not lean
on the fence above.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
ls "$ADLC_TOOLKIT_ROOT/templates"
```

A fence that never names the variable needs no root line.

```sh
echo "no toolkit-owned file is read here"
```

Prose may name `$ADLC_TOOLKIT_ROOT/agents/<name>.md` freely, and a non-shell
fence is not read, even when it shows a variant of the line:

```text
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills}"
```

Expect zero findings of any kind.
