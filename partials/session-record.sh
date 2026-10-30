#!/bin/sh
# partials/session-record.sh — STUB of the `session-record` hook command (REQ-657 BR-10).
#
# REQ-660 ships the real partial under this same name and owns the session
# sidecar's contract: its fields, line format, mode, write conditions, pruning, the
# gitignore line and its lint. Until then this stub records what REQ-657 BR-10
# names and nothing more: `harness=` and `session_id=`, in `.adlc/.session/<id>`.
#
# adlc_session_record [--harness <name>] [--field session_id=<payload key>]...
#   Reads the hook payload (JSON) on stdin. Writes only when ./.adlc/ already
#   exists, only under ./.adlc/.session/, mode 600, and only for a session id made
#   of [A-Za-z0-9_-]. Prints nothing (a session-start hook's stdout becomes model
#   context) and returns 0 on every path, so it never fails a session.
#   Without --harness (the shared `claude` render, which Copilot CLI and Cursor
#   read as-is) the harness comes from a detection table over the payload.
#   The directory carries a `.gitignore` of `*`, so no `git status` changes
#   before REQ-660 adds its gitignore line.
#
# POSIX sh, bash, zsh and dash (partials/tests/hooks.test.sh): no `local`, no
# `[[`, no `case` inside `$( )`, and no `shift` past the last argument (a POSIX
# special built-in error would exit the shell).
adlc_session_record() {
  adlc_sr_harness=""
  adlc_sr_key="session_id"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --harness)
        if [ "$#" -ge 2 ]; then adlc_sr_harness=$2; shift 2; else shift; fi ;;
      --field)
        if [ "$#" -ge 2 ]; then
          case "$2" in session_id=*) adlc_sr_key=${2#session_id=} ;; esac
          shift 2
        else
          shift
        fi ;;
      *) shift ;;
    esac
  done
  case "$adlc_sr_key" in ''|*[!A-Za-z0-9_]*) adlc_sr_key="session_id" ;; esac
  [ -d .adlc ] || return 0
  [ -L .adlc ] && return 0
  if [ -t 0 ]; then
    adlc_sr_payload=""
  else
    adlc_sr_payload=$(cat 2>/dev/null) || adlc_sr_payload=""
  fi
  adlc_sr_id=$(printf '%s' "$adlc_sr_payload" | tr -d '\n\r' | sed -n "s/.*\"$adlc_sr_key\"[[:space:]]*:[[:space:]]*\"\\([A-Za-z0-9_-][A-Za-z0-9_-]*\\)\".*/\\1/p")
  [ -n "$adlc_sr_id" ] || return 0
  if [ -z "$adlc_sr_harness" ]; then
    # The detection table: what each reader of the shared render puts in its payload.
    case "$adlc_sr_payload" in
      *'/.claude/projects/'*) adlc_sr_harness=claude ;;
      *) adlc_sr_harness=unknown ;;
    esac
  fi
  case "$adlc_sr_harness" in ''|*[!A-Za-z0-9_-]*) adlc_sr_harness=unknown ;; esac
  [ -L .adlc/.session ] && return 0
  mkdir -p .adlc/.session 2>/dev/null || return 0
  [ -f .adlc/.session/.gitignore ] || printf '*\n' > .adlc/.session/.gitignore 2>/dev/null
  (
    umask 077
    printf 'harness=%s\nsession_id=%s\n' "$adlc_sr_harness" "$adlc_sr_id" \
      > ".adlc/.session/$adlc_sr_id.tmp" 2>/dev/null \
      && mv -f ".adlc/.session/$adlc_sr_id.tmp" ".adlc/.session/$adlc_sr_id" 2>/dev/null
  ) || true
  return 0
}
