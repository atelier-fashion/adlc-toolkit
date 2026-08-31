---
id: TASK-xxx
title: "Task Title"
status: draft
parent: REQ-xxx
created: YYYY-MM-DD
updated: YYYY-MM-DD
dependencies: []
# repo: <repo-id>   # REQUIRED in cross-repo projects (see .adlc/config.yml).
                    # One of the ids under `repos:` in .adlc/config.yml.
                    # In single-repo projects, omit or set to the primary repo id.
---

## Description

What this task accomplishes.

## Files to Create/Modify

- `path/to/file.js` — description of changes

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Verification

<!-- OPTIONAL section (REQ-595). Emitted by /architect Step 4.5; read by
     /validate's obligation-coverage gate. A task file WITHOUT this section is
     still valid — the gate reports the gap as an advisory finding and does not
     block advancement. Delete this section if you are hand-writing a task and
     have nothing to declare. -->

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `tools/lint-skills`: sentinels, balance | no |
| AC-2 | test-case | `path/to/test_file.py::test_case_name` | yes |

- **rule** — `BR-<n>` or `AC-<n>`, referencing the parent REQ. ACs are addressed
  by **1-based ordinal** within the REQ's `## Acceptance Criteria` list, because
  the requirement template does not print AC numbers.
- **kind** — `test-case` | `structural-check`. Closed enum. `dogfood` (invoke the
  skill and inspect artifacts) is deliberately excluded: it cannot report an
  executed-work count, which the vacuous-run gate requires.
- **artifact** — for `test-case`, a test file path plus case name; for
  `structural-check`, the check surface plus the named check(s). Must resolve
  once the task is implemented.
- **benign_path** — `yes` when the obligation includes a **must-not-fire** case.
  Required for any rule describing detection, refusal, or a halt: a detector
  validated only against adversarial input ships broken and passes its own suite.

## Technical Notes

Implementation details, patterns to follow, edge cases.
