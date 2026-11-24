#!/bin/sh
# Tests for greet.sh. Run from any directory: sh tests/greet.test.sh
root="$(dirname "$0")/.."
failed=0

# check DESCRIPTION EXPECTED [ARGUMENTS...]: run greet.sh with ARGUMENTS and
# compare what it prints with EXPECTED.
check() {
  description=$1
  expected=$2
  shift 2
  actual=$(sh "$root/greet.sh" "$@")
  if [ "$actual" = "$expected" ]; then
    printf 'ok - %s\n' "$description"
  else
    printf 'not ok - %s: expected "%s", got "%s"\n' "$description" "$expected" "$actual"
    failed=1
  fi
}

check "no arguments prints Hello, world" "Hello, world"

exit "$failed"
