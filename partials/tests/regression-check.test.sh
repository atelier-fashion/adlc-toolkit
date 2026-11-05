#!/bin/sh
# partials/tests/regression-check.test.sh — REQ-691: the regression-test setting and
# check, end to end through the sourced wrapper (TASK-239).
#
# tools/adlc/tests/test_regression_check.py covers every rule of the engine. This
# harness proves the shell half: that `adlc_regression_check` runs the installed
# engine under bash, zsh, /bin/sh and dash, hands its stdout and exit code through
# unchanged, and turns every run that breaks the contract into an error, never a
# pass and never off (BR-17). Every case asserts on the verdict lines, not on the
# exit status alone (LESSON-754).
#
#   mode_absent_config_is_off (BR-1, benign) — no config, a config without the key,
#                           and the current directory as the root -> `regression-test: off`;
#                           `check` there -> `regression-check: off`; `required` and a bad
#                           value pass through as the engine prints them
#   no_config_needs_no_engine (BR-1, benign) — no config and no --base: the wrapper's own
#                           off lines, rc 0, with no engine and no resolver, equal to the
#                           engine's real output (parity, so they cannot drift); a config,
#                           --base, an argument it cannot stand in for, a config symlink or
#                           an `.adlc` file -> the engine is needed, and a missing one is an error
#   check_pass_and_fail_verdicts (BR-10, benign) — a bug whose test is tracked and cites
#                           it -> pass, rc 0, the counts line; a second bug whose test is
#                           missing -> fail, rc 1, the counts line and its `BUG-nnn:` line;
#                           named ids and --require-recorded pass through; the wrapper's
#                           stdout and rc equal the engine run directly; the engine's stderr
#                           passes through unchanged
#   check_off_verdict (BR-11, benign) — a report that fails under `required` is never
#                           read under `off`, set or absent -> `regression-check: off`, rc 0,
#                           its reason line and no counts line
#   wrapper_errors_never_read_as_off (BR-17) — a missing engine (root set, or none under
#                           HOME), a relative ADLC_TOOLKIT_ROOT or HOME, an engine stubbed to
#                           print nothing, an exit outside the verb's contract, a verdict
#                           that does not match its code or its verb, a missing interpreter,
#                           an undefined or empty resolver, a bad verb, and an engine inside
#                           the tree under check (LESSON-718), also named in another letter
#                           case -> the verb's error verdict and rc 2, with no pass or off
#                           line leaking through; stderr names the engine by route, never by
#                           an absolute path under HOME
#   install_checkout_is_exempt (benign for mode) — the symlink install's own checkout as the
#                           root: `mode` runs (required or off, whatever the checkout says,
#                           LESSON-745); `check` there, and the same tree without the symlink
#                           install, stay refused
#   forge_from_cwd_never_sourced (LESSON-718) — a .adlc/partials/forge.sh in the current
#                           directory (a planted resolver, or a stale copy without one) is never
#                           sourced: the installed forge.sh is, and the installed engine runs
#   dotdot_root_goes_to_engine — a --root with a `..` segment never gets the no-config answer
#                           (with no engine installed it is an error, not off), and the
#                           inside-tree test sees it lexically, as the engine does: a root
#                           `proj/link/..` whose link leads out of proj is still proj, so an
#                           engine vendored in proj is refused (benign: a `..` root with a
#                           config reaches the real engine)
#   root_inside_toolkit (benign) — the root sits under the toolkit root, as the toolkit's
#                           own worktrees do; the engine is not inside it and runs
#   set_u_home_unset      — sourced by a `set -u` shell with HOME and ADLC_TOOLKIT_ROOT
#                           unset: no abort, and the call is an error
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL). HOME is pointed
# at a sandbox whose ~/.claude/skills is THIS toolkit checkout. The wrapper only
# ever runs the installed toolkit's engine, so that is how the engine under test
# is the one it finds; no global git config (signing, hooks) leaks into the
# sandbox repos either. Every call names its root with --root, or runs in a
# subshell that cd's into one: run from the checkout, the checkout is the tree
# under check and the wrapper refuses it (a case below pins that).

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
nth() { printf '%s\n' "$1" | sed -n "$2p"; }       # nth <text> <n> — the n-th line
count() { printf '%s\n' "$1" | command grep -c -- "$2"; }  # count <text> <regex> — matching lines (LESSON-717)
countf() { printf '%s\n' "$1" | command grep -cF -- "$2"; }  # countf <text> <string> — lines holding it
mode_verdict() { # mode_verdict <line> — yes when it is one of mode's two rc-0 verdicts
  case $1 in
    'regression-test: required' | 'regression-test: off') echo yes ;;
    *) echo no ;;
  esac
}

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-regcheck.XXXXXX") || { echo "regression-check.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "regression-check.test.sh: sandbox path invalid" >&2; exit 1; }
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

mkdir -p "$SANDBOX/home/.claude" && ln -s "$TOOLKIT" "$SANDBOX/home/.claude/skills"
HOME="$SANDBOX/home"; export HOME
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
# REQ-669: the symlink route is the default here; the cases that exercise
# ToolkitRoot set ADLC_TOOLKIT_ROOT themselves.
unset ADLC_TOOLKIT_ROOT CLAUDE_PLUGIN_ROOT

# forge.sh first, from this checkout, so regression-check.sh finds
# `_adlc_forge_python` already defined and does not go looking for an installed copy.
. "$PARTIALS/forge.sh"
. "$PARTIALS/regression-check.sh"

# mkproj <dir> <none|absent|required|off|sometimes> — a git repo and its config:
# none writes no .adlc/config.yml, absent writes one without the key.
mkproj() {
  mp_d=$1
  mkdir -p "$mp_d" && git -C "$mp_d" init -q -b main . || return 1
  case $2 in
    none) ;;
    absent) mkdir -p "$mp_d/.adlc" && printf 'project: fixture\n' > "$mp_d/.adlc/config.yml" ;;
    *) mkdir -p "$mp_d/.adlc" && printf 'bugfix:\n  regression_test: %s\n' "$2" > "$mp_d/.adlc/config.yml" ;;
  esac
  return 0
}
# setmode <dir> <absent|required|off> — rewrite the config in place.
setmode() {
  case $2 in
    absent) printf 'project: fixture\n' > "$1/.adlc/config.yml" ;;
    *) printf 'bugfix:\n  regression_test: %s\n' "$2" > "$1/.adlc/config.yml" ;;
  esac
}
# bug <dir> <BUG-nnn> <status> <regression_tests value> <regression_waiver value>
bug() {
  mkdir -p "$1/.adlc/bugs"
  printf '%s\n' '---' "id: $2" "status: $3" "regression_tests: $4" "regression_waiver: $5" '---' '' "# $2" > "$1/.adlc/bugs/$2-fixture.md"
}
# regtest <dir> <path> <BUG-nnn> — a tracked test file that cites the bug.
regtest() {
  mkdir -p "$1/$(dirname -- "$2")" && printf 'def test_regression():  # %s\n    assert True\n' "$3" > "$1/$2" && git -C "$1" add -- "$2"
}
# mkstub <name> <python line>... — a toolkit root whose engine is the given lines.
mkstub() {
  ms_n=$1; shift
  mkdir -p "$SANDBOX/stubs/$ms_n/tools/adlc"
  printf '%s\n' "$@" > "$SANDBOX/stubs/$ms_n/tools/adlc/regression_check.py"
}

# --- mode_absent_config_is_off (BR-1, benign path) --------------------------
R="$SANDBOX/noconfig"; mkproj "$R" none
out=$(adlc_regression_check mode --root "$R"); rc=$?
check "mode_absent_config_is_off: no config: rc" 0 "$rc"
check "mode_absent_config_is_off: no config: verdict" "regression-test: off" "$(nth "$out" 1)"
check "mode_absent_config_is_off: no config: says there is no config file" "1" "$(count "$(nth "$out" 2)" '^\.adlc/config\.yml does not exist')"
check "mode_absent_config_is_off: no config: names the key that turns it on" "1" "$(count "$(nth "$out" 2)" 'set bugfix\.regression_test: required')"
out=$(cd "$R" && adlc_regression_check mode); rc=$?
check "mode_absent_config_is_off: the current directory as the root: rc" 0 "$rc"
check "mode_absent_config_is_off: the current directory as the root: verdict" "regression-test: off" "$(nth "$out" 1)"
out=$(adlc_regression_check check --root "$R"); rc=$?
check "mode_absent_config_is_off: check with no config: rc" 0 "$rc"
check "mode_absent_config_is_off: check with no config: verdict" "regression-check: off" "$(nth "$out" 1)"
check "mode_absent_config_is_off: check with no config: no counts line" "0" "$(count "$out" '^passed=')"
R="$SANDBOX/nokey"; mkproj "$R" absent
out=$(adlc_regression_check mode --root "$R"); rc=$?
check "mode_absent_config_is_off: config without the key: rc" 0 "$rc"
check "mode_absent_config_is_off: config without the key: verdict" "regression-test: off" "$(nth "$out" 1)"
check "mode_absent_config_is_off: config without the key: says the key is not set" "1" "$(count "$(nth "$out" 2)" '^bugfix\.regression_test is not set in \.adlc/config\.yml')"
R="$SANDBOX/required"; mkproj "$R" required
out=$(adlc_regression_check mode --root "$R"); rc=$?
check "mode_absent_config_is_off: required passes through: rc" 0 "$rc"
check "mode_absent_config_is_off: required passes through: output" "regression-test: required
bugfix.regression_test is required in .adlc/config.yml" "$out"
R="$SANDBOX/badvalue"; mkproj "$R" sometimes
out=$(adlc_regression_check mode --root "$R"); rc=$?
check "mode_absent_config_is_off: a bad value is the engine's error: rc" 2 "$rc"
check "mode_absent_config_is_off: a bad value is the engine's error: verdict" "regression-test: error" "$(nth "$out" 1)"
check "mode_absent_config_is_off: a bad value is the engine's error: names the value" "1" "$(count "$(nth "$out" 2)" 'sometimes')"

# --- no_config_needs_no_engine (BR-1, benign path) ---------------------------
# No config and no --base: the answer needs no engine and no interpreter. The
# root names no engine at all, so a line that came from anywhere but the wrapper
# would be an error here.
mkdir -p "$SANDBOX/emptyroot"
NOCFG_WHY='.adlc/config.yml does not exist, which means off; set bugfix.regression_test: required in it to turn regression tests on'
R="$SANDBOX/noconfig"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R"); rc=$?
check "no_config_needs_no_engine: mode with no engine: rc" 0 "$rc"
check "no_config_needs_no_engine: mode with no engine: output" "regression-test: off
$NOCFG_WHY" "$out"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --require-recorded --root "$R" BUG-123); rc=$?
check "no_config_needs_no_engine: check with no engine: rc" 0 "$rc"
check "no_config_needs_no_engine: check with no engine: output" "regression-check: off
regression tests are off for this project: $NOCFG_WHY" "$out"
( unset -f _adlc_forge_python 2>/dev/null || unfunction _adlc_forge_python 2>/dev/null
  cd "$R" && adlc_regression_check mode ) > "$SANDBOX/nocfg-noresolver.out" 2>/dev/null; rc=$?
out=$(cat "$SANDBOX/nocfg-noresolver.out")
check "no_config_needs_no_engine: no resolver, the current directory as the root: rc" 0 "$rc"
check "no_config_needs_no_engine: no resolver, the current directory as the root: verdict" "regression-test: off" "$(nth "$out" 1)"
# Parity: the wrapper's lines are the engine's real no-config output, line for line.
for v in mode check; do
  wrapped=$(adlc_regression_check "$v" --root "$R"); wrapped_rc=$?
  direct=$(command "$(_adlc_forge_python)" -E "$TOOLKIT/tools/adlc/regression_check.py" "$v" --root "$R"); direct_rc=$?
  check "no_config_needs_no_engine: $v parity with the engine: rc" "$direct_rc" "$wrapped_rc"
  check "no_config_needs_no_engine: $v parity with the engine: stdout" "$direct" "$wrapped"
done
# Where the engine would read something else, the engine is needed: with none
# installed, each is the verb's error, never off.
R="$SANDBOX/nokey"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R" 2>/dev/null); rc=$?
check "no_config_needs_no_engine: a config and no engine: rc" 2 "$rc"
check "no_config_needs_no_engine: a config and no engine: output" "regression-test: error
regression_check.py not found in the installed toolkit" "$out"
R="$SANDBOX/noconfig"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --require-recorded --base refs/remotes/origin/main --root "$R" BUG-123 2>/dev/null); rc=$?
check "no_config_needs_no_engine: --base goes to the engine: rc" 2 "$rc"
check "no_config_needs_no_engine: --base goes to the engine: verdict" "regression-check: error" "$(nth "$out" 1)"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --base=refs/remotes/origin/main --root "$R" 2>/dev/null); rc=$?
check "no_config_needs_no_engine: --base=REF goes to the engine: rc" 2 "$rc"
for a in --bogus BUG-12a -- BUG-123; do
  out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R" "$a" 2>/dev/null); rc=$?
  check "no_config_needs_no_engine: mode with '$a' goes to the engine: rc" 2 "$rc"
done
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" BUG-12a 2>/dev/null); rc=$?
check "no_config_needs_no_engine: check with a bad id goes to the engine: rc" 2 "$rc"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root 2>/dev/null); rc=$?
check "no_config_needs_no_engine: --root with no value goes to the engine: rc" 2 "$rc"
R="$SANDBOX/cfglink"; mkproj "$R" none; mkdir -p "$R/.adlc" && ln -s "$R/nowhere.yml" "$R/.adlc/config.yml"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R" 2>/dev/null); rc=$?
check "no_config_needs_no_engine: a config symlink that does not resolve: rc" 2 "$rc"
check "no_config_needs_no_engine: a config symlink that does not resolve: verdict" "regression-test: error" "$(nth "$out" 1)"
R="$SANDBOX/adlcfile"; mkproj "$R" none; printf 'not a directory\n' > "$R/.adlc"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R" 2>/dev/null); rc=$?
check "no_config_needs_no_engine: .adlc is a file: rc" 2 "$rc"

# --- check_pass_and_fail_verdicts (BR-10, benign path) ----------------------
R="$SANDBOX/passfail"; mkproj "$R" required
regtest "$R" tests/test_bug_001.py BUG-001
bug "$R" BUG-001 resolved '["tests/test_bug_001.py"]' '""'
out=$(adlc_regression_check check --root "$R"); rc=$?
check "check_pass_and_fail_verdicts: pass: rc" 0 "$rc"
check "check_pass_and_fail_verdicts: pass: verdict" "regression-check: pass" "$(nth "$out" 1)"
check "check_pass_and_fail_verdicts: pass: counts line" "passed=1 waived=0 legacy=0 failed=0" "$(nth "$out" 2)"
check "check_pass_and_fail_verdicts: pass: no failure lines" "0" "$(count "$out" '^BUG-')"
bug "$R" BUG-002 resolved '["tests/missing.py"]' '""'
out=$(adlc_regression_check check --root "$R"); rc=$?
check "check_pass_and_fail_verdicts: fail: rc" 1 "$rc"
check "check_pass_and_fail_verdicts: fail: verdict" "regression-check: fail" "$(nth "$out" 1)"
check "check_pass_and_fail_verdicts: fail: counts line" "passed=1 waived=0 legacy=0 failed=1" "$(nth "$out" 2)"
check "check_pass_and_fail_verdicts: fail: the failed bug's line" "BUG-002: tests/missing.py does not exist" "$(nth "$out" 3)"
check "check_pass_and_fail_verdicts: fail: one failure line" "1" "$(count "$out" '^BUG-')"
out=$(adlc_regression_check check --root "$R" BUG-001); rc=$?
check "check_pass_and_fail_verdicts: a named passing id: rc" 0 "$rc"
check "check_pass_and_fail_verdicts: a named passing id: output" "regression-check: pass
passed=1 waived=0 legacy=0 failed=0" "$out"
bug "$R" BUG-003 open '[]' '""'
out=$(adlc_regression_check check --require-recorded --root "$R" BUG-003); rc=$?
check "check_pass_and_fail_verdicts: --require-recorded on a legacy bug: rc" 1 "$rc"
check "check_pass_and_fail_verdicts: --require-recorded on a legacy bug: verdict" "regression-check: fail" "$(nth "$out" 1)"
check "check_pass_and_fail_verdicts: --require-recorded on a legacy bug: its line" "BUG-003: neither regression_tests nor regression_waiver is recorded" "$(nth "$out" 3)"
out=$(adlc_regression_check check --root "$R" BUG-009); rc=$?
check "check_pass_and_fail_verdicts: a named id with no report: rc" 1 "$rc"
check "check_pass_and_fail_verdicts: a named id with no report: its line" "BUG-009: no bug report in .adlc/bugs" "$(nth "$out" 3)"
# The wrapper adds nothing and drops nothing: same stdout, same rc, as running the
# engine by path with the interpreter the wrapper itself resolves.
wrapped=$(adlc_regression_check check --root "$R"); wrapped_rc=$?
direct=$(command "$(_adlc_forge_python)" -E "$TOOLKIT/tools/adlc/regression_check.py" check --root "$R"); direct_rc=$?
check "check_pass_and_fail_verdicts: passthrough: rc identical" "$direct_rc" "$wrapped_rc"
check "check_pass_and_fail_verdicts: passthrough: stdout identical" "$direct" "$wrapped"
# The engine's stderr reaches the caller byte for byte: the wrapper swallows none
# of it and adds nothing to it on a run in the contract.
mkstub stderr 'import sys' 'sys.stderr.write("engine note: one\nengine note: two\n")' 'print("regression-check: pass")' 'print("passed=0 waived=0 legacy=0 failed=0")' 'sys.exit(0)'
err=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/stderr"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>&1 >/dev/null)
check "check_pass_and_fail_verdicts: the engine's stderr passes through unchanged" "engine note: one
engine note: two" "$err"

# --- check_off_verdict (BR-11, benign path) ---------------------------------
# A resolved report with both fields set fails under `required`, so a run that read
# it could not print off. Under `off`, set or absent, it is never opened.
R="$SANDBOX/off"; mkproj "$R" required
bug "$R" BUG-004 resolved '["tests/whatever.py"]' '"and a waiver"'
out=$(adlc_regression_check check --root "$R"); rc=$?
check "check_off_verdict: the same report under required fails: rc" 1 "$rc"
check "check_off_verdict: the same report under required fails: its line" "1" "$(count "$out" '^BUG-004: regression_tests and regression_waiver are both set')"
setmode "$R" off
out=$(adlc_regression_check check --root "$R"); rc=$?
check "check_off_verdict: off set: rc" 0 "$rc"
check "check_off_verdict: off set: output" "regression-check: off
regression tests are off for this project: bugfix.regression_test is off in .adlc/config.yml" "$out"
setmode "$R" absent
out=$(adlc_regression_check check --root "$R"); rc=$?
check "check_off_verdict: key absent: rc" 0 "$rc"
check "check_off_verdict: key absent: verdict" "regression-check: off" "$(nth "$out" 1)"
check "check_off_verdict: key absent: reason line names the key" "1" "$(count "$(nth "$out" 2)" '^regression tests are off for this project: bugfix\.regression_test is not set')"
check "check_off_verdict: key absent: no counts line" "0" "$(count "$out" '^passed=')"
check "check_off_verdict: key absent: no bug line" "0" "$(count "$out" '^BUG-')"
out=$(adlc_regression_check mode --root "$R"); rc=$?
check "check_off_verdict: mode agrees: verdict" "regression-test: off" "$(nth "$out" 1)"

# --- wrapper_errors_never_read_as_off (BR-17) -------------------------------
# Every case runs against a project whose config sets off, where the real engine
# would print off: an error that leaked an off line would read as a pass. A config
# is there so the wrapper's no-config answer cannot stand in for the engine.
R="$SANDBOX/errors"; mkproj "$R" off

# A missing engine: ADLC_TOOLKIT_ROOT names a root with no engine. HOME's install
# (this checkout, which has one) is NOT consulted: the two never mix.
mkdir -p "$SANDBOX/emptyroot"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: missing engine, root set: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: missing engine, root set: output" "regression-check: error
regression_check.py not found in the installed toolkit" "$out"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: missing engine, mode: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: missing engine, mode: verdict" "regression-test: error" "$(nth "$out" 1)"
# A missing engine: no ADLC_TOOLKIT_ROOT, and HOME has no ~/.claude/skills.
mkdir -p "$SANDBOX/emptyhome"
out=$(HOME="$SANDBOX/emptyhome"; export HOME; unset ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: missing engine under HOME: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: missing engine under HOME: verdict" "regression-check: error" "$(nth "$out" 1)"
err=$(HOME="$SANDBOX/emptyhome"; export HOME; unset ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>&1 >/dev/null)
check "wrapper_errors_never_read_as_off: missing engine: stderr names the symlink route" "1" "$(count "$err" 'install\.sh')"
check "wrapper_errors_never_read_as_off: missing engine: stderr names the plugin route" "1" "$(count "$err" 'claude plugin install adlc@adlc-toolkit')"
check "wrapper_errors_never_read_as_off: missing engine under HOME: stderr names the engine by route" "1" "$(countf "$err" '<ToolkitRoot>/tools/adlc/regression_check.py (ToolkitRoot is the symlink install under HOME)')"
check "wrapper_errors_never_read_as_off: missing engine under HOME: stderr holds no absolute path under HOME" "0" "$(countf "$err" "$SANDBOX")"
err=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>&1 >/dev/null)
check "wrapper_errors_never_read_as_off: missing engine, root set: stderr names the engine by route" "1" "$(countf "$err" '<ToolkitRoot>/tools/adlc/regression_check.py (ToolkitRoot from ADLC_TOOLKIT_ROOT)')"
check "wrapper_errors_never_read_as_off: missing engine, root set: stderr holds no absolute path" "0" "$(countf "$err" "$SANDBOX")"

# A relative ADLC_TOOLKIT_ROOT is refused before it is resolved, even one that
# would reach a real engine from the current directory.
out=$(cd "$TOOLKIT/.." && ADLC_TOOLKIT_ROOT=$(basename -- "$TOOLKIT"); export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: relative ADLC_TOOLKIT_ROOT: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: relative ADLC_TOOLKIT_ROOT: output" "regression-check: error
ADLC_TOOLKIT_ROOT is not an absolute path" "$out"
out=$(ADLC_TOOLKIT_ROOT=.; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: relative ADLC_TOOLKIT_ROOT, mode: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: relative ADLC_TOOLKIT_ROOT, mode: verdict" "regression-test: error" "$(nth "$out" 1)"
out=$(HOME=.; export HOME; unset ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: relative HOME: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: relative HOME: output" "regression-check: error
HOME is not an absolute path" "$out"

# An engine stubbed to print nothing and exit 0.
mkstub empty 'import sys' 'sys.exit(0)'
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/empty"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: engine prints nothing: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: engine prints nothing: output" "regression-check: error
regression_check.py exited 0 without a 'regression-check: pass' or 'regression-check: off' line" "$out"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/empty"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: engine prints nothing, mode: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: engine prints nothing, mode: output" "regression-test: error
regression_check.py exited 0 without a 'regression-test: required' or 'regression-test: off' line" "$out"

# Nothing printed with a code that has one verdict (check 1, mode 2): an empty
# first line must not match an empty second verdict.
mkstub emptyrc1 'import sys' 'sys.exit(1)'
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/emptyrc1"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: engine prints nothing and exits 1: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: engine prints nothing and exits 1: output" "regression-check: error
regression_check.py exited 1 without a 'regression-check: fail' line" "$out"
mkstub emptyrc2 'import sys' 'sys.exit(2)'
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/emptyrc2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: engine prints nothing and exits 2, mode: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: engine prints nothing and exits 2, mode: output" "regression-test: error
regression_check.py exited 2 without a 'regression-test: error' line" "$out"

# An exit code outside the contract, after a pass line: the lines are withheld.
mkstub exit7 'import sys' 'print("regression-check: pass")' 'print("passed=1 waived=0 legacy=0 failed=0")' 'sys.exit(7)'
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/exit7"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: exit 7 after a pass line: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: exit 7 after a pass line: output" "regression-check: error
regression_check.py exited 7" "$out"

# A verdict that does not match its code: a pass line with rc 1.
mkstub passrc1 'import sys' 'print("regression-check: pass")' 'print("passed=1 waived=0 legacy=0 failed=0")' 'sys.exit(1)'
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/passrc1"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: a pass line with rc 1: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: a pass line with rc 1: verdict" "regression-check: error" "$(nth "$out" 1)"
check "wrapper_errors_never_read_as_off: a pass line with rc 1: no pass line leaks" "0" "$(count "$out" '^regression-check: pass')"

# An off line with rc 2 is an error, not off.
mkstub offrc2 'import sys' 'print("regression-check: off")' 'sys.exit(2)'
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/offrc2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: an off line with rc 2: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: an off line with rc 2: output" "regression-check: error
regression_check.py exited 2 without a 'regression-check: error' line" "$out"

# The other verb's off is not this verb's off.
mkstub modeoff 'import sys' 'print("regression-test: off")' 'sys.exit(0)'
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/modeoff"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: check given mode's off: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: check given mode's off: verdict" "regression-check: error" "$(nth "$out" 1)"
check "wrapper_errors_never_read_as_off: check given mode's off: no off line leaks" "0" "$(count "$out" ': off$')"
mkstub checkoff 'import sys' 'print("regression-check: off")' 'sys.exit(0)'
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/checkoff"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: mode given check's off: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: mode given check's off: verdict" "regression-test: error" "$(nth "$out" 1)"
check "wrapper_errors_never_read_as_off: mode given check's off: no off line leaks" "0" "$(count "$out" ': off$')"
# `mode` never exits 1: an off line with rc 1 is outside its contract.
mkstub modeoffrc1 'import sys' 'print("regression-test: off")' 'sys.exit(1)'
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/stubs/modeoffrc1"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: mode exits 1: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: mode exits 1: output" "regression-test: error
regression_check.py exited 1" "$out"

# A missing interpreter (127), an undefined resolver, and one that prints nothing.
( _adlc_forge_python() { printf '%s\n' "$SANDBOX/no-such-python3"; }; adlc_regression_check check --root "$R" ) > "$SANDBOX/nopy.out" 2>/dev/null; rc=$?
out=$(cat "$SANDBOX/nopy.out")
check "wrapper_errors_never_read_as_off: interpreter missing: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: interpreter missing: output" "regression-check: error
regression_check.py exited 127" "$out"
( unset -f _adlc_forge_python 2>/dev/null || unfunction _adlc_forge_python 2>/dev/null
  adlc_regression_check mode --root "$R" ) > "$SANDBOX/noresolver.out" 2>/dev/null; rc=$?
out=$(cat "$SANDBOX/noresolver.out")
check "wrapper_errors_never_read_as_off: resolver undefined: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: resolver undefined: output" "regression-test: error
interpreter resolver _adlc_forge_python is not defined" "$out"
( _adlc_forge_python() { :; }; adlc_regression_check check --root "$R" ) > "$SANDBOX/emptyresolver.out" 2>/dev/null; rc=$?
out=$(cat "$SANDBOX/emptyresolver.out")
check "wrapper_errors_never_read_as_off: resolver prints nothing: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: resolver prints nothing: verdict" "regression-check: error" "$(nth "$out" 1)"

# A bad verb, or none: refused before any engine runs.
out=$(adlc_regression_check 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: no verb: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: no verb: output" "regression-check: error
usage: adlc_regression_check <mode|check> [args...]" "$out"
out=$(adlc_regression_check status --root "$R" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: unknown verb: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: unknown verb: verdict" "regression-check: error" "$(nth "$out" 1)"

# LESSON-718: an engine inside the tree under check is that tree's own copy. The
# planted engine prints off and leaves a marker; it must never run, whichever way
# the root is named. The tree has a config, so a refusal that failed would reach
# the planted engine rather than the wrapper's no-config answer.
R2="$SANDBOX/selfload"; mkproj "$R2" off
SELF_RAN="$SANDBOX/selfload-ran"
for d in "$R2/tools/adlc" "$R2/.adlc/tools/adlc"; do
  mkdir -p "$d"
  printf 'import sys\nopen(%s, "w").close()\nprint("regression-check: off")\nsys.exit(0)\n' "'$SELF_RAN'" > "$d/regression_check.py"
done
out=$(ADLC_TOOLKIT_ROOT="$R2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R2" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: engine inside the root: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: engine inside the root: output" "regression-check: error
the engine is inside the tree under check" "$out"
err=$(ADLC_TOOLKIT_ROOT="$R2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R2" 2>&1 >/dev/null)
check "wrapper_errors_never_read_as_off: engine inside the root: stderr says why" "1" "$(count "$err" 'is inside the tree under check')"
check "wrapper_errors_never_read_as_off: engine inside the root: stderr holds no absolute path" "0" "$(countf "$err" "$SANDBOX")"
out=$(ADLC_TOOLKIT_ROOT="$R2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R2" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: engine inside the root, mode: output" "regression-test: error
the engine is inside the tree under check" "$out"
out=$(cd "$R2" && ADLC_TOOLKIT_ROOT="$R2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: engine inside the current directory: rc" 2 "$rc"
out=$(ADLC_TOOLKIT_ROOT="$R2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root="$R2" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: engine inside --root=DIR: rc" 2 "$rc"
out=$(cd "$R2" && ADLC_TOOLKIT_ROOT="$R2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root= 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: an empty --root= is the current directory: rc" 2 "$rc"
out=$(ADLC_TOOLKIT_ROOT="$R2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R" --root "$R2" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: the last --root wins, as the engine reads it: rc" 2 "$rc"
check "wrapper_errors_never_read_as_off: the last --root wins: detail" "the engine is inside the tree under check" "$(nth "$out" 2)"
out=$(ADLC_TOOLKIT_ROOT="$R2/.adlc"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R2" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: a copy vendored in the tree: rc" 2 "$rc"
ln -s "$R2" "$SANDBOX/selfload-link"
out=$(ADLC_TOOLKIT_ROOT="$R2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$SANDBOX/selfload-link" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: the root named through a symlink: rc" 2 "$rc"
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/selfload-link"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R2" 2>/dev/null); rc=$?
check "wrapper_errors_never_read_as_off: ADLC_TOOLKIT_ROOT named through a symlink: rc" 2 "$rc"
# The same directory spelled in another letter case. On a case-insensitive
# filesystem it is the same tree, and bash and /bin/sh keep the typed case in
# `pwd -P`, so only a case-folded comparison sees the engine inside it. On a
# case-sensitive filesystem the spelling names no directory and the case is moot.
mkdir -p "$SANDBOX/CaseProbe"
if [ -d "$SANDBOX/caseprobe" ]; then
  R2UP="$(dirname -- "$R2")/$(basename -- "$R2" | command tr '[:lower:]' '[:upper:]')"
  out=$(ADLC_TOOLKIT_ROOT="$R2UP"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$R2" 2>/dev/null); rc=$?
  check "wrapper_errors_never_read_as_off: ADLC_TOOLKIT_ROOT naming the tree in upper case: rc" 2 "$rc"
  check "wrapper_errors_never_read_as_off: ADLC_TOOLKIT_ROOT naming the tree in upper case: output" "regression-check: error
the engine is inside the tree under check" "$out"
  out=$(ADLC_TOOLKIT_ROOT="$R2"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R2UP" 2>/dev/null); rc=$?
  check "wrapper_errors_never_read_as_off: the root named in upper case: rc" 2 "$rc"
else
  echo "SKIP: wrapper_errors_never_read_as_off: letter-case spellings — $SANDBOX is on a case-sensitive filesystem"
fi
check "wrapper_errors_never_read_as_off: the planted engine never ran" "no" "$([ -e "$SELF_RAN" ] && echo yes || echo no)"
# The symlink route's self-hosting shape: the toolkit's own checkout as the root,
# with ~/.claude/skills pointing at it. That tree IS the install, so `mode` runs
# (benign path): /bugfix on the toolkit itself must not stop before Phase 1. The
# answer is whatever this checkout's own config says (LESSON-745), so either
# verdict passes; an error does not.
out=$(cd "$TOOLKIT" && adlc_regression_check mode 2>/dev/null); rc=$?
check "install_checkout_is_exempt: the install's own checkout as the root: rc" 0 "$rc"
check "install_checkout_is_exempt: the install's own checkout as the root: verdict" "yes" "$(mode_verdict "$(nth "$out" 1)")"
out=$(cd "$TOOLKIT" && ADLC_TOOLKIT_ROOT="$TOOLKIT"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode 2>/dev/null); rc=$?
check "install_checkout_is_exempt: ADLC_TOOLKIT_ROOT naming the same install: rc" 0 "$rc"
# `check` is the gate, and the gate never runs in the tree it judges, the
# install's own clone included: the toolkit's /bugfix runs it from a fix worktree.
out=$(cd "$TOOLKIT" && adlc_regression_check check --require-recorded BUG-001 2>/dev/null); rc=$?
check "install_checkout_is_exempt: check in the install's own checkout: rc" 2 "$rc"
check "install_checkout_is_exempt: check in the install's own checkout: output" "regression-check: error
the engine is inside the tree under check" "$out"
out=$(cd "$TOOLKIT" && ADLC_TOOLKIT_ROOT="$TOOLKIT"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check 2>/dev/null); rc=$?
check "install_checkout_is_exempt: check with ADLC_TOOLKIT_ROOT naming the same install: rc" 2 "$rc"
# The exemption is that install only: the same checkout reached through a root that
# is not the symlink's target is still the tree's own copy, and stays refused.
out=$(HOME="$SANDBOX/emptyhome"; export HOME; ADLC_TOOLKIT_ROOT="$TOOLKIT"; export ADLC_TOOLKIT_ROOT; cd "$TOOLKIT" && adlc_regression_check mode 2>/dev/null); rc=$?
check "install_checkout_is_exempt: no symlink install, same tree: rc" 2 "$rc"
check "install_checkout_is_exempt: no symlink install, same tree: output" "regression-test: error
the engine is inside the tree under check" "$out"
out=$(ADLC_TOOLKIT_ROOT="$R2"; export ADLC_TOOLKIT_ROOT; cd "$TOOLKIT" && adlc_regression_check check --root "$R2" 2>/dev/null); rc=$?
check "install_checkout_is_exempt: a planted engine in another tree: rc" 2 "$rc"

# --- forge_from_cwd_never_sourced (LESSON-718) ----------------------------------
# The resolver picks the interpreter that runs the engine, so it comes from the
# installed toolkit only. A forge.sh in the current directory is never sourced:
# here one that defines a resolver naming a planted "python", and one from before
# the resolver existed. Each leaves a marker when sourced; neither may appear, and
# the installed engine answers. The current directory is the project, as in a fence.
R="$SANDBOX/cwdforge"; mkproj "$R" required
mkdir -p "$R/.adlc/partials" "$SANDBOX/planted"
printf '%s\n' '#!/bin/sh' 'echo "regression-test: off"; echo "PLANTED-PYTHON-RAN"' > "$SANDBOX/planted/python3"
chmod +x "$SANDBOX/planted/python3"
for variant in resolver stale; do
  rm -f "$SANDBOX/cwdforge-loaded"
  if [ "$variant" = resolver ]; then
    printf '%s\n' ": > '$SANDBOX/cwdforge-loaded'" "_adlc_forge_python() { printf '%s\\n' '$SANDBOX/planted/python3'; }" > "$R/.adlc/partials/forge.sh"
  else
    printf '%s\n' "# a forge.sh from before the interpreter resolver" ": > '$SANDBOX/cwdforge-loaded'" > "$R/.adlc/partials/forge.sh"
  fi
  ( unset -f _adlc_forge_python 2>/dev/null || unfunction _adlc_forge_python 2>/dev/null
    cd "$R" && . "$PARTIALS/regression-check.sh" && adlc_regression_check mode ) > "$SANDBOX/cwdforge.out" 2>/dev/null; rc=$?
  out=$(cat "$SANDBOX/cwdforge.out")
  check "forge_from_cwd_never_sourced: $variant: the copy in the current directory was not sourced" "no" "$([ -e "$SANDBOX/cwdforge-loaded" ] && echo yes || echo no)"
  check "forge_from_cwd_never_sourced: $variant: no planted interpreter ran" "0" "$(countf "$out" PLANTED-PYTHON-RAN)"
  check "forge_from_cwd_never_sourced: $variant: rc" 0 "$rc"
  check "forge_from_cwd_never_sourced: $variant: the installed engine ran" "regression-test: required
bugfix.regression_test is required in .adlc/config.yml" "$out"
done

# --- dotdot_root_goes_to_engine ---------------------------------------------------
# `cd -P` resolves `..` physically and the engine lexically, so a `..` root is
# never answered by the wrapper and is checked for containment the engine's way.
R="$SANDBOX/noconfig"; mkdir -p "$R/sub"
for root in "$R/sub/.." "$R/./sub/../"; do
  out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$root" 2>/dev/null); rc=$?
  check "dotdot_root_goes_to_engine: no config, '..' root, no engine: rc" 2 "$rc"
  check "dotdot_root_goes_to_engine: no config, '..' root, no engine: output" "regression-test: error
regression_check.py not found in the installed toolkit" "$out"
done
out=$(cd "$R/sub" && ADLC_TOOLKIT_ROOT="$SANDBOX/emptyroot"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root .. 2>/dev/null); rc=$?
check "dotdot_root_goes_to_engine: a relative '..' root, no engine: rc" 2 "$rc"
check "dotdot_root_goes_to_engine: a relative '..' root, no engine: verdict" "regression-check: error" "$(nth "$out" 1)"
# A root `proj/link/..` whose link leads out of proj: physically the link target's
# parent, to the engine proj itself, which holds a vendored engine stubbed to pass.
P="$SANDBOX/dotdotproj"; mkproj "$P" required
mkdir -p "$SANDBOX/dotdotout/inner" "$P/vt/tools/adlc"
ln -s "$SANDBOX/dotdotout/inner" "$P/link"
printf '%s\n' 'print("regression-check: pass")' 'print("passed=0 waived=0 legacy=0 failed=0")' > "$P/vt/tools/adlc/regression_check.py"
for root in "$P/link/.." "$P/link/../"; do
  out=$(ADLC_TOOLKIT_ROOT="$P/vt"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$root" 2>/dev/null); rc=$?
  check "dotdot_root_goes_to_engine: '$root' reaching an engine inside proj: rc" 2 "$rc"
  check "dotdot_root_goes_to_engine: '$root' reaching an engine inside proj: refused" "regression-check: error
the engine is inside the tree under check" "$out"
done
out=$(cd "$P/link" && ADLC_TOOLKIT_ROOT="$P/vt"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check --root "$P/link/.." 2>/dev/null); rc=$?
check "dotdot_root_goes_to_engine: from inside the link target: refused" "regression-check: error
the engine is inside the tree under check" "$out"
# Benign: a `..` root with a config reaches the installed engine, which reads it.
out=$(adlc_regression_check mode --root "$P/link/.."); rc=$?
check "dotdot_root_goes_to_engine: a '..' root with a config: rc" 0 "$rc"
check "dotdot_root_goes_to_engine: a '..' root with a config: the engine read it" "regression-test: required
bugfix.regression_test is required in .adlc/config.yml" "$out"

# --- root_inside_toolkit (benign path) --------------------------------------
# The toolkit's own layout: worktrees under <root>/.claude/worktrees/. The engine
# is at <root>/tools/adlc, outside the root, so it runs. <root>/tools is a symlink
# to this checkout's tools/, so the engine is the real one. The worktree has a
# config without the key, so the answer comes from the engine, not the wrapper.
TKH="$SANDBOX/tkhost"
mkdir -p "$TKH/.claude/worktrees" && ln -s "$TOOLKIT/tools" "$TKH/tools"
R="$TKH/.claude/worktrees/w"; mkproj "$R" absent
out=$(ADLC_TOOLKIT_ROOT="$TKH"; export ADLC_TOOLKIT_ROOT; adlc_regression_check mode --root "$R"); rc=$?
check "root_inside_toolkit: rc" 0 "$rc"
check "root_inside_toolkit: verdict" "regression-test: off" "$(nth "$out" 1)"
check "root_inside_toolkit: the engine's reason line" "1" "$(count "$(nth "$out" 2)" '^bugfix\.regression_test is not set')"
out=$(cd "$R" && ADLC_TOOLKIT_ROOT="$TKH"; export ADLC_TOOLKIT_ROOT; adlc_regression_check check); rc=$?
check "root_inside_toolkit: check from the root itself: verdict" "regression-check: off" "$(nth "$out" 1)"

# --- set_u_home_unset -------------------------------------------------------
# The partial's own source of forge.sh reads a bare $HOME in its fallback operand;
# with HOME and ADLC_TOOLKIT_ROOT unset a `set -u` caller must not abort on it.
# Native zsh sets HOME itself when it is unset, so zsh runs in sh emulation here.
SETU="$SANDBOX/setu.sh"
printf '%s\n' 'set -u' ". '$PARTIALS/regression-check.sh'" 'adlc_regression_check check --root "$1"; printf "rc=%s\n" "$?"' > "$SETU"
case "$SUT" in
  *zsh) setu_out=$(cd "$SANDBOX" && env -u HOME -u ADLC_TOOLKIT_ROOT "$SUT" --emulate sh "$SETU" "$R" 2>/dev/null) ;;
  *) setu_out=$(cd "$SANDBOX" && env -u HOME -u ADLC_TOOLKIT_ROOT "$SUT" "$SETU" "$R" 2>/dev/null) ;;
esac
check "set_u_home_unset: sourced and called without aborting" "rc=2" "$(printf '%s\n' "$setu_out" | tail -n 1)"
check "set_u_home_unset: the call is an error" "regression-check: error" "$(nth "$setu_out" 1)"

# --- summary ----------------------------------------------------------------
# Case-count floor: a harness that ran nothing must not read as a pass.
echo "regression-check.test.sh: $CASES cases executed"
if [ "$CASES" -lt 100 ]; then
  echo "regression-check.test.sh: FAIL — expected at least 100 cases, ran $CASES ($SUT)"
  exit 1
fi
if [ "$FAILS" -eq 0 ]; then
  echo "regression-check.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "regression-check.test.sh: $FAILS FAILURE(S) ($SUT)"
exit 1
