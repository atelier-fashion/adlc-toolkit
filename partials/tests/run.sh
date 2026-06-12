#!/bin/sh
# partials/tests/run.sh — run the partial test harnesses under BOTH bash and zsh
# (REQ-518 BR-6 / REQ-520 BR-9, Linux-parity AC). Exits non-zero if either shell
# reports a failure on any harness. zsh is skipped with a notice (not a failure) if
# it is not installed, so CI on a bash-only box still runs the bash pass.
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TESTS="$HERE/id-alloc.test.sh $HERE/forge.test.sh"
RC=0

run_all() { # run_all <shell>
  for t in $TESTS; do
    echo "--- $1: $(basename "$t") ---"
    "$1" "$t" || RC=1
  done
}

if command -v bash >/dev/null 2>&1; then
  echo "=== bash ==="
  run_all bash
else
  echo "=== bash: not installed — skipping ==="
fi

if command -v zsh >/dev/null 2>&1; then
  echo "=== zsh ==="
  run_all zsh
else
  echo "=== zsh: not installed — skipping (bash pass still authoritative) ==="
fi

exit $RC
