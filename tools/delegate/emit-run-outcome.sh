#!/bin/sh
# emit-run-outcome.sh — append one RunOutcome line to the run-outcome log (REQ-648).
#
#   emit-run-outcome.sh --state <abs> --terminal <t> --engine <e> [--reason <r>] [--req <REQ-xxx>]
#       runs `run_outcome.py emit` and appends its one JSON line to
#       ${ADLC_RUN_OUTCOMES_LOG:-$HOME/Library/Logs/adlc-run-outcomes.log}
#   emit-run-outcome.sh record-harness|record-validate|record-verify|record-lessons-written <args>
#       passes straight through to the same run_outcome.py subcommand (a state
#       write; its one stdout line is relayed)
#
# The record is built by run_outcome.py from the state file, never by the caller
# (BR-1). This wrapper only resolves the module, runs it, and appends.
#
# It ALWAYS exits 0 (BR-3): telemetry never blocks a pipeline. Every failure is
# one `run-outcome: <reason>` line on stderr. That is also why there is no
# `set -e` here.
#
# A separate file from the delegation log, so check-delegation.sh's 9-key parser
# is untouched. First write creates the log with mode 0600 (umask 077).
#
# EXECUTE it, never source it: the umask below would persist in the caller's
# shell (the emit-telemetry.sh rule). POSIX sh: no local, no [[, no mktemp -t.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)
MODULE="$HERE/run_outcome.py"
LOG=${ADLC_RUN_OUTCOMES_LOG:-"$HOME/Library/Logs/adlc-run-outcomes.log"}

if [ -z "$HERE" ] || [ ! -f "$MODULE" ]; then
  echo "run-outcome: run_outcome.py not found beside emit-run-outcome.sh — nothing recorded" >&2
  exit 0
fi
PY=$(command -v python3 2>/dev/null)
if [ -z "$PY" ]; then
  echo "run-outcome: python3 not on PATH — nothing recorded" >&2
  exit 0
fi

case "${1-}" in
  record-harness|record-validate|record-verify|record-lessons-written)
    "$PY" "$MODULE" "$@" || echo "run-outcome: $1 failed (rc $?) — state not updated" >&2
    exit 0
    ;;
  emit) shift ;;
esac

line=$("$PY" "$MODULE" emit "$@")
rc=$?
if [ "$rc" -ne 0 ] || [ -z "$line" ]; then
  echo "run-outcome: emit failed (rc $rc) — nothing recorded" >&2
  exit 0
fi

umask 077
log_dir=$(dirname -- "$LOG")
if [ ! -d "$log_dir" ] && ! mkdir -p -- "$log_dir" 2>/dev/null; then
  echo "run-outcome: cannot create $log_dir — nothing recorded" >&2
  exit 0
fi
if [ ! -e "$LOG" ]; then
  if ! : >"$LOG" 2>/dev/null; then
    echo "run-outcome: cannot create $LOG — nothing recorded" >&2
    exit 0
  fi
  chmod 600 "$LOG" 2>/dev/null || :
fi
if ! printf '%s\n' "$line" >>"$LOG" 2>/dev/null; then
  echo "run-outcome: cannot append to $LOG — nothing recorded" >&2
  exit 0
fi
exit 0
