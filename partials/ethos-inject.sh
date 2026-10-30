#!/bin/sh
# partials/ethos-inject.sh — the `ethos-inject` hook command's function (REQ-657 BR-10).
#
# Sourced by the hook command templates/hooks.yml renders into each harness's hook
# file, through the canonical two-level guarded spelling. adlc_ethos_inject prints
# the project's vendored .adlc/ETHOS.md, which a session-start hook's stdout turns
# into session context, and prints nothing at all when the project has none or the
# copy is empty: a hook never invents a constitution and never fails a session.
# The project copy only, as the skills' `!` ETHOS line reads it (BUG-218).
#
# POSIX sh, bash, zsh and dash (partials/tests/hooks.test.sh).
adlc_ethos_inject() {
  if [ -s .adlc/ETHOS.md ]; then
    cat .adlc/ETHOS.md 2>/dev/null
  fi
  return 0
}
