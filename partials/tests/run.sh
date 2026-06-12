#!/bin/sh
# partials/tests/run.sh — run the partial test harnesses under BOTH bash and zsh
# (REQ-518 BR-6 / REQ-520 BR-9, Linux-parity AC). Exits non-zero if either shell
# reports a failure on any harness. zsh is skipped with a notice (not a failure) if
# it is not installed, so CI on a bash-only box still runs the bash pass.
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
    "$shell" "$t" || RC=1
  done
}

if [ "${1-}" = "--inner" ]; then
  # Inner pass: run.sh re-run under a specific shell ($2) — runs every harness
  # with that shell, and in doing so exercises this script's own list handling
  # under that shell.
  run_all "$2" "$HERE/id-alloc.test.sh" "$HERE/forge.test.sh"
  exit $RC
fi

for shell in bash zsh; do
  if command -v "$shell" >/dev/null 2>&1; then
    echo "=== $shell ==="
    "$shell" "$0" --inner "$shell" || RC=1
  else
    echo "=== $shell: not installed — skipping (bash pass still authoritative) ==="
  fi
done

exit $RC
