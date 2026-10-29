# Fixture: lesson-check-order — /wrapup question missing one capture-rules line.

`wrapup-good.md` with rule 2 dropped from the delegated `--question` string. The
block itself is unchanged (and still byte-equal to `bugfix-good.md`'s), so the
ONLY finding is `rules-line-not-in-question`, on rule 2's line in the block.

### Step 4: Capture Knowledge

The delegated call passes the rules inside its double-quoted `--question`:

```bash
TMPFILE=$(mktemp -t adlc-wrapup.XXXXXX) || exit 1
case "$ADLC_READ_BIN" in /*) ;; *) echo "refusing a non-absolute ADLC_READ_BIN" >&2; exit 1 ;; esac
command "$ADLC_READ_BIN" --no-warn --paths "$TMPFILE" --question "Propose a lesson draft. Lesson capture rules (fixture): 0. Declare kind: process or domain. 1. Cite the moment: put it in evidence. 3. NO_ENTRY is a valid answer: never pad. Granularity: aim between."
```

**Fallback drafting** uses the same rules:

<!-- lesson-capture-rules -->
Lesson capture rules (fixture):
0. Declare kind: process or domain.
1. Cite the moment: put it in evidence.
2. Declare the contrast: high, medium or low.
3. NO_ENTRY is a valid answer: never pad.
Granularity: aim between.
<!-- /lesson-capture-rules -->

**Write and check**

<!-- lesson-write-point -->
Write `.adlc/knowledge/lessons/LESSON-<id>-<slug>.md` from the lesson template.

**Provenance-classifying harness (BUG-228):** on a harness that pins the session, validate in-model and run none of the fence below.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/lesson-check.sh ]; then . .adlc/partials/lesson-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lesson-check.sh"; fi
adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md
```

**Pre-push recheck.** The call does not start its line:

```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/id-recheck.sh ]; then . .adlc/partials/id-recheck.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-recheck.sh"; fi
LESSON_ID=$(printf 'LESSON-%03d' "$LESSON_NUM")
if ! adlc_recheck_id lesson "$LESSON_ID"; then
  echo "Halting: $LESSON_ID collides on the remote" >&2
  exit 1
fi
```
