---
id: TASK-069
title: "Create partials/trial-merge.sh — shared non-mutating dry-run merge helper (BR-16)"
status: draft
parent: REQ-483
created: 2026-06-04
updated: 2026-06-04
dependencies: []
---

## Description

Create the shared trial-merge helper that the enforcement gates call. It performs a non-mutating dry-run merge to detect real textual conflicts and always restores the worktree exactly. This is the foundational hard-gate primitive (BR-16).

## Files to Create/Modify

- `partials/trial-merge.sh` — exports `adlc_trial_merge` (create)

## Acceptance Criteria

- [ ] Exports a POSIX-shell function `adlc_trial_merge <worktree> <base-ref>` that: runs `git -C <worktree> merge --no-commit --no-ff <base-ref>`; on conflict collects `git -C <worktree> diff --name-only --diff-filter=U`; ALWAYS runs `git -C <worktree> merge --abort` to restore state; returns 0 (clean) or 1 (conflict, conflicting files printed to stdout).
- [ ] **Non-mutating**: after the function returns (clean OR conflict), `git -C <worktree> status --porcelain` is empty and no commit was created (verifiable in dogfood).
- [ ] Robust if no merge is in progress (abort is guarded so a clean fast-forward-less merge or an already-clean state doesn't error).
- [ ] Portable across `sh`/`bash`/`zsh`: no `local` (or the file is sourced and the function uses only POSIX constructs), no reliance on unquoted word-splitting (LESSON-329).
- [ ] Sourceable via the two-level fallback used elsewhere: `. .adlc/partials/trial-merge.sh 2>/dev/null || . ~/.claude/skills/partials/trial-merge.sh`.
- [ ] **Dogfood**: sourced and run against (a) a synthetic clean merge → returns 0, and (b) a synthetic conflicting merge → returns 1 with the conflicting file listed; `git status` clean after both. Identical under `sh` and `zsh`.

## Technical Notes

- Model the worktree-isolation safety on REQ-263 (the worktree is the sandbox; aborting restores it).
- Keep the function body self-contained; callers source the partial and invoke it **within the same fenced block** (avoids the `cross-fence-fn` lint check — conventions "Bash in skills", LESSON-020).
- Do not `git fetch` inside the helper — the caller ensures `<base-ref>` (e.g. `origin/<integration-branch>`) is current; the helper only merges/aborts.
- Echo conflicting files one per line on stdout; keep diagnostics on stderr.
