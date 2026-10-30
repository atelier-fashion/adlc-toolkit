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
# adlc_ethos_inject [--harness <name>] [--context-key <key>]
#   With --context-key the output is one JSON object, {"<key>":"<the file>"}, for a
#   harness that takes context only as JSON and ignores plain stdout (Copilot CLI's
#   additionalContext, REQ-656 ADR-5). Backslash, quote and tab are escaped, lines
#   join with \n, and every other control byte is dropped, so the object always
#   parses. Any other argument is ignored: a hook never fails on its own argv.
#
# POSIX sh, bash, zsh and dash (partials/tests/hooks.test.sh): no `local`, no `[[`,
# no `case` inside `$( )`, and no `shift` past the last argument (a POSIX special
# built-in error would exit the shell).
adlc_ethos_inject() {
  adlc_ei_key=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --context-key)
        if [ "$#" -ge 2 ]; then adlc_ei_key=$2; shift 2; else shift; fi ;;
      *) shift ;;
    esac
  done
  [ -s .adlc/ETHOS.md ] || return 0
  if [ -z "$adlc_ei_key" ]; then
    cat .adlc/ETHOS.md 2>/dev/null
    return 0
  fi
  case "$adlc_ei_key" in *[!A-Za-z0-9_]*) return 0 ;; esac
  adlc_ei_tab=$(printf '\t')
  printf '{"%s":"' "$adlc_ei_key"
  LC_ALL=C tr -d '\000-\010\013-\037\177' < .adlc/ETHOS.md 2>/dev/null |
    sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e "s/$adlc_ei_tab/\\\\t/g" |
    while IFS= read -r adlc_ei_line || [ -n "$adlc_ei_line" ]; do
      printf '%s\\n' "$adlc_ei_line"
    done
  printf '"}\n'
  return 0
}
