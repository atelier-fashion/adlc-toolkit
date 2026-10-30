# Fixture: lesson-check-order — the good /bugfix shape (REQ-646 ADR-5).

Staged as `bugfix/SKILL.md`. Its capture-rules block is byte-equal to
`wrapup-good.md`'s, and the write point, the check fence and the recheck fence
come in that order. /bugfix has no delegated question, so the block is its only
copy of the rules.

**Step 4 — Capture knowledge.**

<!-- lesson-capture-rules -->
Lesson capture rules (fixture):
0. Declare kind: process or domain.
1. Cite the moment: put it in evidence.
2. Declare the contrast: high, medium or low.
3. NO_ENTRY is a valid answer: never pad.
Granularity: aim between.
<!-- /lesson-capture-rules -->

<!-- lesson-write-point -->
**Write the lesson** now, before the schema check and the recheck below.

**Validate the draft** with the schema check below.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/lesson-check.sh ]; then . .adlc/partials/lesson-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lesson-check.sh"; fi
adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md
```

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
