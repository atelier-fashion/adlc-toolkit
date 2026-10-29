#!/bin/sh
# partials/tests/adlc-home.test.sh — REQ-654 BR-1, BR-2 (TASK-134).
#
# Proves partials/adlc-home.sh under the shell run.sh hands it ($ADLC_TEST_SHELL).
# Each case is a script run by $SUT in a scrubbed environment (env -i), with a
# sandbox HOME whose name holds a space, so the resolver's quoting is exercised.
#
#   default_home            — ADLC_HOME unset: <HOME>/.claude, source `default` (BR-1)
#   override_home           — ADLC_HOME=/abs: verbatim, source `env`
#   rejects_empty_and_relative — ADLC_HOME='' and ADLC_HOME=rel each return 1 with
#                             nothing on stdout and a stderr line naming ADLC_HOME;
#                             neither prints the default (BR-2)
#   machine_config          — <home>/adlc/config.yml by default; ADLC_CONFIG wins;
#                             a set ADLC_CONFIG is honoured even when ADLC_HOME is
#                             invalid (the home is never consulted then) (BR-2)
#   set_u_home_unset        — `set -u` with HOME and ADLC_HOME unset: the partial
#                             loads, adlc_home returns 1 naming HOME, and the
#                             script runs on (it never aborts the caller)
#
# Native zsh sets HOME from the password database when it is unset, so the
# set_u case runs zsh as `zsh --emulate sh`, the mode in which HOME can be unset.
#
#   ADLC_TEST_SHELL=dash sh partials/tests/adlc-home.test.sh
# or, for bash, zsh, /bin/sh and dash in turn:  sh partials/tests/run.sh
#
# Exits 0 iff every check passes and the executed-check count clears its floor.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}

FAILS=0
CHECKS=0
pass() { CHECKS=$((CHECKS + 1)); echo "PASS: $1"; }
fail() { CHECKS=$((CHECKS + 1)); echo "FAIL: $1"; FAILS=$((FAILS + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (expected '$2', got '$3')"; fi
}

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-home-test.XXXXXX") || { echo "adlc-home.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "adlc-home.test.sh: sandbox path invalid" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-home-test.*) ;;
  *) echo "adlc-home.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

H="$SANDBOX/home dir"
mkdir -p "$H"
OUT="$SANDBOX/out"
ERR="$SANDBOX/err"

# run_case <script-body> [VAR=value ...] — runs the body under $SUT with a scrubbed
# environment: PATH, HOME=<sandbox> and the given assignments only.
run_case() {
  rc_body=$1; shift
  printf '. "%s/adlc-home.sh"\n%s\n' "$PARTIALS" "$rc_body" > "$SANDBOX/case.sh"
  env -i PATH="$PATH" HOME="$H" "$@" "$SUT" "$SANDBOX/case.sh" > "$OUT" 2> "$ERR"
  RC=$?
}

# ---------------------------------------------------------------------------
run_case 'adlc_home; adlc_home_source'
check "default_home: prints <HOME>/.claude then default" "$H/.claude|default" "$(tr '\n' '|' < "$OUT" | sed 's/|$//')"
check "default_home: rc 0" 0 "$RC"
check "default_home: stderr empty" "" "$(cat "$ERR")"

run_case 'adlc_home; adlc_home_source' ADLC_HOME="$SANDBOX/alt home"
check "override_home: verbatim, source env" "$SANDBOX/alt home|env" "$(tr '\n' '|' < "$OUT" | sed 's/|$//')"
check "override_home: rc 0" 0 "$RC"

for bad in '' 'rel/path' './rel' '~/x'; do
  run_case 'adlc_home' ADLC_HOME="$bad"
  check "rejects_empty_and_relative: ADLC_HOME='$bad' rc 1" 1 "$RC"
  check "rejects_empty_and_relative: ADLC_HOME='$bad' prints nothing" "" "$(cat "$OUT")"
  if grep -q 'ADLC_HOME' "$ERR"; then pass "rejects_empty_and_relative: ADLC_HOME='$bad' stderr names ADLC_HOME"
  else fail "rejects_empty_and_relative: ADLC_HOME='$bad' stderr does not name ADLC_HOME: $(cat "$ERR")"; fi
done
run_case 'adlc_home_source' ADLC_HOME='rel'
check "rejects_empty_and_relative: adlc_home_source rc 1 on a relative home" 1 "$RC"

# ---------------------------------------------------------------------------
run_case 'adlc_machine_config'
check "machine_config: default <HOME>/.claude/adlc/config.yml" "$H/.claude/adlc/config.yml" "$(cat "$OUT")"
run_case 'adlc_machine_config' ADLC_HOME=/opt/adlc
check "machine_config: under an overridden home" "/opt/adlc/adlc/config.yml" "$(cat "$OUT")"
run_case 'adlc_machine_config' ADLC_CONFIG=/etc/adlc.yml ADLC_HOME=/opt/adlc
check "machine_config: ADLC_CONFIG outranks the home" "/etc/adlc.yml" "$(cat "$OUT")"
run_case 'adlc_machine_config' ADLC_CONFIG=/etc/adlc.yml ADLC_HOME=rel
check "machine_config: ADLC_CONFIG honoured with an invalid home" "/etc/adlc.yml|0" "$(cat "$OUT")|$RC"
run_case 'adlc_machine_config' ADLC_HOME=rel
check "machine_config: invalid home, no ADLC_CONFIG: rc 1" 1 "$RC"

# ---------------------------------------------------------------------------
# set -u with HOME and ADLC_HOME both unset: load, fail the call, keep running.
printf 'set -u\n. "%s/adlc-home.sh"\nif adlc_home; then echo resolved; else echo "rc=$?"; fi\necho after\n' "$PARTIALS" > "$SANDBOX/setu.sh"
# Two literal branches, never a word-split command string: zsh, which may be the
# shell running THIS harness, does not split an unquoted parameter (BUG-118).
case "$SUT" in
  *zsh) env -i PATH="$PATH" "$SUT" --emulate sh "$SANDBOX/setu.sh" > "$OUT" 2> "$ERR" ;;
  *)    env -i PATH="$PATH" "$SUT" "$SANDBOX/setu.sh" > "$OUT" 2> "$ERR" ;;
esac
check "set_u_home_unset: the call fails, the script runs on" "rc=1|after" "$(tr '\n' '|' < "$OUT" | sed 's/|$//')"
if grep -q 'HOME' "$ERR"; then pass "set_u_home_unset: stderr names HOME"; else fail "set_u_home_unset: stderr: $(cat "$ERR")"; fi

# ---------------------------------------------------------------------------
FLOOR=24
if [ "$CHECKS" -lt "$FLOOR" ]; then
  echo "FAIL: only $CHECKS checks ran (floor $FLOOR) — a case was skipped"
  FAILS=$((FAILS + 1))
fi
echo "adlc-home.test.sh [$SUT]: $CHECKS checks, $FAILS failure(s)"
[ "$FAILS" -eq 0 ]
