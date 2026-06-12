#!/bin/sh
# partials/tests/run.sh — run id-alloc.test.sh under BOTH bash and zsh (REQ-518 BR-6,
# Linux-parity AC). Exits non-zero if either shell reports a failure. zsh is skipped
# with a notice (not a failure) if it is not installed, so CI on a bash-only box still
# runs the bash pass.
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TEST="$HERE/id-alloc.test.sh"
RC=0

if command -v bash >/dev/null 2>&1; then
  echo "=== bash ==="
  bash "$TEST" || RC=1
else
  echo "=== bash: not installed — skipping ==="
fi

if command -v zsh >/dev/null 2>&1; then
  echo "=== zsh ==="
  zsh "$TEST" || RC=1
else
  echo "=== zsh: not installed — skipping (bash pass still authoritative) ==="
fi

exit $RC
