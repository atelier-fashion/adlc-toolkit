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
#   no_projects_dir          — HOME with no harness root -> rc 1, not an error
#   unset_home               — `set -u` with HOME unset -> rc 1, the shell survives
#   malformed_mark           — empty, a REQ id, non-hex, short -> rc 2 each
#   mark_shape               — adlc_transcript_mark prints one well-formed mark and
#                              two calls differ
#   skill_wiring             — wrapup/SKILL.md marks and finds through this partial
#                              and the ancestor walk is gone from it
#
# REQ-660's chain. HOME is a sandbox, and every rejected target lives outside it and
# HOLDS the mark, so a pass is the path check at work, not the mark check.
#
#   sidecar_wins             — a good sidecar is accepted, and it outranks a root
#                              holder: rung (a) stops the chain (BR-1, BR-4)
#   sidecar_without_mark_falls_to_walk — AC-4: via walk:claude
#   pathless_sidecar_falls_to_walk — empty path, `unknown`, a harness outside the enum
#   stale_sidecar_loses      — an older session on the same REQ loses to the holder
#   planted_sidecar_never_returned — ADR-1: a sidecar naming a real file under $HOME
#                              without the mark is never returned
#   rejected_paths_are_pathless — /etc/passwd, `..`, a symlink, a symlinked directory,
#                              a sibling of $HOME, a deleted file: rung (b) runs and
#                              stderr never names them (BR-2, BR-16, AC-6)
#   two_holders_refuse       — two sidecars or two roots -> the refusal with counts
#   two_sidecars_one_file    — one candidate, accepted
#   no_sidecar_dir           — AC-13: no directory, or an empty one, is rung (b) alone
#   sidecar_dir_hygiene      — a symlinked directory or sidecar, a dotfile and an
#                              unreadable sidecar each contribute nothing
#   git_toplevel             — sidecars are read from the toplevel, not the subdirectory
#   symlinked_home           — containment compares resolved paths
#   walk_each_root           — BR-9: a hit at the deepest allowed level under each of
#                              the four roots names its harness and format
#   walk_bounds              — too deep, misnamed, stale and symlinked files in each
#                              root are not candidates
#   shadowed_grep            — LESSON-717: a grep function cannot pass a non-holder
#   writer_reader_contract   — a sidecar written by adlc_session_record is read here
#   format_from_sidecar      — a path under no root takes the sidecar's harness, and
#                              a root outranks a sidecar that disagrees with it
#   format_from_root         — an `unknown` sidecar leaves the root to answer
#   format_refuses           — no sidecar and no root -> rc 1, empty stdout
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

# macOS temp dirs sit under a symlink, and containment compares resolved paths.
TMP=$(CDPATH= cd -P -- "$TMP" && pwd -P)

# Every call runs in a working tree under $TMP, with no enclosing checkout to find.
unset GIT_DIR GIT_WORK_TREE
GIT_CEILING_DIRECTORIES=$TMP
export GIT_CEILING_DIRECTORIES
NO_TREE="$TMP/no-tree"
mkdir -p "$NO_TREE"

MARK=adlc-transcript-mark-0123456789abcdef

OUTSIDE="$TMP/outside"
SECRET="$OUTSIDE/secret.jsonl"
mkdir -p "$OUTSIDE"
echo "{\"toolUseResult\":{\"stdout\":\"$MARK\"}}" > "$SECRET"

NOTHING="/wrapup: session JSONL — no sidecar and no candidates under any harness root — REFUSING to delegate; draft from the conversation"
# matched <basename> <source> / refused <holders> <sidecar candidates> <root candidates>
matched() { echo "/wrapup: session JSONL — matched this run's mark in $1 via $2"; }
refused() { echo "/wrapup: session JSONL — $1 transcripts hold this run's mark (sidecar candidates: $2, root candidates: $3) — REFUSING to delegate; draft from the conversation"; }

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

# hold <file> — a transcript holding this run's mark, as a tool result would.
hold() {
  mkdir -p "$(dirname -- "$1")"
  echo "{\"type\":\"user\",\"toolUseResult\":{\"stdout\":\"$MARK\"}}" >> "$1"
}

# sidecar <tree> <id> <harness> <transcript_path> — a sidecar in the writer's format.
sidecar() {
  mkdir -p "$1/.adlc/.session"
  printf 'harness=%s\nsession_id=%s\ntranscript_path=%s\ncwd=%s\nstarted_at=2026-10-30T00:00:00Z\n' \
    "$3" "$2" "$4" "$1" > "$1/.adlc/.session/$2"
}

# find_in <home> <mark> [<working tree>] — run adlc_transcript_find under the shell
# under test. Sets OUT, ERR, RC.
find_in() {
  OUT=$(cd "${3:-$NO_TREE}" && HOME="$1" "$SUT" -c '. "$1"; adlc_transcript_find "$2"' sh "$PARTIAL" "$2" 2>"$TMP/err")
  RC=$?
  ERR=$(cat "$TMP/err")
}

# format_in <home> <path> [<working tree>] — the same for adlc_transcript_format.
format_in() {
  OUT=$(cd "${3:-$NO_TREE}" && HOME="$1" "$SUT" -c '. "$1"; adlc_transcript_format "$2"' sh "$PARTIAL" "$2" 2>"$TMP/err")
  RC=$?
  ERR=$(cat "$TMP/err")
}

# expect <case> <rc> <stdout> <stderr> — the whole stderr, so it is exactly that one line.
expect() {
  if [ "$RC" = "$2" ] && [ "$OUT" = "$3" ] && [ "$ERR" = "$4" ]; then
    pass "$1"
  else
    fail "$1 (rc=$RC out=$OUT err=$ERR)"
  fi
}

# --- runner_finds_own_subagent_transcript ---
H="$TMP/h1"; fixture "$H"
RUNNER="$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch/subagents/agent-runner.jsonl"
echo "{\"type\":\"user\",\"toolUseResult\":{\"stdout\":\"$MARK\"}}" >> "$RUNNER"
find_in "$H" "$MARK"
expect runner_finds_own_subagent_transcript 0 "$RUNNER" "$(matched agent-runner.jsonl walk:claude)"

# --- main_session_transcript ---
H="$TMP/h2"; fixture "$H"
MAIN="$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch.jsonl"
echo "{\"type\":\"user\",\"toolUseResult\":{\"stdout\":\"$MARK\"}}" >> "$MAIN"
find_in "$H" "$MARK"
expect main_session_transcript 0 "$MAIN" "$(matched sid-orch.jsonl walk:claude)"

# --- no_mark_refuses ---
H="$TMP/h3"; fixture "$H"
find_in "$H" "$MARK"
expect no_mark_refuses 1 "" "$(refused 0 0 4)"

# --- two_copies_refuse ---
H="$TMP/h4"; fixture "$H"
echo "\"$MARK\"" >> "$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch/subagents/agent-runner.jsonl"
mkdir -p "$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-fork/subagents"
cp "$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch/subagents/agent-runner.jsonl" \
   "$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-fork/subagents/agent-runner.jsonl"
find_in "$H" "$MARK"
expect two_copies_refuse 1 "" "$(refused 2 0 5)"

# --- stale_file_ignored ---
H="$TMP/h5"; fixture "$H"
STALE="$H/.claude/projects/-Users-me-gh-demo/old-session.jsonl"
echo "\"$MARK\"" >> "$STALE"
touch -t 202001010000 "$STALE"
find_in "$H" "$MARK"
expect stale_file_ignored 1 "" "$(refused 0 0 3)"

# --- no_projects_dir ---
H="$TMP/h6"; mkdir -p "$H"
find_in "$H" "$MARK"
expect no_projects_dir 1 "" "$NOTHING"

# --- unset_home --- native zsh restores HOME from the password database, so it
# runs as `zsh --emulate sh`, the mode in which HOME can be unset (set-u-home.test.sh).
# Two spelled-out branches, not an unquoted "$EMU": zsh running this file would not
# word-split it (BUG-118).
# A sidecar in the tree: with no HOME there is nothing to contain it, so it is pathless.
T="$TMP/t-unset"; mkdir -p "$T"; sidecar "$T" sid-1 claude "$SECRET"
UNSET_HOME='set -u; . "$1"; adlc_transcript_find "$2"; echo "rc=$?"; adlc_transcript_format "$3"; echo "rc=$?"'
case "$(basename "$SUT")" in
  zsh) OUT=$(cd "$T" && env -u HOME "$SUT" --emulate sh -c "$UNSET_HOME" sh "$PARTIAL" "$MARK" "$SECRET" 2>"$TMP/err") ;;
  *)   OUT=$(cd "$T" && env -u HOME "$SUT" -c "$UNSET_HOME" sh "$PARTIAL" "$MARK" "$SECRET" 2>"$TMP/err") ;;
esac
ERR=$(cat "$TMP/err")
if [ "$OUT" = "rc=1
rc=1" ] && [ "$ERR" = "$NOTHING" ]; then
  pass unset_home
else
  fail "unset_home (out=$OUT err=$ERR)"
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

# --- sidecar_wins --- the path holds a space, and it is outside every root, so only
# the sidecar can have found it. Then a root holder too: rung (a) still stops the chain.
H="$TMP/s1"; T="$TMP/t1"; mkdir -p "$H" "$T"
OWN="$H/elsewhere/own session.jsonl"
hold "$OWN"
sidecar "$T" sid-1 claude "$OWN"
find_in "$H" "$MARK" "$T"
expect sidecar_wins 0 "$OWN" "$(matched 'own session.jsonl' sidecar)"
hold "$H/.claude/projects/-Users-me-gh-demo/other.jsonl"
find_in "$H" "$MARK" "$T"
expect sidecar_wins_over_a_root_holder 0 "$OWN" "$(matched 'own session.jsonl' sidecar)"

# --- sidecar_without_mark_falls_to_walk ---
H="$TMP/s2"; T="$TMP/t2"; fixture "$H"; mkdir -p "$T"
RUNNER="$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch/subagents/agent-runner.jsonl"
sidecar "$T" sid-parent claude "$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch.jsonl"
hold "$RUNNER"
find_in "$H" "$MARK" "$T"
expect sidecar_without_mark_falls_to_walk 0 "$RUNNER" "$(matched agent-runner.jsonl walk:claude)"

# --- pathless_sidecar_falls_to_walk --- two of these name a file that DOES hold the
# mark, so `unknown` and an out-of-enum harness are what rejects them.
H="$TMP/s3"; T="$TMP/t3"; mkdir -p "$H" "$T"
NAMED="$H/elsewhere/named.jsonl"; hold "$NAMED"
WALKED="$H/.codex/sessions/2026/10/30/rollout-1.jsonl"; hold "$WALKED"
sidecar "$T" sid-empty claude ""
sidecar "$T" sid-unknown unknown "$NAMED"
sidecar "$T" sid-bogus nonsense "$NAMED"
echo "session_id=sid-keyless" > "$T/.adlc/.session/sid-keyless"
find_in "$H" "$MARK" "$T"
expect pathless_sidecar_falls_to_walk 0 "$WALKED" "$(matched rollout-1.jsonl walk:codex)"

# --- stale_sidecar_loses --- an older session on the same REQ: its transcript names
# REQ-647 and exists, and it still loses to the file holding the mark.
H="$TMP/s4"; T="$TMP/t4"; fixture "$H"; mkdir -p "$T"
RUNNER="$H/.claude/projects/-Users-me-gh-demo--claude-worktrees-orch-abc/sid-orch/subagents/agent-runner.jsonl"
sidecar "$T" sid-old claude "$H/.claude/projects/-Users-me-gh-demo/old-session.jsonl"
hold "$RUNNER"
find_in "$H" "$MARK" "$T"
expect stale_sidecar_loses 0 "$RUNNER" "$(matched agent-runner.jsonl walk:claude)"

# --- planted_sidecar_never_returned --- ADR-1: a hostile repo commits a sidecar naming
# a real file under $HOME. Usable, so it counts, and it cannot hold the mark.
H="$TMP/s5"; T="$TMP/t5"; mkdir -p "$H/.ssh" "$T"
echo "private key material" > "$H/.ssh/id_ed25519"
sidecar "$T" sid-planted claude "$H/.ssh/id_ed25519"
find_in "$H" "$MARK" "$T"
expect planted_sidecar_never_returned 1 "" "$(refused 0 1 0)"
WALKED="$H/.gemini/tmp/0a1b/chats/session-1.jsonl"; hold "$WALKED"
find_in "$H" "$MARK" "$T"
expect planted_sidecar_loses_to_the_holder 0 "$WALKED" "$(matched session-1.jsonl walk:gemini)"

# --- rejected_paths_are_pathless --- rejected <label> <sidecar's path>. $SECRET holds
# the mark, so only the path check stands between it and stdout. $NOTHING is the
# whole stderr, so the rejected path appears nowhere in it, and a candidate count of
# zero shows the sidecar was not a candidate.
H="$TMP/s6"; mkdir -p "$H/a"
ln -s "$SECRET" "$H/link.jsonl"
ln -s "$OUTSIDE" "$H/linkdir"
hold "$H-evil/secret.jsonl"
hold "$H/inside.jsonl"
BAD=""
rejected() {
  _T="$TMP/rej-$1"; mkdir -p "$_T"
  sidecar "$_T" sid-rej claude "$2"
  find_in "$H" "$MARK" "$_T"
  if [ "$RC" != 1 ] || [ -n "$OUT" ] || [ "$ERR" != "$NOTHING" ]; then
    BAD="$BAD $1"; echo "  $1 -> rc=$RC out=$OUT err=$ERR"
  fi
}
rejected outside-home "$SECRET"
rejected etc-passwd /etc/passwd
rejected dotdot "$H/../outside/secret.jsonl"
rejected dotdot-deep "$H/a/../../outside/secret.jsonl"
rejected dotdot-inside-home "$H/a/../inside.jsonl"
rejected trailing-dotdot "$H/a/.."
rejected symlink "$H/link.jsonl"
rejected symlinked-dir "$H/linkdir/secret.jsonl"
rejected sibling-of-home "$H-evil/secret.jsonl"
rejected deleted "$H/gone.jsonl"
[ -z "$BAD" ] && pass rejected_paths_are_pathless || fail "rejected_paths_are_pathless:$BAD"

# Rung (b) still runs after a rejected sidecar (AC-6).
T="$TMP/s6t"; mkdir -p "$T"; sidecar "$T" sid-rej claude "$SECRET"
WALKED="$H/.copilot/session-state/sid-1/events.jsonl"; hold "$WALKED"
find_in "$H" "$MARK" "$T"
expect rejected_path_falls_to_walk 0 "$WALKED" "$(matched events.jsonl walk:copilot)"

# --- two_holders_refuse ---
H="$TMP/s7"; T="$TMP/t7"; mkdir -p "$H" "$T"
hold "$H/one/a.jsonl"; hold "$H/two/b.jsonl"
sidecar "$T" sid-a claude "$H/one/a.jsonl"
sidecar "$T" sid-b claude "$H/two/b.jsonl"
find_in "$H" "$MARK" "$T"
expect two_holders_refuse 1 "" "$(refused 2 2 0)"
H="$TMP/s8"; mkdir -p "$H"
hold "$H/.claude/projects/-a/s.jsonl"; hold "$H/.codex/sessions/2026/10/30/rollout-1.jsonl"
find_in "$H" "$MARK"
expect two_roots_refuse 1 "" "$(refused 2 0 2)"

# --- two_sidecars_one_file --- one candidate, whatever the second sidecar says.
H="$TMP/s9"; T="$TMP/t9"; mkdir -p "$H" "$T"
hold "$H/one/a.jsonl"
sidecar "$T" sid-a claude "$H/one/a.jsonl"
sidecar "$T" sid-b claude "$H/one/a.jsonl"
find_in "$H" "$MARK" "$T"
expect two_sidecars_one_file 0 "$H/one/a.jsonl" "$(matched a.jsonl sidecar)"

# --- no_sidecar_dir --- AC-13: rung (b) alone, with no directory or an empty one.
H="$TMP/s10"; T="$TMP/t10"; mkdir -p "$H" "$T"
find_in "$H" "$MARK" "$T"
expect no_sidecar_dir_refuses 1 "" "$NOTHING"
hold "$H/.claude/projects/-a/s.jsonl"
find_in "$H" "$MARK" "$T"
expect no_sidecar_dir 0 "$H/.claude/projects/-a/s.jsonl" "$(matched s.jsonl walk:claude)"
mkdir -p "$T/.adlc/.session"
find_in "$H" "$MARK" "$T"
expect empty_sidecar_dir 0 "$H/.claude/projects/-a/s.jsonl" "$(matched s.jsonl walk:claude)"

# --- sidecar_dir_hygiene --- each names a real holder under $HOME, so each would be
# accepted if it were read. An unreadable sidecar's error must not reach stderr.
H="$TMP/s11"; mkdir -p "$H"; hold "$H/own.jsonl"
T="$TMP/t11-dir"; mkdir -p "$T/.adlc" "$TMP/t11-real"
sidecar "$TMP/t11-real" sid-1 claude "$H/own.jsonl"
ln -s "$TMP/t11-real/.adlc/.session" "$T/.adlc/.session"
find_in "$H" "$MARK" "$T"
expect symlinked_session_dir_ignored 1 "" "$NOTHING"
T="$TMP/t11-file"; mkdir -p "$T/.adlc/.session"
ln -s "$TMP/t11-real/.adlc/.session/sid-1" "$T/.adlc/.session/sid-link"
find_in "$H" "$MARK" "$T"
expect symlinked_sidecar_ignored 1 "" "$NOTHING"
T="$TMP/t11-dot"; mkdir -p "$T"
sidecar "$T" .tmp-123 claude "$H/own.jsonl"
sidecar "$T" .gitignore claude "$H/own.jsonl"
find_in "$H" "$MARK" "$T"
expect dotfile_sidecars_ignored 1 "" "$NOTHING"
T="$TMP/t11-mode"; mkdir -p "$T"
sidecar "$T" sid-1 claude "$H/elsewhere-gone.jsonl"
chmod 000 "$T/.adlc/.session/sid-1"
find_in "$H" "$MARK" "$T"
chmod 600 "$T/.adlc/.session/sid-1"
expect unreadable_sidecar_is_quiet 1 "" "$NOTHING"

# --- git_toplevel --- a subdirectory of a checkout reads the toplevel's sidecars.
H="$TMP/s12"; T="$TMP/t12"; mkdir -p "$H" "$T/deep/er"
hold "$H/own.jsonl"
HOME="$H" git init -q "$T"
sidecar "$T" sid-1 claude "$H/own.jsonl"
find_in "$H" "$MARK" "$T/deep/er"
expect git_toplevel 0 "$H/own.jsonl" "$(matched own.jsonl sidecar)"

# --- symlinked_home --- $HOME itself a symlink: the sidecar spells it, and both sides
# of the containment check resolve.
REAL="$TMP/s13-real"; H="$TMP/s13-link"; T="$TMP/t13"; mkdir -p "$REAL" "$T"
ln -s "$REAL" "$H"
hold "$REAL/own.jsonl"
sidecar "$T" sid-1 claude "$H/own.jsonl"
find_in "$H" "$MARK" "$T"
expect symlinked_home 0 "$H/own.jsonl" "$(matched own.jsonl sidecar)"
# The same file spelled without $HOME resolves under it, and is still not a $HOME path.
sidecar "$T" sid-1 claude "$REAL/own.jsonl"
find_in "$H" "$MARK" "$T"
expect path_must_start_with_home 1 "" "$NOTHING"

# --- walk_each_root --- walk_case <harness> <deepest allowed path under $HOME>.
walk_case() {
  H="$TMP/w-$1"; mkdir -p "$H"
  F="$H/$2"; hold "$F"
  find_in "$H" "$MARK"
  expect "walk_each_root:$1" 0 "$F" "$(matched "$(basename -- "$F")" "walk:$1")"
  format_in "$H" "$F"
  expect "walk_each_root:$1:format" 0 "$1" ""
}
walk_case claude .claude/projects/a/b/c/d/agent-1.jsonl
walk_case codex .codex/sessions/2026/10/30/rollout-2026-10-30T00-00-00-abc.jsonl
walk_case copilot .copilot/session-state/sid-1/events.jsonl
walk_case gemini .gemini/tmp/0a1b2c/chats/session-2026-10-30.jsonl

# --- walk_bounds --- bounds_case <harness> <too deep> <misnamed> <stale> <symlink>, the
# last two in bounds. All four hold the mark and none is a candidate, so the refusal
# is the one with nothing to look at.
bounds_case() {
  H="$TMP/b-$1"; mkdir -p "$H"
  hold "$H/$2"; hold "$H/$3"
  hold "$H/$4"; touch -t 202001010000 "$H/$4"
  mkdir -p "$(dirname -- "$H/$5")"; ln -s "$SECRET" "$H/$5"
  find_in "$H" "$MARK"
  expect "walk_bounds:$1" 1 "" "$NOTHING"
}
bounds_case claude .claude/projects/a/b/c/d/e/deep.jsonl .claude/projects/a/notes.txt .claude/projects/a/s.jsonl .claude/projects/a/link.jsonl
bounds_case codex .codex/sessions/2026/10/30/x/rollout-1.jsonl .codex/sessions/2026/10/30/other.jsonl .codex/sessions/2026/10/30/rollout-1.jsonl .codex/sessions/2026/10/30/rollout-2.jsonl
bounds_case copilot .copilot/session-state/a/b/events.jsonl .copilot/session-state/a/other.jsonl .copilot/session-state/a/events.jsonl .copilot/session-state/c/events.jsonl
bounds_case gemini .gemini/tmp/a/chats/x/session-1.jsonl .gemini/tmp/a/chats/logs.jsonl .gemini/tmp/a/chats/session-1.jsonl .gemini/tmp/a/chats/session-2.jsonl

# --- shadowed_grep --- LESSON-717: the executor can rebind grep. A function that always
# says "matched" must not turn a planted sidecar into a delegated file.
H="$TMP/s14"; T="$TMP/t14"; mkdir -p "$H/elsewhere" "$T"
echo "no mark here" > "$H/elsewhere/other.jsonl"
sidecar "$T" sid-1 claude "$H/elsewhere/other.jsonl"
OUT=$(cd "$T" && HOME="$H" "$SUT" -c 'grep() { return 0; }; . "$1"; adlc_transcript_find "$2"' sh "$PARTIAL" "$MARK" 2>"$TMP/err")
RC=$?; ERR=$(cat "$TMP/err")
expect shadowed_grep 1 "" "$(refused 0 1 0)"

# --- writer_reader_contract --- LESSON-729: the file adlc_session_record writes, not a
# hand-made copy, is what rung (a) and adlc_transcript_format read. The transcript also
# sits under a root, so `via sidecar` shows the sidecar is what found it.
if command -v python3 >/dev/null 2>&1; then
  H="$TMP/s15"; T="$TMP/t15"; mkdir -p "$H" "$T/.adlc"
  F="$H/.claude/projects/-a/s1.jsonl"; hold "$F"
  printf '{"session_id":"s1","transcript_path":"%s","cwd":"%s","hook_event_name":"SessionStart","source":"startup"}' "$F" "$T" \
    | (cd "$T" && HOME="$H" "$SUT" -c '. "$1"; adlc_session_record' sh "$PARTIALS/session-record.sh")
  find_in "$H" "$MARK" "$T"
  expect writer_reader_contract 0 "$F" "$(matched s1.jsonl sidecar)"
  format_in "$H" "$F" "$T"
  expect writer_reader_contract:format 0 claude ""
else
  echo "SKIP: writer_reader_contract (no python3)"
fi

# --- format_from_sidecar --- a file under no root gets the sidecar's harness. Under a
# root the root answers, so a sidecar in the repo cannot relabel a harness's own file.
H="$TMP/s16"; T="$TMP/t16"; mkdir -p "$H" "$T"
F="$H/elsewhere/s.jsonl"; hold "$F"
sidecar "$T" sid-1 cursor "$F"
format_in "$H" "$F" "$T"
expect format_from_sidecar 0 cursor ""
R="$H/.claude/projects/-a/s.jsonl"; hold "$R"
sidecar "$T" sid-2 cursor "$R"
format_in "$H" "$R" "$T"
expect format_from_sidecar:root_outranks_a_conflicting_sidecar 0 claude ""

# --- format_from_root --- an `unknown` sidecar names no format.
H="$TMP/s17"; T="$TMP/t17"; mkdir -p "$H" "$T"
F="$H/.codex/sessions/2026/10/30/rollout-1.jsonl"; hold "$F"
sidecar "$T" sid-1 unknown "$F"
format_in "$H" "$F" "$T"
expect format_from_root 0 codex ""

# --- format_refuses --- a file under no root and named by no sidecar, an empty
# argument, and a `..` path that only looks as if it is under a root.
H="$TMP/s18"; mkdir -p "$H"; hold "$H/elsewhere/s.jsonl"
format_in "$H" "$H/elsewhere/s.jsonl"
expect format_refuses 1 "" ""
format_in "$H" ""
expect format_refuses:empty 1 "" ""
format_in "$H" "$H/.claude/projects/../elsewhere/s.jsonl"
expect format_refuses:dotdot 1 "" ""

# --- skill_wiring ---
SKILL="$TOOLKIT/wrapup/SKILL.md"
if grep -q 'adlc_transcript_mark$' "$SKILL" \
   && grep -q 'adlc_transcript_find "<mark>"' "$SKILL" \
   && grep -qF 'FORMAT=$(adlc_transcript_format "$JSONL" 2>/dev/null) || FORMAT=""' "$SKILL" \
   && grep -qF 'skill-flag.sh mark "$flag" format "$FORMAT"' "$SKILL" \
   && grep -qF 'skill-flag.sh read "$flag" format' "$SKILL" \
   && grep -qF '[ -n "$FORMAT" ] || FORMAT=claude' "$SKILL" \
   && grep -qF 'extract-chat "$JSONL" -o "$TMPFILE" --format "$FORMAT"' "$SKILL" \
   && ! grep -q 'adlc_encode_project_dir' "$SKILL"; then
  pass skill_wiring
else
  fail "skill_wiring (wrapup/SKILL.md must mark and find via the partial, with no ancestor walk)"
fi

[ "$FAILS" = 0 ] || { echo "$FAILS case(s) failed"; exit 1; }
echo "all session-transcript cases passed"
