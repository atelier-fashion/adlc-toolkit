---
id: TASK-207
title: "Wire /wrapup to the chain"
status: complete
parent: REQ-660
created: 2026-10-30
updated: 2026-10-30
dependencies: ['TASK-203', 'TASK-206']
repo: adlc-toolkit
---

## Description

Persist the format through the flag file, pass `--format`, and rename the flag-file wording (BR-13, BR-14, AC-3, AC-11).

## Files to Create/Modify

- `wrapup/SKILL.md` — Step 1 prose, the 1b fence, the step 2 fence, flag-file wording
- `partials/tests/session-transcript.test.sh` — skill_wiring covers the format mark and flag

## Acceptance Criteria

- [ ] `wrapup/SKILL.md` stays under 500 lines
- [ ] `--format "$FORMAT"` follows `-o "$TMPFILE"`
- [ ] Absent `format` reads as `claude`, so the close-out block needs no edit
- [ ] The capture rules, `--question` text and `invoked`/`exit` marks are byte-unchanged
- [ ] `tools/lint-skills/check.sh` is clean

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-13 | structural-check | `tools/lint-skills/check.sh: lesson-check-order` | no |
| BR-14 | structural-check | `tools/lint-skills/check.sh: cross-fence-fn, unguarded-source, skill-line-budget` | no |
| AC-3 | test-case | `partials/tests/session-transcript.test.sh::skill_wiring` | no |
| AC-11 | structural-check | `tools/lint-skills/check.sh: lesson-check-order` | no |

## Technical Notes

In the 1b fence, after `JSONL=$(adlc_transcript_find "<mark>") || JSONL=""`, add `FORMAT=$(adlc_transcript_format "$JSONL" 2>/dev/null) || FORMAT=""` and mark both. In step 2: `FORMAT=$("$DELEGATE_TOOLS"/skill-flag.sh read "$flag" format)` then `[ -n "$FORMAT" ] || FORMAT=claude`. Skill text must name no harness home (`no-harness-path`): say "the harness roots". The `<!-- adlc-home: claude-code -->` marker on the BUG-253 paragraph stays while that paragraph names the Claude path.

## Dependencies

TASK-203, TASK-206
