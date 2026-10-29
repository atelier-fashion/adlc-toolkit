# Fixture: unguarded partial sourcing inside fences (REQ-610 BR-3/BR-5)

Eleven wrong ways to source a partial, one per fence, each a single
`unguarded-source` finding on its own line. The two retired-spelling lines match
BOTH of the check's rules and must still yield ONE finding each, not two — the
second pass is deduped by line number.

The retired two-level spelling in an `sh` fence. `.` is a POSIX special
built-in: the source failure exits a non-interactive `sh` outright, so the `||`
arm never runs and the rest of the fence never executes.

```sh
. .adlc/partials/forge.sh 2>/dev/null || . ~/.claude/skills/partials/forge.sh
echo "forge adapter loaded"
```

The same line in a `bash` fence. Unlike `posix-fence`, this check does NOT
exempt `bash` (REQ-610 ADR-2): the fence label does not choose the shell that
executes the block — consumers and `run.sh` run fences under `/bin/sh`
regardless of the label — and a fatal `.` is a property of the executing shell.

```bash
. .adlc/partials/intake.sh 2>/dev/null || . ~/.claude/skills/partials/intake.sh
```

The `&&`/`||` chain. It double-sources whenever the repo-local copy's final
status is non-zero, which for a function-defining partial is whatever its last
top-level statement happened to return — a property no partial author is
thinking about.

```sh
[ -f .adlc/partials/id-alloc.sh ] && . .adlc/partials/id-alloc.sh || . ~/.claude/skills/partials/id-alloc.sh
```

A guard whose name does not match what it sources: the `[ -f ]` tests
`forge.sh`, and the `else` arm sources `intake.sh`, so on a machine with a
vendored `forge.sh` the fallback never loads the file the guard proved absent.
The backreference in `CANONICAL_SOURCE_RE` is what catches this; without it the
shape reads as guarded.

```sh
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . ~/.claude/skills/partials/intake.sh; fi
```

The bash-only `source` spelling. Not fatal under bash — but `dash` has no
`source` builtin at all, so both arms fail and every function the partial
defines is silently undefined until a later `command not found`.

```sh
source .adlc/partials/forge.sh 2>/dev/null || source ~/.claude/skills/partials/forge.sh
```

The `$HOME` spelling of the canonical operand. The canonical form never uses it,
so every occurrence is, by construction, a finding — and the regex branch that
recognises `$HOME`/`${HOME}` is otherwise unexercised.

```sh
[ -f .adlc/partials/forge.sh ] || . ${HOME}/.claude/skills/partials/forge.sh
```

A quoted operand: quoting does not change what `.` does, and `"~/…"` does not
even tilde-expand, so this shape is doubly wrong.

```sh
. ".adlc/partials/forge.sh" 2>/dev/null || . "~/.claude/skills/partials/forge.sh"
```

The REQ-669 operand, `"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"`, gets no
exemption from the guard. Each fence below carries the root line, so
`toolkit-root-line` is silent and the only findings are the source lines.

The new operand `||`-chained behind the repo-local copy: the same fatal shape as
the retired one.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
. .adlc/partials/lane-check.sh 2>/dev/null || . "$ADLC_TOOLKIT_ROOT/partials/lane-check.sh"
```

The new operand sourced alone, with no repo-local arm: it skips the vendored
copy LESSON-441 depends on.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
. "$ADLC_TOOLKIT_ROOT/partials/conflict-bound.sh"
```

The new operand with a mismatched `<name>`: the guard tests `forge.sh` and the
`else` arm sources `intake.sh`.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi
```

The guarded REQ-610 spelling, exactly as the whole corpus wrote it before
REQ-669 TASK-124. The guard is right; the `else` arm is not. It reads
`~/.claude/skills`, which only the symlink install has, so on the plugin route
the fallback names a file that is not there. TASK-122 accepted it while the
corpus was rewritten, and TASK-124 retired that acceptance. It needs no root
line, since it never reads `$ADLC_TOOLKIT_ROOT`, so `toolkit-root-line` stays
silent here and the one finding is the source line's.

```sh
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . ~/.claude/skills/partials/forge.sh; fi
```

Expect exactly eleven `unguarded-source` findings and no other finding of any
kind.
