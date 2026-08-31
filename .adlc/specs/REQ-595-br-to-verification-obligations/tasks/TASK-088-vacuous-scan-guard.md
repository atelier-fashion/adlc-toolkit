---
id: TASK-088
title: "lint-skills: fail a run that scanned zero files (BR-5 vacuous-run guard)"
status: complete
parent: REQ-595
created: 2026-08-31
updated: 2026-08-31
dependencies: []
repo: adlc-toolkit
---

## Description

`tools/lint-skills/check.py` currently returns `min(len(findings), 255)`. A run
that walks zero `SKILL.md` files produces zero findings and exits **0** — a
confident green from a scan that did no work. That is the REQ-435 vacuous-scan
class, and it is the `structural-check` half of BR-5.

REQ-435 fixed the vacuous *walk* (the skip-list no longer swallows a root that
itself sits under `.worktrees`). It left the vacuous *result* unguarded. This
task closes that: report files scanned, and exit non-zero when the count is zero.

This is the one surface this REQ touches beyond BR-7's list — see ADR-3 for the
reconciliation (`tools/lint-skills` is not a skill; the requirement's External
Dependencies names it as the `structural-check` execution surface, and BR-5
defines the work unit as "files scanned by the lint invocation").

## Files to Create/Modify

- `tools/lint-skills/check.py` — have `run()` report the scanned-file count
  alongside findings; `main()` emits the count and returns a distinct non-zero
  exit status when zero files were scanned
- `tools/lint-skills/tests/test_check.py` — add the vacuous-scan regression (empty
  root → non-zero) and its benign counterpart (populated root → 0)
- `tools/lint-skills/README.md` — document the scanned-count line and the
  zero-scanned exit status

## Acceptance Criteria

- [ ] `check.py --root <empty-dir>` exits **non-zero** and says why (AC-7, BR-5)
- [ ] `check.py --root <populated-clean-root>` still exits **0** — the benign path
      (LESSON-440); a guard validated only against its firing input ships broken
- [ ] The scanned-file count is emitted so a caller can read the work done, not
      just infer it from the exit status (BR-5: "reports files scanned")
- [ ] The zero-scanned exit status is distinguishable from an ordinary
      findings-count exit, so a caller can tell "vacuous" from "N findings"
- [ ] Existing tests in `tools/lint-skills/tests/` continue to pass unchanged
- [ ] `README.md` documents both the count line and the new exit status
- [ ] `pytest tools/lint-skills/tests/ -q` passes with a **non-zero collected
      count** — a green suite that ran zero cases is the same vacuous failure this
      task exists to close

## Technical Notes

`run()` currently returns `list[Finding]`. Return the count alongside it rather
than recomputing the walk in `main()` — walking twice would let the two counts
disagree.

`find_skill_files` is a generator; count as it is consumed inside `run()`, not by
materializing a second list.

Pick an exit status that cannot collide with a findings count. Findings return
`min(len(findings), 255)`, so 1..255 are all taken by the ordinary path. Reserve a
distinct value and document it — note that POSIX exit statuses are 8-bit, so the
choice has to live inside 0..255 rather than above the findings range.

Do not name a local variable `status` (BR-8 / LESSON-335) even in Python — the
constraint is repo-wide convention, and the same file's shell wrapper is subject
to it.

The empty-root fixture must be a genuinely empty `tmp_path`, not a directory of
skipped files — the point is zero *scanned*, and a root full of skipped files
exercises a different branch worth its own case if cheap.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | `tools/lint-skills/tests/test_check.py` — empty-root case asserts non-zero exit; populated-root case asserts exit 0 | yes |
| AC-7 | test-case | `tools/lint-skills/tests/test_check.py` — empty-root case (the REQ-435 vacuous-scan regression) | no |
| BR-8 | structural-check | `tools/lint-skills`: full-root run over the repo, including this file's `check.sh` wrapper | no |

Kind is `test-case` for BR-5 and AC-7 because this task's surface includes
`check.py` and `test_check.py` — not all-`.md` — so BR-11's surface branch
resolves to a behavioral test, and `tools/lint-skills` has a real pytest runner
whose layout the artifact paths follow. BR-8's row stays `structural-check`
because the shell-safety constraint is enforced by the linter, not by a test.

The `benign_path: yes` on BR-5 is the must-not-fire case required by BR-4 for a
detector-shaped rule: the guard must reject an empty scan **and** stay silent on
a populated one. Without it the guard could fail every run and still pass a suite
that only ever pointed it at an empty directory (LESSON-440).
