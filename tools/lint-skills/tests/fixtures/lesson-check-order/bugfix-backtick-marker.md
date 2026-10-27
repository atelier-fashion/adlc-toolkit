# Fixture: lesson-check-order — the write-point marker appears only as a decoy (LESSON-404).

`bugfix-good.md` with its own-line write-point marker replaced by two decoys,
both ABOVE the check fence so that accepting either would make the ordering
pass: a backticked prose mention, and the bare marker followed by prose on the
same line. Neither is a line that IS the marker, so the ONLY finding is
`missing-write-point`.

**Step 4 — Capture knowledge.**

<!-- lesson-capture-rules -->
Lesson capture rules (fixture):
0. Declare kind: process or domain.
1. Cite the moment: put it in evidence.
2. Declare the contrast: high, medium or low.
3. NO_ENTRY is a valid answer: never pad.
Granularity: aim between.
<!-- /lesson-capture-rules -->

The write instruction is anchored by `<!-- lesson-write-point -->` on a line of its own.
<!-- lesson-write-point --> **Write the lesson** now, before the schema check and the recheck below.

**Provenance-classifying harness (BUG-228):** on a harness that pins the session, validate in-model and run none of the fence below.

```sh
if [ -f .adlc/partials/lesson-check.sh ]; then . .adlc/partials/lesson-check.sh; else . ~/.claude/skills/partials/lesson-check.sh; fi
adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md
```

**Pre-push recheck.**

```bash
if [ -f .adlc/partials/id-recheck.sh ]; then . .adlc/partials/id-recheck.sh; else . ~/.claude/skills/partials/id-recheck.sh; fi
LESSON_ID=$(printf 'LESSON-%03d' "$LESSON_NUM")
if ! adlc_recheck_id lesson "$LESSON_ID"; then
  echo "Halting: $LESSON_ID collides on the remote" >&2
  exit 1
fi
```
