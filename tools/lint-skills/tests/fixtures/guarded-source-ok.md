# Fixture: every benign sourcing shape (REQ-610 BR-5 benign path)

The must-not-fire control for `unguarded-source`. A check that only ever fires
is not evidence of anything; these are the shapes that are legitimately in the
corpus and must stay clean.

The canonical spelling in an `sh` fence — the one accepted form. The repo-local
copy is TESTED before it is sourced, so a missing vendored partial takes the
`else` arm instead of exiting the shell, and a present-but-broken one fails
loudly at its own `.` instead of being silently re-sourced from canonical.
The fallback operand is `"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"` (REQ-669
BR-5), and the fence's root line sits above the first use, which keeps
`toolkit-root-line` silent. The REQ-610 operand under `~/.claude/skills` is no
longer accepted (TASK-124); `unguarded-source-fence` carries it as must-fire.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
if [ -f .adlc/partials/intake.sh ]; then . .adlc/partials/intake.sh; else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi  # vendored first
```

```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -n "$SOME_MARKER" ]; then
  if [ -f .adlc/partials/trial-merge.sh ]; then . .adlc/partials/trial-merge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/trial-merge.sh"; fi
fi
```

The same spelling in a `bash` fence and in a `shell` fence: the label is
irrelevant to this check in both directions.

```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi
```

```shell
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/id-alloc.sh ]; then . .adlc/partials/id-alloc.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-alloc.sh"; fi
```

A trailing shell comment on a canonical line is allowed, and so is leading
indentation inside a conditional block.

```sh
if [ -n "$SOME_MARKER" ]; then
  ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
  if [ -f .adlc/partials/trial-merge.sh ]; then . .adlc/partials/trial-merge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/trial-merge.sh"; fi  # vendored first
fi
```

The executable-partial macro form (partials README model 1) needs no `[ -f ]`
guard and must not be flagged: its command is `sh`, not `.`, so an absent file
is an ordinary command failure (exit 127) rather than a fatal special-built-in
failure, and the `||` arm does run.

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

```sh
sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh
```

A source through a variable path is outside this check's remit even when the
path happens to contain `partials/`: the rule prescribes the toolkit's two-level
convention, and a consumer's own sibling resolution behind its own `[ -f ]` is
that author's guard to write (a two-level spelling here would point at a
`~/.claude/skills/partials/<their-name>.sh` that does not exist).

```sh
if [ -f "$ADLC_PARTIALS/partials/helper.sh" ]; then . "$ADLC_PARTIALS/partials/helper.sh"; fi
. "$HERE/../partials/helper.sh"
```

Comment lines hand nothing to any shell, and a path mentioned without a `.` in
front of it is not a source at all.

```sh
# the adapter surface lives in .adlc/partials/forge.sh
# . .adlc/partials/forge.sh — the pre-REQ-610 shape, kept beside its replacement
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
```

Expect zero findings of any kind.
