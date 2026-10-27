---
id: TASK-112
title: "partials/lane-check.sh: adlc_lane_check wrapper, companion doc and vocabulary block"
status: draft
parent: REQ-652
created: 2026-10-27
updated: 2026-10-27
dependencies: [TASK-111]
---

## Description

The sourced shell entry point the skills call, plus the companion doc that holds the lane vocabulary (architecture ADR-3, ADR-13).

## Files to Create/Modify

- `partials/lane-check.sh` — new. `adlc_lane_check <worktree> <base-ref>`: resolves the interpreter via `_adlc_forge_python` (sources `forge.sh` with the guarded two-level spelling), locates `lane_check.py` with the project-vendored-then-toolkit fallback, invokes it through `command`, passes its stdout and exit code through unchanged.
- `partials/lane-check.md` — new. Return contract, same-fence call protocol, rule table, defaults, what counts toward `max_files`, and the `<!-- lane-vocabulary -->` … `<!-- /lane-vocabulary -->` block (lane, trigger, actor, lane_check sets).
- `partials/tests/lane-check.test.sh` — new. Sandbox repos via an `mkrepo` helper modelled on `conflict-bound.test.sh`; a case-count floor so an empty run fails.
- `partials/tests/run.sh` — append `lane-check.test.sh` to the harness list.
- `partials/README.md` — catalogue entry for `lane-check.sh` / `lane-check.md`.

## Acceptance Criteria

- [ ] `sh partials/tests/run.sh` runs the new harness under bash, zsh, sh and dash, and it passes in all four.
- [ ] The harness covers one passing diff and one escalating diff end to end through the wrapper, and a dirty-tree error.
- [ ] The wrapper's exit code and stdout are exactly the module's (no extra lines, no swallowed stderr).
- [ ] `sh tools/lint-skills/check.sh --root .` reports no `unguarded-source`, `posix-fence` or `cross-fence-fn` findings for the new files.
- [ ] The vocabulary block is anchored to line start and lists exactly the four sets in architecture.md.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `partials/tests/lane-check.test.sh`: pass, escalate, error cases | yes |
| AC-4 | test-case | `partials/tests/lane-check.test.sh`: per-shell pass/escalate | yes |
| AC-16 | test-case | `partials/tests/lane-check.test.sh`: re-run after a new commit touching a blocked path escalates | yes |

## Technical Notes

- POSIX only, dash-clean: no `local`, no `case` inside `$( )` (LESSON-582), no arrays.
- Calling a `_`-prefixed function from forge.sh is a documented coupling (architecture ADR-3); say so in a comment next to the call and in `lane-check.md`.
- Use `command "$py" "$script" …` so a shell function named `python3` cannot intercept it (the forge.sh REQ-609 D5 rule).
- Diff base passed in by the caller is `origin/<integrationBranch>`; the partial does not fetch.
