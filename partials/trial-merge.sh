# partials/trial-merge.sh — non-mutating dry-run merge (REQ-483 BR-16).
#
# Source this partial, then call adlc_trial_merge WITHIN THE SAME fenced block:
#   . .adlc/partials/trial-merge.sh 2>/dev/null || . ~/.claude/skills/partials/trial-merge.sh
#   git -C "$worktree" fetch origin "$integration_branch" >/dev/null 2>&1   # caller MUST refresh the base
#   conflicts=$(adlc_trial_merge "$worktree" "origin/$integration_branch"); rc=$?
#   case $rc in
#     0) : ;;                                  # clean — base merges with no conflict
#     1) echo "blocked: real conflict on: $conflicts" ;;   # REAL textual conflict
#     *) echo "precondition/ref error — do NOT treat as a merge conflict" ;;  # rc 2 or 3
#   esac
#
# Contract — adlc_trial_merge <worktree> <base-ref>:
#   return 0 -> <base-ref> merges cleanly into the worktree's current HEAD
#   return 1 -> REAL textual conflict; conflicting paths printed to stdout, one per line
#   return 2 -> precondition error (missing args, or worktree has uncommitted changes)
#   return 3 -> the merge could not start (e.g. bad/unfetched base ref) — NOT a conflict
# Callers MUST branch on the code: only rc=1 is a `blocked` merge conflict. rc=2/3 are
# setup errors and should surface as `failed`/a loud error, never as a spurious conflict.
# It ALWAYS restores the worktree exactly: no commit is created and the index/tree are
# clean after it returns (non-mutating). The caller MUST `git fetch` the base ref first
# (this helper only merges/aborts). Portable across sh/bash/zsh: prefixed globals (no
# `local`), no unquoted word-splitting (LESSON-329).
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
    git -C "$adlc_tm_wt" merge --abort >/dev/null 2>&1 || :   # undo the clean staged merge
    return 0
  fi
  # Non-zero merge. Capture unmerged paths BEFORE aborting, then restore.
  adlc_tm_conf=$(git -C "$adlc_tm_wt" diff --name-only --diff-filter=U 2>/dev/null)
  git -C "$adlc_tm_wt" merge --abort >/dev/null 2>&1 || :
  if [ -n "$adlc_tm_conf" ]; then
    printf '%s\n' "$adlc_tm_conf"
    return 1
  fi
  # Non-zero but no conflicted paths -> the merge never started (bad/unfetched ref, etc.).
  echo "adlc_trial_merge: merge could not start (check base ref '$adlc_tm_base' is fetched)" >&2
  return 3
}
