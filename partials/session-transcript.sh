#!/bin/sh
# partials/session-transcript.sh — find THIS conversation's Claude Code transcript
# by a mark it printed itself (BUG-253, LESSON-733).
#
# /wrapup Step 4 delegates the lesson draft from the transcript of the session that
# ran the work. REQ-423 found it by walking from the working tree up to $HOME, taking
# each ancestor's ~/.claude/projects/<encoded> directory and picking the first JSONL
# whose tail named the REQ id. Under /sprint that cannot work: a pipeline-runner is a
# subagent, and its transcript is
#   ~/.claude/projects/<orchestrator's encoded cwd>/<session>/subagents/agent-<id>.jsonl
# The runner's worktree is never an ancestor of the orchestrator's directory, so the
# walk never sees it — and the repo root's directory holds older sessions that name
# the REQ too (the one that wrote the spec, a sprint that deferred it), so the id
# anchor matched one of those (REQ-647, 2026-10-29). An id anchor proves a transcript
# mentions the work, not that it IS the run.
#
# Neither the directory nor the id can tell sibling transcripts apart: concurrent
# runners share one session id (a subagent's shell sees the parent's
# $CLAUDE_CODE_SESSION_ID and no agent id of its own), and the orchestrator's
# transcript names every REQ. What does identify the run is something only it wrote.
# So the caller prints a fresh random mark in one tool call; by the next call that
# output is a tool result in exactly one transcript, its own, wherever the harness
# keeps it. The command that is still running is NOT yet in the transcript (checked
# 2026-10-29), which is why marking and finding must be two separate tool calls.
#
# Source this partial, then call WITHIN THE SAME fenced block, after the fence's
# ToolkitRoot root line (conventions.md "Bash in skills"):
#   fence 1:  adlc_transcript_mark                 # prints the mark; nothing else
#   fence 2:  JSONL=$(adlc_transcript_find "<the mark fence 1 printed, as a literal>")
#
# Contract — adlc_transcript_mark:
#   stdout: one line, adlc-transcript-mark-<16 hex>, from /dev/urandom. return 0.
#   return 2 when /dev/urandom yields nothing (never a guessable fallback mark).
#
# Contract — adlc_transcript_find <mark>:
#   Searches every *.jsonl under ~/.claude/projects/ (depth <= 5, so subagents/ is
#   in reach) modified in the last 60 minutes for the mark as a fixed string.
#   return 0 -> exactly one transcript holds it; its path on stdout
#   return 1 -> none does, or more than one does (a forked copy): nothing on stdout.
#               The caller must NOT fall back to any other discovery — a transcript
#               of other work is worse than none (LESSON-483). Draft directly instead.
#   return 2 -> usage: the argument is not a well-formed mark
#   Exactly one stderr line on every return 0/1, saying what was chosen or refused.
#
# POSIX sh only: no bashisms, no GNU-only flags. grep runs under find -exec, so a
# shell function shadowing grep cannot change its exit status (LESSON-717).

adlc_transcript_mark() {
  _adlc_tm_hex=$(od -An -N8 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n')
  case "$_adlc_tm_hex" in
    ????????????????) ;;
    *) echo "session transcript: /dev/urandom unavailable — no mark printed" >&2; return 2 ;;
  esac
  printf 'adlc-transcript-mark-%s\n' "$_adlc_tm_hex"
}

adlc_transcript_find() {
  _adlc_tf_mark=${1-}
  case "$_adlc_tf_mark" in
    adlc-transcript-mark-*) ;;
    *) echo "usage: adlc_transcript_find adlc-transcript-mark-<16 hex>" >&2; return 2 ;;
  esac
  case "${_adlc_tf_mark#adlc-transcript-mark-}" in
    *[!0-9a-f]*|'') echo "usage: adlc_transcript_find adlc-transcript-mark-<16 hex>" >&2; return 2 ;;
    ????????????????) ;;
    *) echo "usage: adlc_transcript_find adlc-transcript-mark-<16 hex>" >&2; return 2 ;;
  esac

  if [ -z "${HOME:-}" ] || [ ! -d "${HOME%/}/.claude/projects" ]; then
    echo "session transcript: no ~/.claude/projects — REFUSING to delegate; draft from the conversation" >&2
    return 1
  fi

  # Trailing slash: follow ~/.claude/projects if it is itself a symlink. -type f
  # skips symlinked files. find exits non-zero when grep matches nothing in a batch;
  # the match list, not the status, is the answer.
  _adlc_tf_hits=$(find "${HOME%/}/.claude/projects/" -maxdepth 5 -type f -name '*.jsonl' -mmin -60 \
    -exec grep -lF -e "$_adlc_tf_mark" {} + 2>/dev/null)
  _adlc_tf_n=0
  if [ -n "$_adlc_tf_hits" ]; then
    _adlc_tf_n=$(printf '%s\n' "$_adlc_tf_hits" | wc -l | tr -d ' ')
  fi

  case "$_adlc_tf_n" in
    0)
      echo "session transcript: no transcript holds this run's mark — REFUSING to delegate; draft from the conversation" >&2
      return 1 ;;
    1)
      echo "session transcript: this run's own transcript is ${_adlc_tf_hits#"${HOME%/}"/.claude/projects/}" >&2
      printf '%s\n' "$_adlc_tf_hits"
      return 0 ;;
    *)
      echo "session transcript: $_adlc_tf_n transcripts hold this run's mark (a forked copy?) — REFUSING to delegate; draft from the conversation" >&2
      return 1 ;;
  esac
}
