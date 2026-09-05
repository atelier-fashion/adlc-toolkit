# partials/conflict-bound.sh — the checkable bound on runner conflict resolution (BUG-207).
#
# The contract lets an UNATTENDED pipeline-runner resolve a Phase 7/8 conflict on its
# own branch only when the conflict is an append-point collision of self-contained
# blocks. Two mechanical conditions, both checked at every conflicted hunk:
#
#   1. BOTH sides purely add lines at the same point and neither side changed or
#      removed anything that was there. With diff3 conflict markers that is exactly
#      "the base section (between `|||||||` and `=======`) is empty".
#   2. EACH side is independently delimiter-balanced: within the side, every
#      `{`/`[`/`(` it opens it also closes, and it never closes one it did not open.
#      Condition 1 proves both sides only added; it does NOT prove the region git
#      chose is a whole syntactic unit. When git ends the region mid-construct — the
#      shared closing line sits after `>>>>>>>` as common context — concatenating the
#      two bodies closes only the second side's block and leaves the first open, and
#      every contributed line is still present in the broken file (LESSON-646 in
#      teton-code: `harness/tools/mod.rs`, two REQs each adding a method pair before
#      the same following method). Condition 2 is what makes the shared trailer
#      NOT load-bearing, so keep-both cannot change nesting.
#
# "Looked mechanical" is not a checkable property; these two are. Both are verified
# against positive and negative fixtures in partials/tests/conflict-bound.test.sh.
#
# What the bound does NOT prove: that the resolved file compiles or parses. The
# delimiter check is language-agnostic and counts characters, not tokens — a brace
# inside a string or comment counts, so a side can be refused for a benign reason
# (that is the safe direction: refused -> blocked -> a human looks). It cannot see
# indentation-, keyword-, or tag-delimited structure, and it cannot see a construct
# that is balanced but wrong. The project's own build on the pushed tip is the only
# proof of syntactic validity; treat a passing bound as "safe to attempt", never
# "safe to ship" without it.
#
# Source this partial, then call WITHIN THE SAME fenced block:
#   if [ -f .adlc/partials/conflict-bound.sh ]; then . .adlc/partials/conflict-bound.sh; else . ~/.claude/skills/partials/conflict-bound.sh; fi
#   offenders=$(adlc_conflict_append_only "$worktree"); rc=$?
#   case $rc in
#     0) adlc_conflict_keep_both "$worktree" && adlc_conflict_verify_kept "$worktree" ;;  # resolve + verify
#     1) echo "halt: bound does not hold: $offenders" ;;   # anything else -> blocked, human resolves
#     *) echo "precondition error" ;;
#   esac
#
# Contract — adlc_conflict_append_only <worktree>:
#   return 0 -> every conflicted file satisfies BOTH conditions (resolvable under the bound)
#   return 1 -> at least one does not; those paths printed to stdout, one per line, and
#               one reason per offending file on stderr (base non-empty, or which side of
#               which hunk left which delimiter open / closed one it did not open)
#   return 2 -> precondition error (missing arg, not a git worktree, or NO conflicted files —
#               calling this with nothing to classify is a caller bug, not a pass)
#   Re-materializes each conflicted file with diff3 markers (`git checkout --conflict=diff3`),
#   which is idempotent on an already-conflicted path and changes nothing else.
#
# Contract — adlc_conflict_sides_balanced <file>:
#   The condition-2 check on one diff3-marked file. return 0 -> every side of every
#   hunk is balanced; 1 -> not (reasons on stderr). Used by adlc_conflict_append_only;
#   callable alone on any diff3-marked file (no git needed).
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
#   This proves line preservation and nothing else — it is deliberately NOT a
#   syntactic check (LESSON-646); condition 2 above is, and it runs before resolution.
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

# awk: exit 1 (non-zero) if ANY side of ANY hunk is not delimiter-balanced — it
# leaves a `{`/`[`/`(` open, or closes one it did not open. Characters are counted
# in order within the side (a `}` before its `{` on the same line is a dip, not a
# wash), so a region git slid onto a shared closing line is refused as well as a
# region it ended before one. Reasons go to stderr, one per defect.
adlc_conflict_sides_balanced() { # <file> -> return 0 if every side of every hunk is self-contained
  awk -v file="$1" '
    function reset() { d["{"] = 0; d["["] = 0; d["("] = 0; dip = "" }
    function scan(line,   i, c) {
      for (i = 1; i <= length(line); i++) {
        c = substr(line, i, 1)
        if      (c == "{" || c == "[" || c == "(") d[c]++
        else if (c == "}") { d["{"]--; if (d["{"] < 0 && dip == "") dip = c }
        else if (c == "]") { d["["]--; if (d["["] < 0 && dip == "") dip = c }
        else if (c == ")") { d["("]--; if (d["("] < 0 && dip == "") dip = c }
      }
    }
    function close_side(   n, ks, j) {
      if (dip != "") { printf "%s: hunk %d, %s side closes a `%s` it did not open\n", file, hunk, side, dip > "/dev/stderr"; bad++ }
      n = split("{ [ (", ks, " ")
      for (j = 1; j <= n; j++) if (d[ks[j]] != 0 && !(dip != "" && d[ks[j]] < 0))
        { printf "%s: hunk %d, %s side leaves `%s` unbalanced (%+d)\n", file, hunk, side, ks[j], d[ks[j]] > "/dev/stderr"; bad++ }
      side = ""; reset()
    }
    /^<<<<<<< /        { hunk++; inhunk = 1; side = "ours"; reset(); next }
    /^\|\|\|\|\|\|\| / { if (side == "ours") close_side(); side = "base"; next }
    /^=======$/        { if (side == "ours") close_side(); if (inhunk) { side = "theirs"; reset() }; next }
    /^>>>>>>> /        { if (side == "theirs") close_side(); inhunk = 0; next }
    side == "ours" || side == "theirs" { scan($0) }
    END                { exit (bad > 0) ? 1 : 0 }
  ' "$1"
}

adlc_conflict_append_only() {
  adlc_cb_wt=$1
  [ -n "$adlc_cb_wt" ] || { echo "adlc_conflict_append_only: usage: adlc_conflict_append_only <worktree>" >&2; return 2; }
  git -C "$adlc_cb_wt" rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "adlc_conflict_append_only: not a git worktree: $adlc_cb_wt" >&2; return 2; }
  adlc_cb_files=$(adlc_conflict_unmerged "$adlc_cb_wt")
  [ -n "$adlc_cb_files" ] || { echo "adlc_conflict_append_only: no conflicted files in $adlc_cb_wt — nothing to classify" >&2; return 2; }
  adlc_cb_rc=0
  adlc_cb_tmp="${TMPDIR:-/tmp}/adlc-cb-offenders.$$"
  # Offending paths go to stdout (the contract); the reason each one failed goes to
  # stderr, kept apart so a caller capturing `$(...)` gets paths only.
  printf '%s\n' "$adlc_cb_files" | while IFS= read -r adlc_cb_f; do
    [ -n "$adlc_cb_f" ] || continue
    git -C "$adlc_cb_wt" checkout --conflict=diff3 -- "$adlc_cb_f" >/dev/null 2>&1 || { echo "adlc_conflict_append_only: could not re-materialize diff3 markers for $adlc_cb_f" >&2; exit 2; }
    if adlc_conflict_base_nonempty "$adlc_cb_wt/$adlc_cb_f"; then
      echo "$adlc_cb_f: base section non-empty — a side changed or removed existing lines" >&2
      printf '%s\n' "$adlc_cb_f"
    elif ! adlc_conflict_sides_balanced "$adlc_cb_wt/$adlc_cb_f"; then
      printf '%s\n' "$adlc_cb_f"
    fi
  done > "$adlc_cb_tmp" 2> "$adlc_cb_tmp.why"
  adlc_cb_rc=$?
  adlc_cb_off=$(cat "$adlc_cb_tmp"); adlc_cb_why=$(cat "$adlc_cb_tmp.why"); rm -f "$adlc_cb_tmp" "$adlc_cb_tmp.why"
  [ -n "$adlc_cb_why" ] && printf '%s\n' "$adlc_cb_why" >&2
  [ "$adlc_cb_rc" -eq 2 ] && return 2
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
    [ "$adlc_ck_rc" -eq 1 ] && echo "adlc_conflict_keep_both: refusing — bound does not hold (reasons above): $(printf '%s' "$adlc_ck_off" | tr '\n' ' ')" >&2
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
