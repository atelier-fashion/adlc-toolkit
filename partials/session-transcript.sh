#!/bin/sh
# partials/session-transcript.sh — find THIS conversation's transcript by a mark it
# printed itself (BUG-253, LESSON-733), on any harness (REQ-660).
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
# REQ-660 makes that mark the one acceptance check on every rung (ADR-1). A sidecar
# or a harness root only nominates a file. A sidecar (partials/session-record.sh) is
# a file in the working tree, so a hostile repo can commit one naming anything under
# $HOME, but that file cannot hold a value generated a moment ago and is never
# delegated. There is deliberately no REQ-id check and no cwd or hash locator.
#
# Source this partial, then call WITHIN THE SAME fenced block, after the fence's
# ToolkitRoot root line (conventions.md "Bash in skills"):
#   fence 1:  adlc_transcript_mark                 # prints the mark; nothing else
#   fence 2:  JSONL=$(adlc_transcript_find "<the mark fence 1 printed, as a literal>")
#             FORMAT=$(adlc_transcript_format "$JSONL" 2>/dev/null) || FORMAT=""
#
# Contract — adlc_transcript_mark:
#   stdout: one line, adlc-transcript-mark-<16 hex>, from /dev/urandom. return 0.
#   return 2 when /dev/urandom yields nothing (never a guessable fallback mark).
#
# Contract — adlc_transcript_find <mark>:
#   Rung (a): the transcript_path of every sidecar in .adlc/.session/ of this working
#   tree (git toplevel, else $PWD). A sidecar counts only with a harness in the
#   five-value enum and a path that is under $HOME, carries no `..` segment, exists,
#   is not a symlink, and sits in a directory that resolves under $HOME. Two sidecars
#   naming one path are one candidate. Any other sidecar contributes nothing.
#   Rung (b), only when no sidecar's file holds the mark: the four harness roots
#   (_adlc_tf_each_root), recent files only, in bounds of depth and name.
#   return 0 -> exactly one transcript holds it; its path on stdout
#   return 1 -> none does, or more than one does on a rung (a forked copy): nothing on
#               stdout. The caller must NOT fall back to any other discovery — a
#               transcript of other work is worse than none (LESSON-483). Draft
#               directly instead.
#   return 2 -> usage: the argument is not a well-formed mark
#   Exactly one stderr line on every return 0/1, prefixed `/wrapup: session JSONL —`
#   and naming the source. It carries a basename at most, never a rejected path.
#
# Contract — adlc_transcript_format <path>:
#   stdout: the `extract-chat --format` value for <path>: the harness of a usable
#   sidecar naming exactly that path, else the harness whose root it is under. return 0.
#   return 1 -> neither answers: nothing on stdout. Silent on stderr: its caller reads
#   it with 2>/dev/null, so a stale vendored copy without it stays quiet too (ADR-2).
#
# POSIX sh only: no bashisms, no GNU-only flags. `command` and find -exec keep a shell
# function shadowing a coreutil from changing what is read or a status (LESSON-717).

adlc_transcript_mark() {
  _adlc_tm_hex=$(od -An -N8 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n')
  case "$_adlc_tm_hex" in
    ????????????????) ;;
    *) echo "session transcript: /dev/urandom unavailable — no mark printed" >&2; return 2 ;;
  esac
  printf 'adlc-transcript-mark-%s\n' "$_adlc_tm_hex"
}

# _adlc_tf_each_root <fn>: the HarnessRoot table. Calls <fn> <harness> <root/> <depth>
# <name> once per root. A root is that harness's own data directory, not toolkit
# machine state, so it is spelled from HOME and does not move with ADLC_HOME (REQ-654
# ADR-1). Callers check that HOME is set first, so a `set -u` caller with HOME unset
# never expands it. Cursor has no root (OQ-3). The trailing slash follows a root that
# is itself a symlink, as a harness home moved to another volume is (BUG-253): the
# walk may then read outside HOME, and returns a file only if it holds the mark.
_ADLC_TF_WINDOW_MIN=60
# A hostile repo can commit sidecars, so how many are read is bounded (BR-16).
_ADLC_TF_MAX_SIDECARS=64

_adlc_tf_each_root() {
  "${1}" claude "${HOME%/}/.claude/projects/" 5 '*.jsonl'  # adlc-home: claude-code
  "${1}" codex "${HOME%/}/.codex/sessions/" 4 'rollout-*.jsonl'
  "${1}" copilot "${HOME%/}/.copilot/session-state/" 2 'events.jsonl'
  "${1}" gemini "${HOME%/}/.gemini/tmp/" 3 'session-*.jsonl'
}

# _adlc_tf_recent <root/> <depth> <name> [find primary...]: a root's candidates.
# -type f skips symlinked files.
_adlc_tf_recent() {
  _adlc_tfr_root=${1}
  _adlc_tfr_depth=${2}
  _adlc_tfr_name=${3}
  shift 3
  command find "$_adlc_tfr_root" -maxdepth "$_adlc_tfr_depth" -type f \
    -name "$_adlc_tfr_name" -mmin "-$_ADLC_TF_WINDOW_MIN" "$@" 2>/dev/null
}

# Rung (b), one root. find exits non-zero when grep matches nothing in a batch; the
# match list, not the status, is the answer. _adlc_tf_path is only read when the
# count across the roots is 1, and then this is that one line.
_adlc_tf_walk_root() {
  [ -d "${2}" ] || return 0
  _adlc_tfw_hits=$(_adlc_tf_recent "${2}" "${3}" "${4}" \
    -exec grep -lF -e "$_adlc_tf_mark" {} +) || :
  [ -n "$_adlc_tfw_hits" ] || return 0
  _adlc_tfw_n=$(printf '%s\n' "$_adlc_tfw_hits" | wc -l | tr -d ' ')
  _adlc_tf_held=$((_adlc_tf_held + _adlc_tfw_n))
  _adlc_tf_path=$_adlc_tfw_hits
  _adlc_tf_via=walk:${1}
}

# Counted only on the way to a refusal, so the line can tell "nothing to look at"
# from "looked and none held it". Reads no file.
_adlc_tf_count_root() {
  [ -d "${2}" ] || return 0
  _adlc_tfc_n=$(_adlc_tf_recent "${2}" "${3}" "${4}" | wc -l | tr -d ' ')
  _adlc_tf_roots=$((_adlc_tf_roots + _adlc_tfc_n))
}

_adlc_tf_format_root() {
  case "$_adlc_tfm_path" in
    "${2}"*) _adlc_tfm_name=${1} ;;
  esac
}

# _adlc_tf_usable <path> <resolved home>: whether a sidecar's path may be opened at all.
_adlc_tf_usable() {
  case "${1}" in
    "${HOME%/}/"*) ;;
    *) return 1 ;;
  esac
  case "${1}" in
    */../*|*/..) return 1 ;;
  esac
  [ -f "${1}" ] && [ ! -L "${1}" ] || return 1
  _adlc_tfu_dir=$(CDPATH= cd -P -- "${1%/*}/" 2>/dev/null && pwd -P) || return 1
  case "$_adlc_tfu_dir/" in
    "${2%/}/"*) return 0 ;;
  esac
  return 1
}

# _adlc_tf_sidecars: one `<harness> <path>` line for each usable path in this working
# tree's sidecars, each path once, ordered by path. Nothing when HOME is unset.
# No trailing slash on the directory, so a symlinked .session yields nothing. -type f
# skips a symlinked sidecar, and the dotfile test skips the .gitignore and the
# writer's temporary files. find, never a bare glob: zsh aborts on a pattern that
# matches nothing (LESSON-335).
_adlc_tf_sidecars() {
  [ -n "${HOME:-}" ] || return 0
  _adlc_tfs_home=$(CDPATH= cd -P -- "$HOME" 2>/dev/null && pwd -P) || return 0
  _adlc_tfs_top=$(command git rev-parse --show-toplevel 2>/dev/null) || _adlc_tfs_top=""
  [ -n "$_adlc_tfs_top" ] || _adlc_tfs_top=${PWD:-.}
  _adlc_tfs_list=$(command find "$_adlc_tfs_top/.adlc/.session" -maxdepth 1 -type f \
    ! -name '.*' 2>/dev/null | command head -n "$_ADLC_TF_MAX_SIDECARS")
  while IFS= read -r _adlc_tfs_f; do
    [ -n "$_adlc_tfs_f" ] || continue
    _adlc_tfs_h=$(command sed -n 's/^harness=//p' "$_adlc_tfs_f" 2>/dev/null | command head -n 1)
    case "$_adlc_tfs_h" in
      claude|copilot|codex|gemini|cursor|antigravity) ;;
      *) continue ;;
    esac
    _adlc_tfs_p=$(command sed -n 's/^transcript_path=//p' "$_adlc_tfs_f" 2>/dev/null | command head -n 1)
    if _adlc_tf_usable "$_adlc_tfs_p" "$_adlc_tfs_home"; then
      printf '%s %s\n' "$_adlc_tfs_h" "$_adlc_tfs_p"
    fi
  done <<EOF | LC_ALL=C command sort -u -t ' ' -k 2
$_adlc_tfs_list
EOF
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

  _adlc_tf_held=0
  _adlc_tf_path=""
  _adlc_tf_via=sidecar
  _adlc_tf_cands=0

  # Rung (a). A here-doc, so the counts survive the loop. `command grep`: this branch
  # decides what gets delegated, so a shadowing function must not answer it (LESSON-717).
  _adlc_tf_list=$(_adlc_tf_sidecars)
  while IFS= read -r _adlc_tf_line; do
    [ -n "$_adlc_tf_line" ] || continue
    _adlc_tf_cands=$((_adlc_tf_cands + 1))
    if command grep -qF -e "$_adlc_tf_mark" "${_adlc_tf_line#* }" 2>/dev/null; then
      _adlc_tf_held=$((_adlc_tf_held + 1))
      _adlc_tf_path=${_adlc_tf_line#* }
    fi
  done <<EOF
$_adlc_tf_list
EOF

  # Rung (b). A rung whose candidates do not hold the mark does not stop the chain.
  if [ "$_adlc_tf_held" = 0 ] && [ -n "${HOME:-}" ]; then
    _adlc_tf_each_root _adlc_tf_walk_root
  fi

  if [ "$_adlc_tf_held" = 1 ]; then
    printf "/wrapup: session JSONL — matched this run's mark in %s via %s\n" \
      "${_adlc_tf_path##*/}" "$_adlc_tf_via" >&2
    printf '%s\n' "$_adlc_tf_path"
    return 0
  fi

  _adlc_tf_roots=0
  if [ -n "${HOME:-}" ]; then _adlc_tf_each_root _adlc_tf_count_root; fi
  if [ "$_adlc_tf_cands" = 0 ] && [ "$_adlc_tf_roots" = 0 ]; then
    echo "/wrapup: session JSONL — no sidecar and no candidates under any harness root — REFUSING to delegate; draft from the conversation" >&2
  else
    echo "/wrapup: session JSONL — $_adlc_tf_held transcripts hold this run's mark (sidecar candidates: $_adlc_tf_cands, root candidates: $_adlc_tf_roots) — REFUSING to delegate; draft from the conversation" >&2
  fi
  return 1
}

adlc_transcript_format() {
  _adlc_tfm_path=${1-}
  [ -n "$_adlc_tfm_path" ] && [ -n "${HOME:-}" ] || return 1
  case "$_adlc_tfm_path" in
    */../*|*/..) return 1 ;;
  esac
  # The root first: it is the harness's own directory, where a sidecar is repo content
  # that can disagree. A sidecar answers only for a path under no root, such as Cursor's.
  _adlc_tfm_name=""
  _adlc_tf_each_root _adlc_tf_format_root
  if [ -n "$_adlc_tfm_name" ]; then
    printf '%s\n' "$_adlc_tfm_name"
    return 0
  fi
  _adlc_tfm_list=$(_adlc_tf_sidecars)
  while IFS= read -r _adlc_tfm_line; do
    if [ "${_adlc_tfm_line#* }" = "$_adlc_tfm_path" ]; then
      printf '%s\n' "${_adlc_tfm_line%% *}"
      return 0
    fi
  done <<EOF
$_adlc_tfm_list
EOF
  return 1
}
