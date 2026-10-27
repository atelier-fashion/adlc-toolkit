# Fixture: lesson-check-order — /bugfix with no harness line above the check fence (BR-15).

`bugfix-good.md` with the provenance-classifying-harness line moved from above
the `adlc_lesson_check` fence to below it. A line after the fence tells the
model nothing before it runs the fence, so the ONLY finding is
`missing-harness-line`, on the check fence's opening line.

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

```sh
if [ -f .adlc/partials/lesson-check.sh ]; then . .adlc/partials/lesson-check.sh; else . ~/.claude/skills/partials/lesson-check.sh; fi
adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md
```

**Provenance-classifying harness (BUG-228):** on a harness that pins the session, validate in-model and run none of the fence above.

**Pre-push recheck.**

```bash
if [ -f .adlc/partials/id-recheck.sh ]; then . .adlc/partials/id-recheck.sh; else . ~/.claude/skills/partials/id-recheck.sh; fi
LESSON_ID=$(printf 'LESSON-%03d' "$LESSON_NUM")
if ! adlc_recheck_id lesson "$LESSON_ID"; then
  echo "Halting: $LESSON_ID collides on the remote" >&2
  exit 1
fi
```
