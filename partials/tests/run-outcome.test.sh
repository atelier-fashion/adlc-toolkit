#!/bin/sh
# partials/tests/run-outcome.test.sh — REQ-648 BR-3/BR-11: the run-outcome wrapper, end to end.
#
# tools/delegate/tests/test_run_outcome.py covers every derivation rule of
# run_outcome.py. This harness proves the shell half under bash, zsh, /bin/sh and
# dash: that tools/delegate/emit-run-outcome.sh appends the emitted line with
# umask 077, passes record-* through, and turns every way it cannot record into
# exit 0 plus one `run-outcome:` stderr line (telemetry never blocks a pipeline).
#
#   first_write        — creates the log 0600 holding one RunOutcome line
#   append             — a second emit appends a second line
#   explicit_emit      — the `emit` subcommand spelling behaves the same
#   bad_state          — a missing state file: rc 0, one stderr line, log unchanged
#   bad_terminal       — an out-of-vocabulary terminal: rc 0, one stderr line
#   record_passthrough — record-validate writes validateAttempts and relays its line
#   record_carry       — record-carry fills only the keys the primary copy lacks
#   record_failure     — a record on a missing state: rc 0, one stderr line
#   no_python          — python3 not on PATH: rc 0, one stderr line, no log
#   module_missing     — the wrapper copied away from run_outcome.py: rc 0, one line
#   unwritable_dir     — the log directory cannot be created: rc 0, one line
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL).

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TOOLKIT=$(CDPATH= cd -- "$HERE/../.." && pwd)
WRAP="$TOOLKIT/tools/delegate/emit-run-outcome.sh"
SUT=${ADLC_TEST_SHELL:-/bin/sh}

FAILS=0
CASES=0
pass() { echo "PASS: $1"; CASES=$((CASES + 1)); }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-run-outcome.XXXXXX") || { echo "run-outcome.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "run-outcome.test.sh: sandbox path invalid" >&2; exit 1; }
trap 'chmod -R u+w "$SANDBOX" 2>/dev/null; rm -rf "$SANDBOX"' EXIT INT TERM

STATE="$SANDBOX/pipeline-state.json"
printf '%s\n' '{"req":"REQ-648","startedAt":"2026-10-29T11:00:00Z",' \
  '"repos":{"adlc-toolkit":{"primary":true,"path":"/x/adlc-toolkit"}},' \
  '"harness":{"version":"5.4.0","sha":"c013262"}}' > "$STATE"
LOG="$SANDBOX/logs/run-outcomes.log"

lines() { if [ -f "$1" ]; then wc -l < "$1" | tr -d ' '; else echo 0; fi; }

# --- first_write --------------------------------------------------------------
err=$(ADLC_RUN_OUTCOMES_LOG="$LOG" "$SUT" "$WRAP" --state "$STATE" --terminal merged --engine solo 2>&1 >/dev/null); rc=$?
check "first_write: rc" 0 "$rc"
check "first_write: no stderr" "" "$err"
check "first_write: one line" 1 "$(lines "$LOG")"
check "first_write: mode 0600" "-rw-------" "$(ls -l "$LOG" | cut -c1-10)"
check "first_write: a RunOutcome line" 1 "$(command grep -c '^{"timestamp":"[^"]*","skill":"proceed","step":"run-outcome","req":"REQ-648"' "$LOG")"
check "first_write: terminal and sha" 1 "$(command grep -c '"toolkit_sha":"c013262","terminal":"merged"' "$LOG")"

# --- append -------------------------------------------------------------------
ADLC_RUN_OUTCOMES_LOG="$LOG" "$SUT" "$WRAP" --state "$STATE" --terminal blocked --engine solo --reason validation-exhausted 2>/dev/null; rc=$?
check "append: rc" 0 "$rc"
check "append: two lines" 2 "$(lines "$LOG")"
check "append: reason normalised" 1 "$(command grep -c '"blocked_reason":"validation-exhausted"' "$LOG")"

# --- explicit_emit ------------------------------------------------------------
ADLC_RUN_OUTCOMES_LOG="$LOG" "$SUT" "$WRAP" emit --state "$STATE" --terminal pr-ready --engine legacy 2>/dev/null; rc=$?
check "explicit_emit: rc" 0 "$rc"
check "explicit_emit: three lines" 3 "$(lines "$LOG")"

# --- bad_state ----------------------------------------------------------------
err=$(ADLC_RUN_OUTCOMES_LOG="$LOG" "$SUT" "$WRAP" --state "$SANDBOX/absent.json" --terminal merged --engine solo 2>&1 >/dev/null); rc=$?
check "bad_state: rc 0 (never blocks)" 0 "$rc"
check "bad_state: run-outcome lines on stderr" 1 "$(printf '%s\n' "$err" | command grep -c '^run-outcome: emit failed')"
check "bad_state: log unchanged" 3 "$(lines "$LOG")"

# --- bad_terminal -------------------------------------------------------------
err=$(ADLC_RUN_OUTCOMES_LOG="$LOG" "$SUT" "$WRAP" --state "$STATE" --terminal done --engine solo 2>&1 >/dev/null); rc=$?
check "bad_terminal: rc 0" 0 "$rc"
check "bad_terminal: emit failed line" 1 "$(printf '%s\n' "$err" | command grep -c '^run-outcome: emit failed (rc 2)')"
check "bad_terminal: log unchanged" 3 "$(lines "$LOG")"

# --- record_passthrough -------------------------------------------------------
out=$("$SUT" "$WRAP" record-validate --state "$STATE" --phase 1 --attempt 2 2>/dev/null); rc=$?
check "record_passthrough: rc" 0 "$rc"
check "record_passthrough: relayed line" "validateAttempts: phase1=2 phase3=0" "$out"
check "record_passthrough: key written" 1 "$(command grep -c '"phase1": 2' "$STATE")"
check "record_passthrough: harness kept" 1 "$(command grep -c '"sha": "c013262"' "$STATE")"

# --- record_carry -------------------------------------------------------------
WSTATE="$SANDBOX/worktree-state.json"
printf '%s\n' '{"req":"REQ-648","phaseHistory":[{"phase":0}],"harness":{"version":"0.0.1","sha":"0000000"}}' > "$WSTATE"
out=$("$SUT" "$WRAP" record-carry --state "$STATE" --from "$WSTATE" 2>/dev/null); rc=$?
check "record_carry: rc" 0 "$rc"
check "record_carry: relayed line" "carried: phaseHistory" "$out"
check "record_carry: the primary copy's harness wins" 1 "$(command grep -c '"sha": "c013262"' "$STATE")"

# --- record_failure -----------------------------------------------------------
err=$("$SUT" "$WRAP" record-verify --state "$SANDBOX/absent.json" --findings - < /dev/null 2>&1 >/dev/null); rc=$?
check "record_failure: rc 0" 0 "$rc"
check "record_failure: failed line" 1 "$(printf '%s\n' "$err" | command grep -c '^run-outcome: record-verify failed')"

# --- no_python ----------------------------------------------------------------
mkdir -p "$SANDBOX/bin"
for t in dirname; do
  p=$(command -v "$t") && ln -s "$p" "$SANDBOX/bin/$t"
done
NP_LOG="$SANDBOX/np/log"
SUT_ABS=$(command -v "$SUT")   # the restricted PATH below cannot find a bare shell name
err=$(PATH="$SANDBOX/bin" ADLC_RUN_OUTCOMES_LOG="$NP_LOG" "$SUT_ABS" "$WRAP" --state "$STATE" --terminal merged --engine solo 2>&1 >/dev/null); rc=$?
check "no_python: rc 0" 0 "$rc"
check "no_python: one line" "run-outcome: python3 not on PATH — nothing recorded" "$err"
check "no_python: no log" 0 "$(lines "$NP_LOG")"

# --- module_missing -----------------------------------------------------------
mkdir -p "$SANDBOX/lonely"
cp "$WRAP" "$SANDBOX/lonely/emit-run-outcome.sh"
err=$(ADLC_RUN_OUTCOMES_LOG="$LOG" "$SUT" "$SANDBOX/lonely/emit-run-outcome.sh" --state "$STATE" --terminal merged --engine solo 2>&1 >/dev/null); rc=$?
check "module_missing: rc 0" 0 "$rc"
check "module_missing: one line" 1 "$(printf '%s\n' "$err" | command grep -c '^run-outcome: run_outcome.py not found')"

# --- unwritable_dir -----------------------------------------------------------
mkdir -p "$SANDBOX/ro" && chmod 500 "$SANDBOX/ro"
if [ -w "$SANDBOX/ro" ]; then
  pass "unwritable_dir: skipped (running with write access to a 0500 directory)"
  pass "unwritable_dir: skipped"
else
  err=$(ADLC_RUN_OUTCOMES_LOG="$SANDBOX/ro/sub/log" "$SUT" "$WRAP" --state "$STATE" --terminal merged --engine solo 2>&1 >/dev/null); rc=$?
  check "unwritable_dir: rc 0" 0 "$rc"
  check "unwritable_dir: one line" 1 "$(printf '%s\n' "$err" | command grep -c '^run-outcome: cannot create')"
fi

# --- summary ------------------------------------------------------------------
# Case-count floor: a harness that ran nothing must not read as a pass.
echo "run-outcome.test.sh: $CASES cases executed"
if [ "$CASES" -lt 25 ]; then
  echo "run-outcome.test.sh: FAIL — expected at least 25 cases, ran $CASES ($SUT)"
  exit 1
fi
if [ "$FAILS" -eq 0 ]; then
  echo "run-outcome.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "run-outcome.test.sh: $FAILS FAILURE(S) ($SUT)"
exit 1
