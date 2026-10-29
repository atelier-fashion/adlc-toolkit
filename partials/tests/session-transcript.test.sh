#!/bin/sh
# partials/tests/session-transcript.test.sh — BUG-253 (LESSON-733): /wrapup finds
# THIS run's transcript by a mark it printed, not by walking ancestor directories.
#
# The fixture is the layout REQ-647's sprint runner actually had: a repo-root
# project dir holding an older session that names the REQ, an orchestrator session
# (in a harness worktree) whose transcript names it too, and two pipeline-runner
# subagents under <session>/subagents/ — the sibling runner names the REQ as well.
# Only the run's own transcript holds its mark.
#
#   runner_finds_own_subagent_transcript — the mark is in agent-runner.jsonl under
#                              <session>/subagents/ -> rc 0, that path, nothing else
#   main_session_transcript  — the same lookup for a top-level <session>.jsonl
#   no_mark_refuses          — every transcript names the REQ, none holds the mark
#                              -> rc 1, empty stdout, one stderr line. This is the
#                              case the REQ-423 walk answered with the 2026-10-27
#                              session (LESSON-483: a detected miss refuses)
#   two_copies_refuse        — the mark in two transcripts (a forked copy) -> rc 1
#   stale_file_ignored       — a transcript untouched for over an hour is not
#                              searched -> rc 1
#   no_projects_dir          — HOME without ~/.claude/projects -> rc 1, not an error
#   unset_home               — `set -u` with HOME unset -> rc 1, the shell survives
#   malformed_mark           — empty, a REQ id, non-hex, short -> rc 2 each
#   mark_shape               — adlc_transcript_mark prints one well-formed mark and
#                              two calls differ
#   skill_wiring             — wrapup/SKILL.md marks and finds through this partial
#                              and the ancestor walk is gone from it
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL):
#   ADLC_TEST_SHELL=zsh sh partials/tests/session-transcript.test.sh
# or, for bash, zsh, /bin/sh and dash in turn:  sh partials/tests/run.sh
#
# Exits 0 iff every case passes.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
TOOLKIT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}
PARTIAL="$PARTIALS/session-transcript.sh"

FAILS=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }

TMP=$(mktemp -d "${TMPDIR:-/tmp}/adlc-session-transcript.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

MARK=adlc-transcript-mark-0123456789abcdef

# fixture <home> — the REQ-647 layout. Every transcript names REQ-647; none holds a mark.
fixture() {
  _p="$1/.claude/projects"
  _orch="$_p/-Users-me-gh-demo--claude-worktrees-orch-abc"
  mkdir -p "$_p/-Users-me-gh-demo" "$_orch/sid-orch/subagents"
  echo '{"message":{"role":"user","content":"spec writing: draft REQ-647"}}' > "$_p/-Users-me-gh-demo/old-session.jsonl"
  echo '{"message":{"role":"user","content":"sprint: launch runners for REQ-647 and REQ-654"}}' > "$_orch/sid-orch.jsonl"
  echo '{"message":{"role":"user","content":"Pipeline REQ-654: also touches REQ-647 surfaces"}}' > "$_orch/sid-orch/subagents/agent-sibling.jsonl"
  echo '{"message":{"role":"user","content":"Pipeline REQ-647: TASK-140 done"}}' > "$_orch/sid-orch/subagents/agent-runner.jsonl"
}

# find_in <home> <mark> — run adlc_transcript_find under the shell under test.
# Sets OUT, ERR, RC.
find_in() {
  OUT=$(HOME="$1" "$SUT" -c '. "$1"; adlc_transcript_find "$2"' sh "$PARTIAL" "$2" 2>"$TMP/err")
  RC=$?
  ERR=$(cat "$TMP/err")
}

lines() { [ -z "$1" ] && echo 0 || printf '%s\n' "$1" | wc -l | tr -d ' '; }

# --- runner_finds_own_subagent_transcript ---
H="$TMP/h1"; fixture "$H"
RUNNER="$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch/subagents/agent-runner.jsonl"
echo "{\"type\":\"user\",\"toolUseResult\":{\"stdout\":\"$MARK\"}}" >> "$RUNNER"
find_in "$H" "$MARK"
if [ "$RC" = 0 ] && [ "$OUT" = "$RUNNER" ] && [ "$(lines "$ERR")" = 1 ]; then
  pass runner_finds_own_subagent_transcript
else
  fail "runner_finds_own_subagent_transcript (rc=$RC out=$OUT err=$ERR)"
fi

# --- main_session_transcript ---
H="$TMP/h2"; fixture "$H"
MAIN="$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch.jsonl"
echo "{\"type\":\"user\",\"toolUseResult\":{\"stdout\":\"$MARK\"}}" >> "$MAIN"
find_in "$H" "$MARK"
if [ "$RC" = 0 ] && [ "$OUT" = "$MAIN" ]; then
  pass main_session_transcript
else
  fail "main_session_transcript (rc=$RC out=$OUT err=$ERR)"
fi

# --- no_mark_refuses ---
H="$TMP/h3"; fixture "$H"
find_in "$H" "$MARK"
if [ "$RC" = 1 ] && [ -z "$OUT" ] && [ "$(lines "$ERR")" = 1 ] && printf '%s' "$ERR" | grep -q REFUSING; then
  pass no_mark_refuses
else
  fail "no_mark_refuses (rc=$RC out=$OUT err=$ERR)"
fi

# --- two_copies_refuse ---
H="$TMP/h4"; fixture "$H"
echo "\"$MARK\"" >> "$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch/subagents/agent-runner.jsonl"
mkdir -p "$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-fork/subagents"
cp "$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch/subagents/agent-runner.jsonl" \
   "$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-fork/subagents/agent-runner.jsonl"
find_in "$H" "$MARK"
if [ "$RC" = 1 ] && [ -z "$OUT" ] && printf '%s' "$ERR" | grep -q '^session transcript: 2 transcripts'; then
  pass two_copies_refuse
else
  fail "two_copies_refuse (rc=$RC out=$OUT err=$ERR)"
fi

# --- stale_file_ignored ---
H="$TMP/h5"; fixture "$H"
STALE="$H/.claude/projects/-Users-me-gh-demo/old-session.jsonl"
echo "\"$MARK\"" >> "$STALE"
touch -t 202001010000 "$STALE"
find_in "$H" "$MARK"
if [ "$RC" = 1 ] && [ -z "$OUT" ]; then
  pass stale_file_ignored
else
  fail "stale_file_ignored (rc=$RC out=$OUT err=$ERR)"
fi

# --- no_projects_dir ---
H="$TMP/h6"; mkdir -p "$H"
find_in "$H" "$MARK"
if [ "$RC" = 1 ] && [ -z "$OUT" ] && [ "$(lines "$ERR")" = 1 ]; then
  pass no_projects_dir
else
  fail "no_projects_dir (rc=$RC out=$OUT err=$ERR)"
fi

# --- unset_home --- native zsh restores HOME from the password database, so it
# runs as `zsh --emulate sh`, the mode in which HOME can be unset (set-u-home.test.sh).
# Two spelled-out branches, not an unquoted "$EMU": zsh running this file would not
# word-split it (BUG-118).
UNSET_HOME='set -u; . "$1"; adlc_transcript_find "$2"; echo "rc=$?"'
case "$(basename "$SUT")" in
  zsh) OUT=$(env -u HOME "$SUT" --emulate sh -c "$UNSET_HOME" sh "$PARTIAL" "$MARK" 2>/dev/null) ;;
  *)   OUT=$(env -u HOME "$SUT" -c "$UNSET_HOME" sh "$PARTIAL" "$MARK" 2>/dev/null) ;;
esac
if [ "$OUT" = "rc=1" ]; then
  pass unset_home
else
  fail "unset_home (out=$OUT)"
fi

# --- malformed_mark ---
BAD=0
for m in "" REQ-647 adlc-transcript-mark-0123456789abcdeg adlc-transcript-mark-0123456789abcde adlc-transcript-mark-0123456789abcdef0; do
  find_in "$TMP/h1" "$m"
  [ "$RC" = 2 ] && [ -z "$OUT" ] || { BAD=1; echo "  malformed '$m' -> rc=$RC"; }
done
[ "$BAD" = 0 ] && pass malformed_mark || fail malformed_mark

# --- mark_shape ---
M1=$("$SUT" -c '. "$1"; adlc_transcript_mark' sh "$PARTIAL")
M2=$("$SUT" -c '. "$1"; adlc_transcript_mark' sh "$PARTIAL")
case "$M1" in
  adlc-transcript-mark-????????????????)
    if [ "$M1" != "$M2" ] && [ -z "$(printf '%s' "${M1#adlc-transcript-mark-}" | tr -d 0-9a-f)" ]; then
      pass mark_shape
    else
      fail "mark_shape (m1=$M1 m2=$M2)"
    fi ;;
  *) fail "mark_shape (m1=$M1)" ;;
esac

# --- skill_wiring ---
SKILL="$TOOLKIT/wrapup/SKILL.md"
if grep -q 'adlc_transcript_mark$' "$SKILL" \
   && grep -q 'adlc_transcript_find "<mark>"' "$SKILL" \
   && ! grep -q 'adlc_encode_project_dir' "$SKILL"; then
  pass skill_wiring
else
  fail "skill_wiring (wrapup/SKILL.md must mark and find via the partial, with no ancestor walk)"
fi

[ "$FAILS" = 0 ] || { echo "$FAILS case(s) failed"; exit 1; }
echo "all session-transcript cases passed"
