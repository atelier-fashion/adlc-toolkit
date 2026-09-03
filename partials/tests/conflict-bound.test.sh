#!/bin/sh
# partials/tests/conflict-bound.test.sh — BUG-207: the checkable bound on runner
# conflict resolution.
#
# The contract lets an unattended runner resolve a Phase 7/8 conflict on its own
# branch ONLY when both sides purely add lines at the same point. That is a claim
# about a classifier, so it is proven against fixtures, not asserted:
#
#   append_only_positive     — both sides append at the same point -> rc 0
#   append_only_negative     — one side modified an existing line   -> rc 1, path printed
#   append_only_mixed        — two files, one of each                -> rc 1, ONLY the bad one printed
#   append_only_no_conflict  — nothing to classify                  -> rc 2 (a caller bug, not a pass)
#   append_only_not_a_repo   — precondition                          -> rc 2
#   keep_both_resolves       — positive case resolved: both sides present, in order,
#                              no markers, file staged
#   keep_both_refuses        — negative case: keep_both returns 1 and TOUCHES NOTHING
#                              (markers still present, nothing staged) — the benign path
#                              (LESSON-440: a detector needs a must-not-fire case)
#   verify_kept_passes       — after keep_both, every contributed line is present
#   verify_kept_catches_loss — a resolution that dropped one side is caught
#   harness_list_survives    — the run.sh-shaped append-point collision, end to end:
#                              two branches each add a harness to a positional list
#                              line; resolved file enumerates BOTH (BUG-207's caution)
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL) — the partial must
# behave identically under bash, zsh, /bin/sh and dash.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}

FAILS=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-cbound.XXXXXX") || { echo "conflict-bound.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "conflict-bound.test.sh: sandbox path invalid" >&2; exit 1; }
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

. "$PARTIALS/conflict-bound.sh"

# mkrepo <dir> <base-content> <ours-content> <theirs-content> [<file>]
# Leaves <dir> on branch `ours` with `theirs` merged and CONFLICTED (no commit).
mkrepo() {
  mr_d=$1; mr_f=${5:-list.txt}
  mkdir -p "$mr_d" && git -C "$mr_d" init -q -b main . && git -C "$mr_d" config user.email t@t && git -C "$mr_d" config user.name t
  printf '%s' "$2" > "$mr_d/$mr_f" && git -C "$mr_d" add -- "$mr_f" && git -C "$mr_d" commit -qm base
  git -C "$mr_d" checkout -qb ours && printf '%s' "$3" > "$mr_d/$mr_f" && git -C "$mr_d" commit -qam ours
  git -C "$mr_d" checkout -q main && git -C "$mr_d" checkout -qb theirs && printf '%s' "$4" > "$mr_d/$mr_f" && git -C "$mr_d" commit -qam theirs
  git -C "$mr_d" checkout -q ours && git -C "$mr_d" merge -q theirs >/dev/null 2>&1
  return 0
}

BASE='a
b
c
'
OURS_APP='a
b
c
ours-1
'
THEIRS_APP='a
b
c
theirs-1
'
THEIRS_MOD='a
b
C-MODIFIED
theirs-2
'

# --- append_only_positive ---------------------------------------------------
R="$SANDBOX/pos"; mkrepo "$R" "$BASE" "$OURS_APP" "$THEIRS_APP"
out=$(adlc_conflict_append_only "$R"); rc=$?
check "append_only_positive: rc" 0 "$rc"
check "append_only_positive: no offenders printed" "" "$out"

# --- append_only_negative ---------------------------------------------------
R="$SANDBOX/neg"; mkrepo "$R" "$BASE" "$OURS_APP" "$THEIRS_MOD"
out=$(adlc_conflict_append_only "$R"); rc=$?
check "append_only_negative: rc" 1 "$rc"
check "append_only_negative: offending path printed" "list.txt" "$out"

# --- append_only_mixed ------------------------------------------------------
R="$SANDBOX/mix"; mkdir -p "$R" && git -C "$R" init -q -b main . && git -C "$R" config user.email t@t && git -C "$R" config user.name t
printf '%s' "$BASE" > "$R/good.txt"; printf '%s' "$BASE" > "$R/bad.txt"; git -C "$R" add . && git -C "$R" commit -qm base
git -C "$R" checkout -qb ours && printf '%s' "$OURS_APP" > "$R/good.txt" && printf '%s' "$OURS_APP" > "$R/bad.txt" && git -C "$R" commit -qam ours
git -C "$R" checkout -q main && git -C "$R" checkout -qb theirs && printf '%s' "$THEIRS_APP" > "$R/good.txt" && printf '%s' "$THEIRS_MOD" > "$R/bad.txt" && git -C "$R" commit -qam theirs
git -C "$R" checkout -q ours && git -C "$R" merge -q theirs >/dev/null 2>&1
out=$(adlc_conflict_append_only "$R"); rc=$?
check "append_only_mixed: rc" 1 "$rc"
check "append_only_mixed: only the non-append file is printed" "bad.txt" "$out"

# --- append_only_no_conflict / not_a_repo -----------------------------------
R="$SANDBOX/clean"; mkdir -p "$R" && git -C "$R" init -q -b main . && git -C "$R" config user.email t@t && git -C "$R" config user.name t && printf 'x\n' > "$R/f" && git -C "$R" add f && git -C "$R" commit -qm c
adlc_conflict_append_only "$R" >/dev/null 2>&1; check "append_only_no_conflict: nothing to classify is rc 2, never a pass" 2 "$?"
adlc_conflict_append_only "$SANDBOX/does-not-exist" >/dev/null 2>&1; check "append_only_not_a_repo: rc" 2 "$?"
adlc_conflict_append_only >/dev/null 2>&1; check "append_only_no_arg: rc" 2 "$?"

# --- keep_both_resolves -----------------------------------------------------
R="$SANDBOX/kb"; mkrepo "$R" "$BASE" "$OURS_APP" "$THEIRS_APP"
ADLC_CONFLICT_SIDECAR="$SANDBOX/kb-side"; mkdir -p "$ADLC_CONFLICT_SIDECAR"; export ADLC_CONFLICT_SIDECAR
out=$(adlc_conflict_keep_both "$R" 2>/dev/null); rc=$?
check "keep_both_resolves: rc" 0 "$rc"
check "keep_both_resolves: touched path printed" "list.txt" "$out"
check "keep_both_resolves: resolved content = base + ours + theirs, no markers" "a b c ours-1 theirs-1" "$(tr '\n' ' ' < "$R/list.txt" | sed 's/ $//')"
check "keep_both_resolves: no conflict markers remain" 0 "$(grep -c '^<<<<<<<\|^=======$\|^>>>>>>>\|^|||||||' "$R/list.txt")"
check "keep_both_resolves: file is staged (no longer unmerged)" "" "$(git -C "$R" diff --name-only --diff-filter=U)"

# --- verify_kept_passes -----------------------------------------------------
adlc_conflict_verify_kept "$R" "$ADLC_CONFLICT_SIDECAR" >/dev/null; check "verify_kept_passes: rc" 0 "$?"

# --- verify_kept_catches_loss ----------------------------------------------
printf 'a\nb\nc\nours-1\n' > "$R/list.txt"   # simulate a resolution that dropped theirs
out=$(adlc_conflict_verify_kept "$R" "$ADLC_CONFLICT_SIDECAR"); rc=$?
check "verify_kept_catches_loss: rc" 1 "$rc"
check "verify_kept_catches_loss: path printed" "list.txt" "$out"
unset ADLC_CONFLICT_SIDECAR

# --- keep_both_refuses (benign path — must NOT fire) -------------------------
R="$SANDBOX/kbneg"; mkrepo "$R" "$BASE" "$OURS_APP" "$THEIRS_MOD"
# The classifier documents ONE side effect: it re-materializes markers as diff3
# (`HEAD` -> `ours`, a `|||||||` base section). Snapshot after that, so the
# assertion below proves keep_both adds NOTHING on refusal — not that the
# documented re-materialization didn't happen.
git -C "$R" checkout --conflict=diff3 -- list.txt >/dev/null 2>&1
before=$(cat "$R/list.txt")
ADLC_CONFLICT_SIDECAR="$SANDBOX/kbneg-side"; mkdir -p "$ADLC_CONFLICT_SIDECAR"; export ADLC_CONFLICT_SIDECAR
adlc_conflict_keep_both "$R" >/dev/null 2>&1; check "keep_both_refuses: rc" 1 "$?"
after=$(cat "$R/list.txt")
check "keep_both_refuses: file untouched beyond diff3 re-materialization (markers intact)" "$before" "$after"
check "keep_both_refuses: still unmerged (nothing staged)" "list.txt" "$(git -C "$R" diff --name-only --diff-filter=U)"
check "keep_both_refuses: no sidecar files written" 0 "$(ls "$ADLC_CONFLICT_SIDECAR" | wc -l | tr -d ' ')"
unset ADLC_CONFLICT_SIDECAR

# --- harness_list_survives (the run.sh-shaped case, BUG-207's caution) --------
RUNBASE='#!/bin/sh
run_all "$2" "$HERE/a.test.sh" "$HERE/b.test.sh"
exit $RC
'
RUNOURS='#!/bin/sh
run_all "$2" "$HERE/a.test.sh" "$HERE/b.test.sh"
# ours added c
run_all "$2" "$HERE/c.test.sh"
exit $RC
'
RUNTHEIRS='#!/bin/sh
run_all "$2" "$HERE/a.test.sh" "$HERE/b.test.sh"
# theirs added d
run_all "$2" "$HERE/d.test.sh"
exit $RC
'
R="$SANDBOX/runsh"; mkrepo "$R" "$RUNBASE" "$RUNOURS" "$RUNTHEIRS" run.sh
ADLC_CONFLICT_SIDECAR="$SANDBOX/runsh-side"; mkdir -p "$ADLC_CONFLICT_SIDECAR"; export ADLC_CONFLICT_SIDECAR
adlc_conflict_keep_both "$R" >/dev/null 2>&1; check "harness_list_survives: keep_both rc" 0 "$?"
adlc_conflict_verify_kept "$R" >/dev/null; check "harness_list_survives: verify rc" 0 "$?"
check "harness_list_survives: BOTH added harnesses enumerated" 2 "$(grep -c 'c.test.sh\|d.test.sh' "$R/run.sh")"
check "harness_list_survives: original harnesses still enumerated" 1 "$(grep -c 'a.test.sh.*b.test.sh' "$R/run.sh")"
check "harness_list_survives: resolved file still parses as sh" 0 "$($SUT -n "$R/run.sh" 2>/dev/null; echo $?)"
unset ADLC_CONFLICT_SIDECAR

# ===========================================================================
if [ "$FAILS" -eq 0 ]; then
  echo "conflict-bound.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "conflict-bound.test.sh: $FAILS CASE(S) FAILED ($SUT)"
exit 1
