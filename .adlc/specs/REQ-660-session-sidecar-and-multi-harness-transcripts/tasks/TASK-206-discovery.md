---
id: TASK-206
title: "Sidecar and multi-root discovery"
status: complete
parent: REQ-660
created: 2026-10-30
updated: 2026-10-30
dependencies: ['TASK-204']
repo: adlc-toolkit
---

## Description

Extend `adlc_transcript_find` to the sidecar rung and four roots, add `adlc_transcript_format`, and restore the `/wrapup: session JSONL —` line (BR-1 to BR-4, BR-9, BR-16, ADR-1, ADR-2, ADR-3).

## Files to Create/Modify

- `partials/session-transcript.sh` — rung (a), rung (b) over four roots, `adlc_transcript_format`
- `partials/tests/session-transcript.test.sh` — the BR-12 matrix
- `tools/lint-skills/check.py` — file exception for the three non-Claude roots
- `tools/lint-skills/tests/test_toolkit_path.py` — the pinned exception set
- `tools/lint-skills/README.md` — exception row, additively

## Acceptance Criteria

- [ ] Every BR-12 matrix row produces the stated outcome and stderr reason under bash, zsh, sh and dash
- [ ] A sidecar naming `/etc/passwd`, a `..` path, a symlink or a deleted file is pathless, and the stderr line does not name it
- [ ] Exactly one stderr line per return 0/1
- [ ] `adlc_transcript_find` keeps its stdout-and-rc contract; malformed marks still return 2
- [ ] Lint stays clean

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `partials/tests/session-transcript.test.sh::sidecar_wins` | yes |
| BR-2 | test-case | `partials/tests/session-transcript.test.sh::rejected_paths_are_pathless` | yes |
| BR-3 | test-case | `partials/tests/session-transcript.test.sh::no_mark_refuses` | yes |
| BR-4 | test-case | `partials/tests/session-transcript.test.sh::sidecar_wins` | no |
| BR-9 | test-case | `partials/tests/session-transcript.test.sh::walk_each_root` | yes |
| BR-16 | test-case | `partials/tests/session-transcript.test.sh::rejected_paths_are_pathless` | no |
| AC-4 | test-case | `partials/tests/session-transcript.test.sh::sidecar_without_mark_falls_to_walk` | yes |
| AC-5 | test-case | `partials/tests/run.sh` | no |
| AC-6 | test-case | `partials/tests/session-transcript.test.sh::rejected_paths_are_pathless` | yes |
| AC-13 | test-case | `partials/tests/session-transcript.test.sh::no_sidecar_dir` | yes |
| BR-12 | test-case | `partials/tests/session-transcript.test.sh` | yes |

## Technical Notes

Rung (a): list with `find "$dir" -maxdepth 1 -type f ! -name '.*'` into a variable and loop with a here-doc, never a bare glob (LESSON-335) and never a pipe (variables must survive). `find` given a symlinked `$dir` with no trailing slash yields nothing. Read a value with `sed -n 's/^key=//p' "$f" | head -1`. Usable means: harness in the five-value enum; path starts with `$HOME/`; no `/../` and no trailing `/..`; `[ -f ]` and not `[ -L ]`; `$(CDPATH= cd -P -- dirname && pwd -P)` under `$(cd -P HOME && pwd -P)/`. Hold check: `command grep -qF -e "$mark" "$p"`. Dedupe the same path. Roots, in order: claude `.claude/projects/` depth 5 `*.jsonl`; codex `.codex/sessions/` depth 4 `rollout-*.jsonl`; copilot `.copilot/session-state/` depth 2 `events.jsonl`; gemini `.gemini/tmp/` depth 3 `session-*.jsonl`. Keep the `find … -mmin -60 -exec grep -lF` form and the trailing slash. Stderr carries the basename only. Lines: `/wrapup: session JSONL — matched this run's mark in <basename> via sidecar`, `… via walk:<harness>`, `/wrapup: session JSONL — no sidecar and no candidates under any harness root — REFUSING to delegate; draft from the conversation`, and a refusal naming sidecar and root candidate counts. Revise the existing `^session transcript:` assertions. `git rev-parse --show-toplevel 2>/dev/null` else `$PWD`. The `.claude` literal keeps its `# adlc-home: claude-code` marker; `.codex`, `.copilot` and `.gemini` take a `file` exception in `TOOLKIT_PATH_EXCEPTIONS` with a README row, not an adlc-home marker, which would mislabel them.

## Dependencies

TASK-204
