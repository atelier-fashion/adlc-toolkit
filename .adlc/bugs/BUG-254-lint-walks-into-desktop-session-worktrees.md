---
id: BUG-254
title: "lint-skills walks into .claude/worktrees session checkouts"
status: resolved
severity: medium
created: 2026-10-29
updated: 2026-10-29
component: "tools/lint-skills"
domain: "adlc"
stack: ["python"]
concerns: ["correctness"]
tags: ["lint", "worktrees", "find-skill-files", "scan-root", "desktop-app"]
introduced_by: []
attribution: none
---

## Description

`tools/lint-skills/check.py` fails on the primary checkout
(`~/GitHub/adlc-toolkit`) with 125 findings, every one in a file under
`.claude/worktrees/<name>/...`. Those are the Claude desktop app's session
worktrees: whole checkouts of other branches, not part of the tree being linted.
The checks that report them are `dispatch-has-fallback` (60), `unguarded-source`
(57) and `canonical-helper` (8), and `skill-md-corruption` reports 136 scanned
SKILL.md files where the tree has 17.

Not a regression from REQ-666: the lint at `f57c876` reports the same three
checks on the same tree (under the old name `dispatch-fallback`). A `/proceed`
runner inside `.worktrees/REQ-xxx` never sees it, because that checkout has no
`.claude/worktrees/`.

## Reproduction Steps

1. From the primary checkout, with at least one desktop session worktree under
   `.claude/worktrees/`, run `sh tools/lint-skills/check.sh`.
2. Filter stdout for lines starting with `.claude/worktrees/`.

## Expected Behavior

Exit 0 on a clean tree; nested session checkouts are not walked.

## Actual Behavior

Exit 125, 125 findings, all from nested session checkouts.

## Environment

- Platform: macOS, Claude desktop app (Code tab)
- Version: `main` at d2eadd7

## Root Cause

Prior lessons consulted:
- LESSON-737 — `git status` and `git diff` refresh the index, so a check that promises to write nothing must run git with --no-optional-locks (score 5)
- LESSON-743 — git -C <dir> answers for the nearest enclosing repository, not for <dir> — test <dir>/.git before asking git whether a directory is a checkout (score 5)
- LESSON-744 — Credential redaction chains match inside ordinary identifiers — validate identifier fields by format instead of redacting them (score 5)
- LESSON-749 — When two checks split one pattern, hand a line over only where the receiving check reads the file, or the receiver's exceptions become lines nobody checks (score 5)
- LESSON-614 — A governance config needs a recognizer, not a reader — and a differential oracle, not one author's corpus (score 5)

None of the retrieved five describes this failure. The governing rule is
LESSON-019 (applied in REQ-436 ADR-5 and REQ-435): test skip names only on the
components strictly below the scan root, never on the root's own.

`find_skill_files` (`tools/lint-skills/check.py`) is the one walk behind every
per-file check and the scanned-file count. It skips a SKILL.md only when a
directory component below the root is in `SKIP_DIR_PARTS` (`.git`,
`.worktrees`, `node_modules`). The desktop app's `.claude/worktrees/` matches
none of those, so `root.rglob("SKILL.md")` reached every nested session
checkout and linted its (older) skills. The `tools/**` walk
(`_toolkit_path_tools_files`) was already safe because it prunes hidden
directories; the per-root `*/SKILL.md` surface was safe because it is one level
deep. `tests/test_check.py::test_repo_root_unguarded_source_and_root_line_clean`
had papered over the gap by dropping output lines that start with `.claude/`.

Attribution: `git blame` on the walk (lines 1038–1057) and `SKIP_DIR_PARTS`
returns two candidates, REQ-425 (the original walk and skip list) and REQ-436
(the root-relative skip). Neither is recorded: with 2+ candidates the operator
selects. Arguably neither introduced it; the walk predates the desktop app's
`.claude/worktrees/` layout.

## Resolution

Added `SKIP_DIR_SEQUENCES = ((".claude", "worktrees"),)` and a helper,
`_skipped_below_root`, which `find_skill_files` now calls on the directory
components below the resolved root. It skips a `SKIP_DIR_PARTS` member, as
before, or a run of consecutive components matching a sequence. Only the pair
is skipped: `worktrees` alone is too common a name, and a project's own
`.claude/skills/<name>/SKILL.md` is still linted. The root's own components are
never tested, so a run whose root sits inside `.claude/worktrees/<name>` (every
desktop session) still lints itself, and the REQ-595 BR-5 exit 255 on a zero
count is untouched.

Verified: the new `test_nested_session_worktree_skipped` fails on the old walker
(counts 3 files and reports the sentinel) and passes on the fix; the primary
checkout lints with exit 0 and 17 scanned files (was 125 and 136); this session
worktree, a root inside `.claude/worktrees/`, lints with exit 0 and 17 files;
`pytest tools/lint-skills` passes (702).

## Files Changed

- `tools/lint-skills/check.py` — `SKIP_DIR_SEQUENCES`, `_skipped_below_root`, `find_skill_files` uses it; docstring notes BUG-254.
- `tools/lint-skills/tests/test_check.py` — `test_nested_session_worktree_skipped`, `test_root_inside_session_worktree_still_scanned`; the repo-root test no longer filters `.claude/` lines.
- `.adlc/bugs/BUG-254-lint-walks-into-desktop-session-worktrees.md` — this report.

## Deployment

No deploy target: the toolkit is live on merge, through the `~/.claude/skills`
symlink to the primary checkout. Lesson captured: LESSON-750.
