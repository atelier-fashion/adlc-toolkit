# partials/trial-merge.sh — non-mutating dry-run merge (REQ-483 BR-16).
#
# Source this partial, then call adlc_trial_merge WITHIN THE SAME fenced block:
#   . .adlc/partials/trial-merge.sh 2>/dev/null || . ~/.claude/skills/partials/trial-merge.sh
#   if conflicts=$(adlc_trial_merge "$worktree" "origin/$integration_branch"); then
#     :   # clean — base merges with no conflict
#   else
#     echo "trial-merge conflicts on: $conflicts"
#   fi
#
# Contract — adlc_trial_merge <worktree> <base-ref>:
#   return 0  -> <base-ref> merges cleanly into the worktree's current HEAD
#   return 1  -> real textual conflict; conflicting paths printed to stdout, one per line
#   return 2  -> precondition error (missing args, or worktree has uncommitted changes)
# It ALWAYS restores the worktree exactly: no commit is created and the index/tree
# are clean after it returns (non-mutating). The caller must ensure <base-ref> is
# already fetched. Portable across sh/bash/zsh: prefixed globals (no `local`), no
# unquoted word-splitting (LESSON-329).
adlc_trial_merge() {
  adlc_tm_wt=$1
  adlc_tm_base=$2
  if [ -z "$adlc_tm_wt" ] || [ -z "$adlc_tm_base" ]; then
    echo "adlc_trial_merge: usage: adlc_trial_merge <worktree> <base-ref>" >&2
    return 2
  fi
  if [ -n "$(git -C "$adlc_tm_wt" status --porcelain 2>/dev/null)" ]; then
    echo "adlc_trial_merge: '$adlc_tm_wt' has uncommitted changes; commit before gating" >&2
    return 2
  fi
  # Defensive: clear any stale merge state (no-op / ignored if none in progress).
  git -C "$adlc_tm_wt" merge --abort >/dev/null 2>&1 || :
  if git -C "$adlc_tm_wt" merge --no-commit --no-ff "$adlc_tm_base" >/dev/null 2>&1; then
    # Clean merge (or already up to date) — undo the staged merge, restore HEAD.
    git -C "$adlc_tm_wt" merge --abort >/dev/null 2>&1 || :
    return 0
  fi
  # Non-zero exit -> conflict (or other merge failure). Emit unmerged paths, restore.
  git -C "$adlc_tm_wt" diff --name-only --diff-filter=U 2>/dev/null
  git -C "$adlc_tm_wt" merge --abort >/dev/null 2>&1 || :
  return 1
}
