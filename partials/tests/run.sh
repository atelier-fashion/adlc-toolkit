#!/bin/sh
# partials/tests/run.sh — run the partial test harnesses under bash, zsh AND
# /bin/sh (REQ-518 BR-6 / REQ-520 BR-9, Linux-parity AC; REQ-609 BR-16/AC-14).
# Exits non-zero if any shell reports a failure on any harness. A shell that is
# not installed is skipped with a notice (not a failure), so CI on a bash-only
# box still runs the bash pass.
#
# sh joined the loop with REQ-609: the delegate gate's resolver is pure POSIX
# parameter expansion precisely so it behaves the same in all three, and a claim
# like that is worth only as much as the shell it was executed under. Each
# harness is told which shell is driving it ($ADLC_TEST_SHELL) so a harness that
# spawns inner shells can spawn THIS one rather than always /bin/sh.
#
# The harness list lives in the positional parameters, never in a space-joined
# string: `for t in $TESTS` depends on sh/bash word-splitting, which zsh does not
# perform, so under `zsh run.sh` (the macOS Claude executor shell) the whole list
# collapsed into one bogus filename (BUG-118; masked while the list had a single
# element — LESSON-399). The outer pass re-execs THIS script under each shell, so
# run.sh's own iteration is exercised under zsh on every run, not just the
# harnesses it dispatches.
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RC=0

run_all() { # run_all <shell> <harness>... — element-wise, no word-splitting (BUG-118)
  shell=$1; shift
  for t in "$@"; do
    echo "--- $shell: $(basename "$t") ---"
    ADLC_TEST_SHELL="$shell" "$shell" "$t" || RC=1
  done
}

if [ "${1-}" = "--inner" ]; then
  # Inner pass: run.sh re-run under a specific shell ($2) — runs every harness
  # with that shell, and in doing so exercises this script's own list handling
  # under that shell.
  run_all "$2" "$HERE/id-alloc.test.sh" "$HERE/forge.test.sh" "$HERE/attribution.test.sh" "$HERE/intake.test.sh" "$HERE/delegate-gate.test.sh" "$HERE/source-guard.test.sh"
  exit $RC
fi

for shell in bash zsh /bin/sh dash; do
  if command -v "$shell" >/dev/null 2>&1; then
    echo "=== $shell ==="
    "$shell" "$0" --inner "$shell" || RC=1
  else
    echo "=== $shell: not installed — skipping (bash pass still authoritative) ==="
  fi
done

exit $RC
