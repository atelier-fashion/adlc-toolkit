# Fixture: lesson-check-order — the good /wrapup shape (REQ-646 ADR-5).

Staged as `wrapup/SKILL.md`. The double-quoted `--question` of the delegated
call carries every capture-rules line verbatim and in block order, the block
sits on own-line markers, and the write point, the check fence and the recheck
fence come in that order.

### Step 4: Capture Knowledge

The delegated call passes the rules inside its double-quoted `--question`:

```bash
TMPFILE=$(mktemp -t adlc-wrapup.XXXXXX) || exit 1
case "$ADLC_READ_BIN" in /*) ;; *) echo "refusing a non-absolute ADLC_READ_BIN" >&2; exit 1 ;; esac
command "$ADLC_READ_BIN" --no-warn --paths "$TMPFILE" --question "Propose a lesson draft. Lesson capture rules (fixture): 0. Declare kind: process or domain. 1. Cite the moment: put it in evidence. 2. Declare the contrast: high, medium or low. 3. NO_ENTRY is a valid answer: never pad. Granularity: aim between."
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

**Validate the draft** with the schema check below.

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
