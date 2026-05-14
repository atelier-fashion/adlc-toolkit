---
id: TASK-026
title: "Repo cleanup: gitignore pipeline-state.json + remove tracked copies, delete stray LESSON dup, README troubleshooting subsection"
status: complete
parent: REQ-415
created: 2026-05-13
updated: 2026-05-13
dependencies: []
---

## Description

Four small cleanups in a single commit:

1. **`.gitignore`** — add the line `.adlc/specs/*/pipeline-state.json` (ADR-5). Create the
   `.gitignore` file if it doesn't already exist.
2. **Remove tracked stale `pipeline-state.json` files** — three files committed by accident
   during REQ-412/413/414 pipelines:
   - `.adlc/specs/REQ-412-kimi-delegation-tooling/pipeline-state.json`
   - `.adlc/specs/REQ-413-kimi-tools-hardening/pipeline-state.json`
   - `.adlc/specs/REQ-414-adlc-skill-kimi-pilot/pipeline-state.json`
   Use `git rm --cached <file>` (ADR-6) so they're un-tracked but left on disk. The
   `.gitignore` entry from item 1 then prevents them from coming back.
3. **Delete stray `LESSON-005-sibling-skill-anti-pattern-audit 2.md`** — Finder-created
   duplicate of LESSON-005, untracked since first commit. The file lives at
   `.adlc/knowledge/lessons/LESSON-005-sibling-skill-anti-pattern-audit 2.md`. Just
   `rm` it (it's not tracked, no git operation needed; but ensure `git status` after the
   task does not list it).
4. **`tools/kimi/README.md` — add a `### Troubleshooting` subsection** under the existing
   Privacy section (or wherever it sits after the routing block). Two bullets:
   - GUI-launched Claude Code can't see your key — run `launchctl setenv
     MOONSHOT_API_KEY "$MOONSHOT_API_KEY"` from a terminal where the key is loaded, OR
     launch Claude Code from a terminal that already has the var.
   - bash login shell? `install.sh` now writes the PATH entry to `~/.bash_profile` instead
     of `~/.zshrc`. If you previously hand-edited `~/.zshrc` and your login shell is bash,
     either move the lines to `~/.bash_profile` or run `chsh -s /bin/zsh` and restart
     Terminal.app.

## Files to Create/Modify

- `.gitignore` — add (or create) the `.adlc/specs/*/pipeline-state.json` entry.
- `.adlc/specs/REQ-412-kimi-delegation-tooling/pipeline-state.json` — `git rm --cached`.
- `.adlc/specs/REQ-413-kimi-tools-hardening/pipeline-state.json` — `git rm --cached`.
- `.adlc/specs/REQ-414-adlc-skill-kimi-pilot/pipeline-state.json` — `git rm --cached`.
- `.adlc/knowledge/lessons/LESSON-005-sibling-skill-anti-pattern-audit 2.md` — delete with
  `rm` (it is untracked).
- `tools/kimi/README.md` — append the `### Troubleshooting` subsection (under 15 lines).

## Acceptance Criteria

- [ ] `.gitignore` contains the line `.adlc/specs/*/pipeline-state.json`.
- [ ] `git ls-files .adlc/specs/ | grep pipeline-state.json` returns empty.
- [ ] After the cleanup commit, creating a new `.adlc/specs/REQ-415-kimi-hotfix-bundle/pipeline-state.json`
      in this worktree shows `git status` as a no-op (the file is gitignored). Verified by
      `git status` not listing it.
- [ ] The stray `.adlc/knowledge/lessons/LESSON-005-sibling-skill-anti-pattern-audit 2.md`
      does not exist on disk after the task.
- [ ] `grep -F '### Troubleshooting' tools/kimi/README.md` returns at least one match.
- [ ] The README troubleshooting subsection mentions both `launchctl setenv` and
      `~/.bash_profile` (verified by two more `grep -F` calls).
- [ ] The README remains valid markdown (read it end-to-end).
- [ ] The REQ-413 pytest suite (`~/.claude/kimi-venv/bin/python3 -m pytest tools/kimi/tests/
      -q`) still reports 29/29 passing.

## Technical Notes

- The `git rm --cached` commands DO NOT delete the files from disk. They only stop tracking
  them. After this task and the corresponding commit, the files remain in their directories
  but `git status` shows them as untracked (and the new `.gitignore` will hide them).
- The stray LESSON file's filename contains a space (` 2.md`). When deleting via shell:
  ```
  rm ".adlc/knowledge/lessons/LESSON-005-sibling-skill-anti-pattern-audit 2.md"
  ```
- Do NOT touch any SKILL.md file, `install.sh`, `_common.py`, or any other tools/kimi/ file
  beyond the README troubleshooting addition.
- This task does not affect the REQ-413 pytest suite — verifying it still passes is a
  regression sanity check, not a behavioral change.
