# Fixture: lesson-check-order — the only write point above the check is inside an example fence.

`bugfix-good.md` with its own-line write point moved BELOW the check fence, and
an example block above the check fence that shows the marker on a line of its
own — inside a ```` ```markdown ```` fence. A marker in a fence of any language
is an example, not an anchor (LESSON-404), so the real write point is the one
below the check and the ONLY finding is `check-before-write-point`, on the
check fence's opening line. Counting the fenced decoy would make this pass.

**Step 4 — Capture knowledge.**

<!-- lesson-capture-rules -->
Lesson capture rules (fixture):
0. Declare kind: process or domain.
1. Cite the moment: put it in evidence.
2. Declare the contrast: high, medium or low.
3. NO_ENTRY is a valid answer: never pad.
Granularity: aim between.
<!-- /lesson-capture-rules -->

The write instruction is anchored like this:

```markdown
<!-- lesson-write-point -->
**Write the lesson** now.
```

**Validate the draft** with the schema check below.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/lesson-check.sh ]; then . .adlc/partials/lesson-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lesson-check.sh"; fi
adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md
```

<!-- lesson-write-point -->
**Write the lesson** now — too late, the schema check above already ran.

**Pre-push recheck.**

```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/id-recheck.sh ]; then . .adlc/partials/id-recheck.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-recheck.sh"; fi
LESSON_ID=$(printf 'LESSON-%03d' "$LESSON_NUM")
if ! adlc_recheck_id lesson "$LESSON_ID"; then
  echo "Halting: $LESSON_ID collides on the remote" >&2
  exit 1
fi
```
