#!/bin/sh
# partials/tests/lane-check.test.sh — REQ-652 BR-6: the lite lane's mechanical
# diff check, end to end through the sourced wrapper.
#
# tools/adlc/tests/test_lane_check.py covers every rule of the engine. This
# harness proves the shell half: that `adlc_lane_check` runs the engine under
# bash, zsh, /bin/sh and dash, and hands its stdout and exit code through
# unchanged.
#
#   pass                  — one source file changed            -> rc 0, lane_check=pass
#   escalate_blocked      — a CI workflow changed               -> rc 1, trigger=blocked-path
#   escalate_max_files    — four source files changed           -> rc 1, trigger=max-files
#   error_dirty_tree      — an uncommitted change               -> rc 2, lane_check=error, trigger=check-error
#   error_bad_base        — a base ref that does not resolve    -> rc 2, lane_check=error
#   error_usage           — no arguments                        -> rc 2, lane_check=error
#   passthrough           — wrapper stdout and rc are byte-identical to the engine run directly
#   recheck_after_commit  — AC-16: a passing branch, then a new commit touching a blocked
#                           path (a CI fix in Phase 7), re-checked -> rc 1
#   engine_not_found      — HOME has no .claude/skills and ADLC_TOOLKIT_ROOT is unset
#                                                                     -> rc 2, check-error
#   engine_not_found_root_set — ADLC_TOOLKIT_ROOT names a root with no engine; HOME's
#                           install is NOT consulted                  -> rc 2, check-error
#   engine_via_toolkit_root — REQ-669: no .claude/skills at all, ADLC_TOOLKIT_ROOT is the
#                           checkout (the plugin route)               -> rc 0, pass
#   branch_engine_ignored — the branch commits tools/adlc/lane_check.py and
#                           .adlc/tools/adlc/lane_check.py stubs that print a pass;
#                           the installed engine still runs           -> rc 1, blocked-path
#   rc_outside_contract   — the interpreter exits 7 after printing a pass line
#                                                                     -> rc 2, `detail=lane_check.py exited 7`
#   rc_without_verdict    — the interpreter exits 0 but prints no `lane_check=pass`
#                                                                     -> rc 2, check-error
#   resolver_undefined    — `_adlc_forge_python` is not defined       -> rc 2, check-error
#   empty_diff            — no commits on the branch                  -> rc 2, check-error
#   engine_inside_worktree — LESSON-718: ADLC_TOOLKIT_ROOT is the tree under check (or a
#                           copy vendored in it), whose planted engine prints a pass;
#                           refused before it runs, also through a symlinked worktree
#                           path or root                                -> rc 2, check-error
#   worktree_inside_toolkit — the benign shape: the worktree sits under the toolkit
#                           root, as the toolkit's own .claude/worktrees/ do; the
#                           engine is not inside it and runs           -> rc 0, pass
#   set_u_home_unset      — sourced by a `set -u` shell with HOME and ADLC_TOOLKIT_ROOT
#                           unset: no abort, and the call is a check-error
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL). HOME is pointed
# at a sandbox whose ~/.claude/skills is THIS toolkit checkout. The wrapper only
# ever runs the installed toolkit's engine, so that is how the engine under test
# is the one it finds; no global git config (signing, hooks) leaks into the
# sandbox repos either.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
TOOLKIT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}

FAILS=0
CASES=0
pass() { echo "PASS: $1"; CASES=$((CASES + 1)); }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-lanecheck.XXXXXX") || { echo "lane-check.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "lane-check.test.sh: sandbox path invalid" >&2; exit 1; }
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

mkdir -p "$SANDBOX/home/.claude" && ln -s "$TOOLKIT" "$SANDBOX/home/.claude/skills"
HOME="$SANDBOX/home"; export HOME
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
# REQ-669: the symlink route is the default here; the cases that exercise
# ToolkitRoot set ADLC_TOOLKIT_ROOT themselves.
unset ADLC_TOOLKIT_ROOT CLAUDE_PLUGIN_ROOT

# forge.sh first, from this checkout, so lane-check.sh finds `_adlc_forge_python`
# already defined and does not go looking for an installed copy.
. "$PARTIALS/forge.sh"
. "$PARTIALS/lane-check.sh"

# mkrepo <dir> — a repo with one base commit on `main`, left on branch `feat`.
mkrepo() {
  mr_d=$1
  mkdir -p "$mr_d" && git -C "$mr_d" init -q -b main . && git -C "$mr_d" config user.email t@t && git -C "$mr_d" config user.name t
  mkdir -p "$mr_d/src" && printf 'base\n' > "$mr_d/src/a.txt" && git -C "$mr_d" add -A && git -C "$mr_d" commit -qm base
  git -C "$mr_d" checkout -qb feat
  return 0
}
# commit_files <dir> <path>... — write and commit each path on the current branch.
commit_files() {
  cf_d=$1; shift
  for cf_p in "$@"; do
    mkdir -p "$cf_d/$(dirname -- "$cf_p")" && printf 'change\n' > "$cf_d/$cf_p"
  done
  git -C "$cf_d" add -A && git -C "$cf_d" commit -qm change
}

# --- pass -------------------------------------------------------------------
R="$SANDBOX/pass"; mkrepo "$R"; commit_files "$R" src/a.txt
out=$(adlc_lane_check "$R" main); rc=$?
check "pass: rc" 0 "$rc"
check "pass: first line" "lane_check=pass" "$(printf '%s\n' "$out" | sed -n 1p)"
check "pass: files_counted" "files_counted=1" "$(printf '%s\n' "$out" | sed -n 2p)"
check "pass: no trigger lines" "0" "$(printf '%s\n' "$out" | grep -c '^trigger=')"

# --- escalate_blocked -------------------------------------------------------
R="$SANDBOX/blocked"; mkrepo "$R"; commit_files "$R" .github/workflows/ci.yml
out=$(adlc_lane_check "$R" main); rc=$?
check "escalate_blocked: rc" 1 "$rc"
check "escalate_blocked: first line" "lane_check=escalate" "$(printf '%s\n' "$out" | sed -n 1p)"
check "escalate_blocked: trigger" "trigger=blocked-path" "$(printf '%s\n' "$out" | grep '^trigger=' | sed -n 1p)"
check "escalate_blocked: detail names the path" "detail=.github/workflows/ci.yml" "$(printf '%s\n' "$out" | grep '^detail=' | sed -n 1p)"

# --- escalate_max_files -----------------------------------------------------
R="$SANDBOX/maxfiles"; mkrepo "$R"; commit_files "$R" src/a.txt src/b.txt src/c.txt src/d.txt
out=$(adlc_lane_check "$R" main); rc=$?
check "escalate_max_files: rc" 1 "$rc"
check "escalate_max_files: trigger" "trigger=max-files" "$(printf '%s\n' "$out" | grep '^trigger=' | sed -n 1p)"
check "escalate_max_files: detail" "detail=4 > 3" "$(printf '%s\n' "$out" | grep '^detail=' | sed -n 1p)"

# --- error_dirty_tree -------------------------------------------------------
R="$SANDBOX/dirty"; mkrepo "$R"; commit_files "$R" src/a.txt; printf 'uncommitted\n' > "$R/src/a.txt"
out=$(adlc_lane_check "$R" main); rc=$?
check "error_dirty_tree: rc" 2 "$rc"
check "error_dirty_tree: first line" "lane_check=error" "$(printf '%s\n' "$out" | sed -n 1p)"
check "error_dirty_tree: trigger" "trigger=check-error" "$(printf '%s\n' "$out" | grep '^trigger=' | sed -n 1p)"

# --- error_bad_base ---------------------------------------------------------
R="$SANDBOX/badbase"; mkrepo "$R"; commit_files "$R" src/a.txt
out=$(adlc_lane_check "$R" origin/no-such-branch 2>/dev/null); rc=$?
check "error_bad_base: rc" 2 "$rc"
check "error_bad_base: first line" "lane_check=error" "$(printf '%s\n' "$out" | sed -n 1p)"

# --- error_usage ------------------------------------------------------------
out=$(adlc_lane_check 2>/dev/null); rc=$?
check "error_usage: rc" 2 "$rc"
check "error_usage: first line" "lane_check=error" "$(printf '%s\n' "$out" | sed -n 1p)"

# --- passthrough ------------------------------------------------------------
# The wrapper adds nothing and drops nothing: same stdout, same rc, as running
# the engine by path with the interpreter the wrapper itself resolves.
R="$SANDBOX/passthrough"; mkrepo "$R"; commit_files "$R" .github/workflows/ci.yml src/a.txt
wrapped=$(adlc_lane_check "$R" main); wrapped_rc=$?
direct=$(command "$(_adlc_forge_python)" "$TOOLKIT/tools/adlc/lane_check.py" --worktree "$R" --base main); direct_rc=$?
check "passthrough: rc identical" "$direct_rc" "$wrapped_rc"
check "passthrough: stdout identical" "$direct" "$wrapped"

# --- recheck_after_commit (AC-16) -------------------------------------------
R="$SANDBOX/recheck"; mkrepo "$R"; commit_files "$R" src/a.txt
adlc_lane_check "$R" main >/dev/null; rc=$?
check "recheck_after_commit: first check passes" 0 "$rc"
commit_files "$R" infra/main.tf
out=$(adlc_lane_check "$R" main); rc=$?
check "recheck_after_commit: re-check after a blocked-path commit escalates" 1 "$rc"
check "recheck_after_commit: trigger" "trigger=blocked-path" "$(printf '%s\n' "$out" | grep '^trigger=' | sed -n 1p)"

# --- engine_not_found -------------------------------------------------------
# The wrapper looks in the installed toolkit only; a HOME without one, and no
# ADLC_TOOLKIT_ROOT, is an error.
R="$SANDBOX/noengine"; mkrepo "$R"; commit_files "$R" src/a.txt
mkdir -p "$SANDBOX/emptyhome"
out=$(HOME="$SANDBOX/emptyhome"; export HOME; unset ADLC_TOOLKIT_ROOT; adlc_lane_check "$R" main 2>/dev/null); rc=$?
check "engine_not_found: rc" 2 "$rc"
check "engine_not_found: first line" "lane_check=error" "$(printf '%s\n' "$out" | sed -n 1p)"
check "engine_not_found: trigger" "trigger=check-error" "$(printf '%s\n' "$out" | sed -n 2p)"
check "engine_not_found: detail" "detail=lane_check.py not found in the installed toolkit" "$(printf '%s\n' "$out" | sed -n 3p)"
# The stderr names both install routes, not install.sh alone.
err=$(HOME="$SANDBOX/emptyhome"; export HOME; unset ADLC_TOOLKIT_ROOT; adlc_lane_check "$R" main 2>&1 >/dev/null)
check "engine_not_found: stderr names the symlink route" "1" "$(printf '%s\n' "$err" | grep -c 'install.sh')"
check "engine_not_found: stderr names the plugin route" "1" "$(printf '%s\n' "$err" | grep -c 'claude plugin install adlc@adlc-toolkit')"

# --- engine_not_found_root_set ----------------------------------------------
# ADLC_TOOLKIT_ROOT is the install. A root without the engine is an error even
# though HOME's ~/.claude/skills (this checkout) has one: the two never mix.
mkdir -p "$SANDBOX/emptyroot"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_lane_check "$R" main 2>/dev/null); rc=$?
check "engine_not_found_root_set: rc" 2 "$rc"
check "engine_not_found_root_set: detail" "detail=lane_check.py not found in the installed toolkit" "$(printf '%s\n' "$out" | sed -n 3p)"

# --- engine_via_toolkit_root ------------------------------------------------
# REQ-669 plugin route: no ~/.claude/skills anywhere, the engine is ToolkitRoot's.
mkdir -p "$SANDBOX/pluginhome/.claude"
out=$(HOME="$SANDBOX/pluginhome"; export HOME; ADLC_TOOLKIT_ROOT="$TOOLKIT"; export ADLC_TOOLKIT_ROOT; adlc_lane_check "$R" main); rc=$?
check "engine_via_toolkit_root: rc" 0 "$rc"
check "engine_via_toolkit_root: first line" "lane_check=pass" "$(printf '%s\n' "$out" | sed -n 1p)"

# --- branch_engine_ignored --------------------------------------------------
# A branch that ships its own checker (at both locations the old lookup tried)
# printing a pass is not run: the installed engine sees the blocked path.
R="$SANDBOX/ownengine"; mkrepo "$R"
mkdir -p "$R/tools/adlc" "$R/.adlc/tools/adlc"
printf 'import sys\nprint("lane_check=pass")\nprint("files_counted=0")\nsys.exit(0)\n' > "$R/tools/adlc/lane_check.py"
cp "$R/tools/adlc/lane_check.py" "$R/.adlc/tools/adlc/lane_check.py"
commit_files "$R" .github/workflows/ci.yml
out=$(adlc_lane_check "$R" main); rc=$?
check "branch_engine_ignored: rc" 1 "$rc"
check "branch_engine_ignored: first line" "lane_check=escalate" "$(printf '%s\n' "$out" | sed -n 1p)"
check "branch_engine_ignored: CI path still blocked" "1" "$(printf '%s\n' "$out" | grep -c '^detail=.github/workflows/ci.yml$')"
check "branch_engine_ignored: vendored copy itself blocked" "1" "$(printf '%s\n' "$out" | grep -c '^detail=.adlc/tools/adlc/lane_check.py$')"

# --- rc_outside_contract ----------------------------------------------------
# The "interpreter" is a script that prints a pass verdict and exits 7: the
# printed lines are withheld and the run is an error.
STUB7="$SANDBOX/exit7.sh"
printf '#!/bin/sh\nprintf '"'"'lane_check=pass\\nfiles_counted=0\\n'"'"'\nexit 7\n' > "$STUB7" && chmod +x "$STUB7"
R="$SANDBOX/exit7"; mkrepo "$R"; commit_files "$R" src/a.txt
( _adlc_forge_python() { printf '%s\n' "$STUB7"; }; adlc_lane_check "$R" main ) > "$SANDBOX/exit7.out" 2>/dev/null; rc=$?
out=$(cat "$SANDBOX/exit7.out")
check "rc_outside_contract: rc" 2 "$rc"
check "rc_outside_contract: output" "lane_check=error
trigger=check-error
detail=lane_check.py exited 7" "$out"

# --- rc_without_verdict -----------------------------------------------------
# Exit 0 with no `lane_check=pass` first line is not a pass.
STUB0="$SANDBOX/exit0.sh"
printf '#!/bin/sh\necho hello\nexit 0\n' > "$STUB0" && chmod +x "$STUB0"
( _adlc_forge_python() { printf '%s\n' "$STUB0"; }; adlc_lane_check "$R" main ) > "$SANDBOX/exit0.out" 2>/dev/null; rc=$?
out=$(cat "$SANDBOX/exit0.out")
check "rc_without_verdict: rc" 2 "$rc"
check "rc_without_verdict: first line" "lane_check=error" "$(printf '%s\n' "$out" | sed -n 1p)"
check "rc_without_verdict: no pass line leaks" "0" "$(printf '%s\n' "$out" | grep -c '^lane_check=pass')"

# --- resolver_undefined -----------------------------------------------------
( unset -f _adlc_forge_python 2>/dev/null || unfunction _adlc_forge_python 2>/dev/null
  adlc_lane_check "$R" main ) > "$SANDBOX/noresolver.out" 2>/dev/null; rc=$?
out=$(cat "$SANDBOX/noresolver.out")
check "resolver_undefined: rc" 2 "$rc"
check "resolver_undefined: first line" "lane_check=error" "$(printf '%s\n' "$out" | sed -n 1p)"
check "resolver_undefined: trigger" "trigger=check-error" "$(printf '%s\n' "$out" | sed -n 2p)"

# --- empty_diff -------------------------------------------------------------
R="$SANDBOX/empty"; mkrepo "$R"
out=$(adlc_lane_check "$R" main); rc=$?
check "empty_diff: rc" 2 "$rc"
check "empty_diff: detail" "detail=empty diff against main" "$(printf '%s\n' "$out" | sed -n 3p)"

# --- relative_home -----------------------------------------------------------
# A relative HOME would make the "installed" engine resolve inside the tree under
# check. Refused before any engine runs.
R="$SANDBOX/relhome"; mkrepo "$R"; commit_files "$R" src/a.txt
out=$(HOME=. adlc_lane_check "$R" main 2>/dev/null); rc=$?
check "relative_home: rc" 2 "$rc"
check "relative_home: first line" "lane_check=error" "$(printf '%s\n' "$out" | sed -n 1p)"

# --- relative_toolkit_root --------------------------------------------------
# REQ-669: the same refusal for a relative ADLC_TOOLKIT_ROOT.
out=$(ADLC_TOOLKIT_ROOT=. adlc_lane_check "$R" main 2>/dev/null); rc=$?
check "relative_toolkit_root: rc" 2 "$rc"
check "relative_toolkit_root: detail" "detail=ADLC_TOOLKIT_ROOT is not an absolute path" "$(printf '%s\n' "$out" | sed -n 3p)"

# --- engine_inside_worktree -------------------------------------------------
# LESSON-718: ToolkitRoot pointed at the tree under check (a dev session's
# --plugin-dir, or a stale pointer) must not run that tree's engine. The planted
# engine prints a pass and leaves a marker; it must never run.
R="$SANDBOX/selfload"; mkrepo "$R"
SELF_RAN="$SANDBOX/selfload-ran"
for d in "$R/tools/adlc" "$R/.adlc/tools/adlc"; do
  mkdir -p "$d"
  printf 'import sys\nopen(%s, "w").close()\nprint("lane_check=pass")\nprint("files_counted=0")\nsys.exit(0)\n' "'$SELF_RAN'" > "$d/lane_check.py"
done
commit_files "$R" src/a.txt
out=$(ADLC_TOOLKIT_ROOT="$R"; export ADLC_TOOLKIT_ROOT; adlc_lane_check "$R" main 2>/dev/null); rc=$?
check "engine_inside_worktree: rc" 2 "$rc"
check "engine_inside_worktree: output" "lane_check=error
trigger=check-error
detail=the engine is inside the worktree under check" "$out"
err=$(ADLC_TOOLKIT_ROOT="$R"; export ADLC_TOOLKIT_ROOT; adlc_lane_check "$R" main 2>&1 >/dev/null)
check "engine_inside_worktree: stderr says why" "1" "$(printf '%s\n' "$err" | grep -c 'is inside the worktree under check')"
out=$(ADLC_TOOLKIT_ROOT="$R/.adlc"; export ADLC_TOOLKIT_ROOT; adlc_lane_check "$R" main 2>/dev/null); rc=$?
check "engine_inside_worktree: a copy vendored in the tree: rc" 2 "$rc"
check "engine_inside_worktree: a copy vendored in the tree: detail" "detail=the engine is inside the worktree under check" "$(printf '%s\n' "$out" | sed -n 3p)"
ln -s "$R" "$SANDBOX/selfload-link"
out=$(ADLC_TOOLKIT_ROOT="$R"; export ADLC_TOOLKIT_ROOT; adlc_lane_check "$SANDBOX/selfload-link" main 2>/dev/null); rc=$?
check "engine_inside_worktree: the worktree named through a symlink: rc" 2 "$rc"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/selfload-link"; export ADLC_TOOLKIT_ROOT; adlc_lane_check "$R" main 2>/dev/null); rc=$?
check "engine_inside_worktree: the root named through a symlink: rc" 2 "$rc"
check "engine_inside_worktree: the planted engine never ran" "no" "$([ -e "$SELF_RAN" ] && echo yes || echo no)"

# --- worktree_inside_toolkit (benign) ---------------------------------------
# The toolkit's own layout: worktrees under <root>/.claude/worktrees/. The engine
# is at <root>/tools/adlc, outside the worktree, so it runs. <root>/tools is a
# symlink to this checkout's tools/, so the engine is the real one.
TKH="$SANDBOX/tkhost"
mkdir -p "$TKH/.claude/worktrees" && ln -s "$TOOLKIT/tools" "$TKH/tools"
R="$TKH/.claude/worktrees/w"; mkrepo "$R"; commit_files "$R" src/a.txt
out=$(ADLC_TOOLKIT_ROOT="$TKH"; export ADLC_TOOLKIT_ROOT; adlc_lane_check "$R" main); rc=$?
check "worktree_inside_toolkit: rc" 0 "$rc"
check "worktree_inside_toolkit: first line" "lane_check=pass" "$(printf '%s\n' "$out" | sed -n 1p)"

# --- set_u_home_unset -------------------------------------------------------
# The partial's own source of forge.sh reads a bare $HOME in its fallback operand;
# with HOME and ADLC_TOOLKIT_ROOT unset a `set -u` caller must not abort on it.
# Native zsh sets HOME itself when it is unset, so zsh runs in sh emulation here.
SETU="$SANDBOX/setu.sh"
printf '%s\n' 'set -u' ". '$PARTIALS/lane-check.sh'" 'adlc_lane_check "$1" main; printf "rc=%s\n" "$?"' > "$SETU"
case "$SUT" in
  *zsh) setu_out=$(cd "$SANDBOX" && env -u HOME -u ADLC_TOOLKIT_ROOT "$SUT" --emulate sh "$SETU" "$R" 2>/dev/null) ;;
  *) setu_out=$(cd "$SANDBOX" && env -u HOME -u ADLC_TOOLKIT_ROOT "$SUT" "$SETU" "$R" 2>/dev/null) ;;
esac
check "set_u_home_unset: sourced and called without aborting" "rc=2" "$(printf '%s\n' "$setu_out" | tail -n 1)"
check "set_u_home_unset: the call is a check-error" "trigger=check-error" "$(printf '%s\n' "$setu_out" | sed -n 2p)"

# --- summary ----------------------------------------------------------------
# Case-count floor: a harness that ran nothing must not read as a pass.
echo "lane-check.test.sh: $CASES cases executed"
if [ "$CASES" -lt 40 ]; then
  echo "lane-check.test.sh: FAIL — expected at least 40 cases, ran $CASES ($SUT)"
  exit 1
fi
if [ "$FAILS" -eq 0 ]; then
  echo "lane-check.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "lane-check.test.sh: $FAILS FAILURE(S) ($SUT)"
exit 1
