---
id: TASK-005
title: "Dual-shell test harness for partials/intake.sh"
status: draft
parent: REQ-594
created: 2026-08-31
updated: 2026-08-31
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

Add `partials/tests/intake.test.sh` following the established harness conventions and
register it in `partials/tests/run.sh`. Fully offline — no network, no real `adlc-read`
invocation.

## Files to Create/Modify

- `partials/tests/intake.test.sh` — NEW
- `partials/tests/run.sh` — MODIFY: register the harness in `run_all`

## Acceptance Criteria

- [ ] Harness follows the `forge.test.sh` shape: `HERE`/`PARTIALS`/`ROOT` resolution, `pass`/`fail`/`check`/`contains` helpers, one line per case, exit 0 iff every case passes.
- [ ] Registered in `run.sh`'s `run_all` call so `sh partials/tests/run.sh` runs it under both bash and zsh.
- [ ] Cases cover `adlc_intake_detect`: the `--intake` flag trigger, the file-path trigger, the >25-line trigger, and the negative case (a one-line request triggers nothing — AC-1).
- [ ] Cases cover `adlc_intake_segment`: exact segment count for a known line count, the 40-segment boundary, and the over-budget refusal returning 3 with the size named (AC-10).
- [ ] Cases cover `adlc_intake_redact`: each of the five credential patterns is replaced, and the `.bak` file is removed.
- [ ] Cases cover `adlc_intake_sections`: the emitted list excludes `Description`, `Assumptions`, `Open Questions`, and `Retrieved Context`, and includes the five sections the `Gap.section` enum names.
- [ ] A fixture case proves a delegate response citing `REQ-999999` or a path containing `..` is rejected by the validation regexes (AC-7).
- [ ] A fixture case proves a response missing a middle segment is detected by reconciliation (AC-9).
- [ ] Passes under **both** `bash` and `zsh` (the run.sh dual-shell pass).
- [ ] `sh tools/lint-skills/check.sh` exits 0.

## Technical Notes

`run.sh`'s harness list lives in positional parameters, never a space-joined string —
zsh does not word-split, and collapsing the list into one bogus filename is BUG-118
(masked while the list had a single element, LESSON-399). Add the new harness as another
quoted positional argument to `run_all`, matching the existing call.

The regex-rejection and segment-omission cases (AC-7, AC-9) test validation logic that
lives in `spec/SKILL.md` prose rather than in the partial. Test them at the level the
partial exposes: if the rejection regexes are not partial functions, assert the fixture
strings against the same regexes the SKILL.md specifies, so a future divergence between
the documented regex and the tested one is visible. Note the coupling in a comment.

Use `mktemp -d` sandboxes for the file-path and segmentation cases; clean up on EXIT.
