# partials/conflict-bound.sh — the checkable bound on runner conflict resolution (BUG-207).
#
# The contract lets an UNATTENDED pipeline-runner resolve a Phase 7/8 conflict on its
# own branch only when the conflict is an append-point collision: at every conflicted
# hunk, BOTH sides purely add lines at the same point and neither side changed or
# removed anything that was there. "Looked mechanical" is not a checkable property;
# this is. With diff3 conflict markers, that condition is exactly "the base section
# (between `|||||||` and `=======`) of every hunk is empty" — verified against
# positive and negative fixtures in partials/tests/conflict-bound.test.sh.
#
# Source this partial, then call WITHIN THE SAME fenced block:
#   if [ -f .adlc/partials/conflict-bound.sh ]; then . .adlc/partials/conflict-bound.sh; else . ~/.claude/skills/partials/conflict-bound.sh; fi
#   offenders=$(adlc_conflict_append_only "$worktree"); rc=$?
#   case $rc in
#     0) adlc_conflict_keep_both "$worktree" && adlc_conflict_verify_kept "$worktree" ;;  # resolve + verify
#     1) echo "halt: not append-only: $offenders" ;;   # anything else -> blocked, human resolves
#     *) echo "precondition error" ;;
#   esac
#
# Contract — adlc_conflict_append_only <worktree>:
#   return 0 -> every conflicted file is an append-point collision (resolvable under the bound)
#   return 1 -> at least one is not; those paths printed to stdout, one per line
#   return 2 -> precondition error (missing arg, not a git worktree, or NO conflicted files —
#               calling this with nothing to classify is a caller bug, not a pass)
#   Re-materializes each conflicted file with diff3 markers (`git checkout --conflict=diff3`),
#   which is idempotent on an already-conflicted path and changes nothing else.
#
# Contract — adlc_conflict_keep_both <worktree>:
#   Resolves every conflicted file by keeping BOTH sides in order (ours, then theirs),
#   dropping markers and the (empty) base section, and stages the result. return 0 on
#   success; return 1 if the bound does not hold (it re-checks — never resolves what it
#   should not); return 2 on precondition error. Files touched are printed to stdout.
#
# Contract — adlc_conflict_verify_kept <worktree> [<sidecar-dir>]:
#   Proves the resolution preserved both sides: every line each side contributed is
#   present in the resolved file. return 0 -> verified; 1 -> a contributed line is
#   missing (paths printed); 2 -> precondition error. adlc_conflict_keep_both records
#   each side's lines in a sidecar under $ADLC_CONFLICT_SIDECAR (default: a mktemp dir
#   it prints on stderr) so verification does not trust its own resolution step.
#
# Portable across sh/bash/zsh/dash: prefixed globals (no `local`), no unquoted
# word-splitting (LESSON-329), BSD awk/sed only.

adlc_conflict_unmerged() { # <worktree> -> conflicted paths, one per line
  git -C "$1" diff --name-only --diff-filter=U 2>/dev/null
}

# awk: exit 1 (non-zero) if ANY hunk's base section has a line. Marker lines are
# matched at column 0 with their trailing space/`$` so content lines that merely
# start with `=` or `<` are not mistaken for markers.
adlc_conflict_base_nonempty() { # <file> -> return 0 if some base section is non-empty
  awk '
    /^<<<<<<< /      { inb = 0; next }
    /^\|\|\|\|\|\|\| / { inb = 1; next }
    /^=======$/      { inb = 0; next }
    /^>>>>>>> /      { inb = 0; next }
    inb              { n++ }
    END              { exit (n > 0) ? 0 : 1 }
  ' "$1"
}

adlc_conflict_append_only() {
  adlc_cb_wt=$1
  [ -n "$adlc_cb_wt" ] || { echo "adlc_conflict_append_only: usage: adlc_conflict_append_only <worktree>" >&2; return 2; }
  git -C "$adlc_cb_wt" rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "adlc_conflict_append_only: not a git worktree: $adlc_cb_wt" >&2; return 2; }
  adlc_cb_files=$(adlc_conflict_unmerged "$adlc_cb_wt")
  [ -n "$adlc_cb_files" ] || { echo "adlc_conflict_append_only: no conflicted files in $adlc_cb_wt — nothing to classify" >&2; return 2; }
  adlc_cb_rc=0
  printf '%s\n' "$adlc_cb_files" | while IFS= read -r adlc_cb_f; do
    [ -n "$adlc_cb_f" ] || continue
    git -C "$adlc_cb_wt" checkout --conflict=diff3 -- "$adlc_cb_f" >/dev/null 2>&1 || { echo "adlc_conflict_append_only: could not re-materialize diff3 markers for $adlc_cb_f" >&2; exit 2; }
    if adlc_conflict_base_nonempty "$adlc_cb_wt/$adlc_cb_f"; then
      printf '%s\n' "$adlc_cb_f"
    fi
  done > "${TMPDIR:-/tmp}/adlc-cb-offenders.$$" 2>&1
  adlc_cb_rc=$?
  adlc_cb_off=$(cat "${TMPDIR:-/tmp}/adlc-cb-offenders.$$"); rm -f "${TMPDIR:-/tmp}/adlc-cb-offenders.$$"
  [ "$adlc_cb_rc" -eq 2 ] && { printf '%s\n' "$adlc_cb_off" >&2; return 2; }
  if [ -n "$adlc_cb_off" ]; then printf '%s\n' "$adlc_cb_off"; return 1; fi
  return 0
}

# Emit the ours/theirs lines of a diff3-marked file to two sidecars, and the
# resolved (both-kept, marker-free) content to stdout.
adlc_conflict_split() { # <file> <ours-out> <theirs-out>
  awk -v ours="$2" -v theirs="$3" '
    /^<<<<<<< /      { s = "o"; next }
    /^\|\|\|\|\|\|\| / { s = "b"; next }
    /^=======$/      { if (s == "o" || s == "b") { s = "t"; next } }
    /^>>>>>>> /      { s = ""; next }
    s == "o"         { print > ours;   print; next }
    s == "t"         { print > theirs; print; next }
    s == "b"         { next }
                     { print }
  ' "$1"
}

adlc_conflict_keep_both() {
  adlc_ck_wt=$1
  [ -n "$adlc_ck_wt" ] || { echo "adlc_conflict_keep_both: usage: adlc_conflict_keep_both <worktree>" >&2; return 2; }
  adlc_ck_off=$(adlc_conflict_append_only "$adlc_ck_wt"); adlc_ck_rc=$?
  if [ "$adlc_ck_rc" -ne 0 ]; then
    [ "$adlc_ck_rc" -eq 1 ] && echo "adlc_conflict_keep_both: refusing — not append-only: $(printf '%s' "$adlc_ck_off" | tr '\n' ' ')" >&2
    return "$adlc_ck_rc"
  fi
  if [ -z "${ADLC_CONFLICT_SIDECAR:-}" ]; then
    ADLC_CONFLICT_SIDECAR=$(mktemp -d "${TMPDIR:-/tmp}/adlc-conflict.XXXXXX") || { echo "adlc_conflict_keep_both: mktemp failed" >&2; return 2; }
    echo "adlc_conflict_keep_both: sidecar $ADLC_CONFLICT_SIDECAR" >&2
  fi
  [ -n "$ADLC_CONFLICT_SIDECAR" ] && [ -d "$ADLC_CONFLICT_SIDECAR" ] || { echo "adlc_conflict_keep_both: sidecar dir invalid" >&2; return 2; }
  adlc_conflict_unmerged "$adlc_ck_wt" | while IFS= read -r adlc_ck_f; do
    [ -n "$adlc_ck_f" ] || continue
    adlc_ck_key=$(printf '%s' "$adlc_ck_f" | tr '/' '_')
    adlc_conflict_split "$adlc_ck_wt/$adlc_ck_f" "$ADLC_CONFLICT_SIDECAR/$adlc_ck_key.ours" "$ADLC_CONFLICT_SIDECAR/$adlc_ck_key.theirs" > "$ADLC_CONFLICT_SIDECAR/$adlc_ck_key.resolved" || exit 2
    cp "$ADLC_CONFLICT_SIDECAR/$adlc_ck_key.resolved" "$adlc_ck_wt/$adlc_ck_f" || exit 2
    git -C "$adlc_ck_wt" add -- "$adlc_ck_f" || exit 2
    printf '%s\n' "$adlc_ck_f"
  done
  adlc_ck_rc=$?
  [ "$adlc_ck_rc" -eq 0 ] || return 2
  printf '%s\n' "$ADLC_CONFLICT_SIDECAR" > "$ADLC_CONFLICT_SIDECAR/.dir"
  return 0
}

adlc_conflict_verify_kept() {
  adlc_cv_wt=$1
  adlc_cv_dir=${2:-${ADLC_CONFLICT_SIDECAR:-}}
  [ -n "$adlc_cv_wt" ] && [ -n "$adlc_cv_dir" ] && [ -d "$adlc_cv_dir" ] || { echo "adlc_conflict_verify_kept: usage: adlc_conflict_verify_kept <worktree> [<sidecar-dir>] (sidecar missing)" >&2; return 2; }
  adlc_cv_bad=""
  for adlc_cv_side in "$adlc_cv_dir"/*.ours "$adlc_cv_dir"/*.theirs; do
    [ -f "$adlc_cv_side" ] || continue
    adlc_cv_key=$(basename "$adlc_cv_side"); adlc_cv_key=${adlc_cv_key%.ours}; adlc_cv_key=${adlc_cv_key%.theirs}
    adlc_cv_file=$(printf '%s' "$adlc_cv_key" | tr '_' '/')
    [ -f "$adlc_cv_wt/$adlc_cv_file" ] || { adlc_cv_bad="$adlc_cv_bad $adlc_cv_file"; continue; }
    # Every contributed line must appear in the resolved file (fixed-string, whole line).
    while IFS= read -r adlc_cv_line; do
      grep -qxF -- "$adlc_cv_line" "$adlc_cv_wt/$adlc_cv_file" || { adlc_cv_bad="$adlc_cv_bad $adlc_cv_file"; break; }
    done < "$adlc_cv_side"
  done
  if [ -n "$adlc_cv_bad" ]; then printf '%s\n' "$adlc_cv_bad" | tr ' ' '\n' | sed '/^$/d' | sort -u; return 1; fi
  return 0
}
