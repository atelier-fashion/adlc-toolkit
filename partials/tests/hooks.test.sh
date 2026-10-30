#!/bin/sh
# partials/tests/hooks.test.sh — REQ-657 BR-10, BR-16, AC-8, AC-14; REQ-660 BR-5 to
# BR-7, AC-1, AC-2, AC-13.
#
# The hook commands exactly as the committed `claude` render carries them
# (harness/claude/rendered/settings.json), run the way a harness runs a hook
# command: `<shell> -c "<command>"`, from a sandbox project, with the payload on
# stdin, under the shell being tested. Every case has its own sandbox HOME, so
# nothing here reads or writes the real home directory.
#
# Cases:
#   case_ethos_inject_prints: with .adlc/ETHOS.md present, ethos-inject prints it
#       byte for byte and exits 0 (both SessionStart groups carry the same command).
#   case_ethos_inject_absent / _empty (benign path): no ETHOS, or an empty one,
#       prints nothing and exits 0.
#   case_vendored_partial_wins: a project's .adlc/partials/ethos-inject.sh is the
#       one sourced (repo-local first, LESSON-441).
#   case_partial_absent_both_levels: with no vendored copy and no ToolkitRoot,
#       each command exits 0 and prints nothing on stdout or stderr.
#   case_session_record_sources_silently: the partial sources with exit 0 and no output.
#   case_session_record_writes: a payload with the real five keys writes
#       .adlc/.session/<id>: harness, session_id, transcript_path, cwd, started_at in
#       that order, mode 600, with a self-ignoring .gitignore, so `git status` shows
#       nothing; stdout empty.
#   case_session_record_inert (benign path): no .adlc/ writes nothing; an empty,
#       non-JSON or id-less payload, or a closed stdin, exits 0, prints nothing and
#       writes at most a generated-id sidecar; a symlinked .adlc or .adlc/.session
#       writes nothing.
#   case_session_record_no_python: with no python3 the hook writes nothing, exit 0.
#   case_session_record_planted_module / _shadowed_python: a planted json.py and a
#       shell function named python3 change nothing (ADR-4, LESSON-717).
#   case_session_record_unsafe_id: an id that is not a safe file name is replaced.
#   case_session_record_transcript_contained: a path outside $HOME, with a `..`
#       segment, with a control character, or relative is recorded empty.
#   case_session_record_cwd_clean: a cwd that would break the line format is not used.
#   case_session_record_resume: a re-fire keeps started_at and rewrites the rest, and
#       a symlinked sidecar is replaced without being followed.
#   case_session_record_prunes: a 31-day-old sidecar goes, a 29-day-old one stays, and
#       .gitignore is never pruned.
#   case_session_record_harness_arg: `--harness X --field item=key` reads only the
#       named items; an invalid harness records `unknown`.
#   case_session_record_detection: a payload matching no table row records `unknown`
#       and reads the claude keys.
#   case_session_record_timing / _stdin_cap: an open stdin and an oversized payload
#       both end inside the entry's timeout_s.
#   case_rendered_sources_guarded: every rendered command sources its partial with
#       the one canonical guarded spelling.
#   case_copilot_*: the commands harness/copilot/rendered/adlc.json carries. With
#       ETHOS present the output parses as one JSON object whose additionalContext
#       equals the file, quotes, backslashes, tabs and control bytes included
#       (REQ-656 BR-5); absent, it prints nothing; session-record is passed
#       --harness copilot, and with no partial at either level both exit 0 silently.
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL):
#   ADLC_TEST_SHELL=dash sh partials/tests/hooks.test.sh
# Exits 0 iff every check passes and the executed-case count clears its floor.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TOOLKIT=$(CDPATH= cd -- "$HERE/../.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}
GOLDEN="$TOOLKIT/harness/claude/rendered/settings.json"

FAILS=0
CASES=0
pass() { printf 'PASS: %s\n' "$1"; CASES=$((CASES + 1)); }
fail() { printf 'FAIL: %s\n' "$1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (expected '$2', got '$3')"; fi
}

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-hooks.XXXXXX") || { echo "hooks.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "hooks.test.sh: sandbox path invalid" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-hooks.*) ;;
  *) echo "hooks.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
trap 'rm -rf "$SANDBOX"' EXIT
trap 'rm -rf "$SANDBOX"; exit 130' INT TERM
unset CLAUDE_PLUGIN_ROOT ADLC_TOOLKIT_ROOT ADLC_HOME

# The rendered commands, one file each (python3 reads the JSON; no shell parsing).
python3 - "$GOLDEN" "$SANDBOX" <<'PY' || { echo "hooks.test.sh: could not read the golden render" >&2; exit 1; }
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
seen = {}
for group in doc["hooks"]["SessionStart"]:
    for k, hook in enumerate(group["hooks"]):
        cmd = hook["command"]
        name = "ethos" if "adlc_ethos_inject" in cmd else "record"
        tag = "%s-%s" % (name, (group.get("matcher") or "all").split("|")[0])
        with open("%s/%s.cmd" % (sys.argv[2], tag), "w", encoding="utf-8") as fh:
            fh.write(cmd)
PY
ETHOS_CMD=$(cat "$SANDBOX/ethos-startup.cmd")
RECORD_CMD=$(cat "$SANDBOX/record-startup.cmd")
check "case_rendered_groups: the compact group carries the same ethos-inject command" \
  "$ETHOS_CMD" "$(cat "$SANDBOX/ethos-compact.cmd")"

new_project() { # new_project <name> — a fresh project dir and HOME, cd'd into by run_hook
  PROJ="$SANDBOX/p-$1"
  HOMEDIR="$SANDBOX/h-$1"
  mkdir -p "$PROJ" "$HOMEDIR" || exit 1
}
run_hook() { # run_hook <command> <payload> [root] — sets OUT, ERR, RC
  ( cd "$PROJ" || exit 99
    if [ -n "${3-}" ]; then CLAUDE_PLUGIN_ROOT=$3; export CLAUDE_PLUGIN_ROOT; fi
    HOME=$HOMEDIR; export HOME
    printf '%s' "$2" | "$SUT" -c "$1" >"$SANDBOX/out" 2>"$SANDBOX/err" )
  RC=$?
  OUT=$(cat "$SANDBOX/out")
  ERR=$(cat "$SANDBOX/err")
}

# --- ethos-inject ------------------------------------------------------------
new_project ethos
mkdir -p "$PROJ/.adlc"
printf '# ETHOS\n\n## 1. Known principle\nline two\n' > "$PROJ/.adlc/ETHOS.md"
run_hook "$ETHOS_CMD" '{}' "$TOOLKIT"
check "case_ethos_inject_prints: exit 0" "0" "$RC"
check "case_ethos_inject_prints: prints .adlc/ETHOS.md" "$(cat "$PROJ/.adlc/ETHOS.md")" "$OUT"
check "case_ethos_inject_prints: stderr empty" "" "$ERR"

new_project noethos
mkdir -p "$PROJ/.adlc"
run_hook "$ETHOS_CMD" '{}' "$TOOLKIT"
check "case_ethos_inject_absent: exit 0" "0" "$RC"
check "case_ethos_inject_absent: prints nothing" "" "$OUT$ERR"
: > "$PROJ/.adlc/ETHOS.md"
run_hook "$ETHOS_CMD" '{}' "$TOOLKIT"
check "case_ethos_inject_empty: exit 0" "0" "$RC"
check "case_ethos_inject_empty: prints nothing" "" "$OUT$ERR"

new_project vendored
mkdir -p "$PROJ/.adlc/partials"
printf 'adlc_ethos_inject() { echo VENDORED; }\n' > "$PROJ/.adlc/partials/ethos-inject.sh"
run_hook "$ETHOS_CMD" '{}' "$TOOLKIT"
check "case_vendored_partial_wins: the repo-local copy is sourced" "VENDORED" "$OUT"

# --- both levels absent ------------------------------------------------------
new_project absent
mkdir -p "$PROJ/.adlc"
printf 'x\n' > "$PROJ/.adlc/ETHOS.md"
run_hook "$ETHOS_CMD" '{}'
check "case_partial_absent_both_levels: ethos-inject exits 0" "0" "$RC"
check "case_partial_absent_both_levels: ethos-inject is silent" "" "$OUT$ERR"
run_hook "$RECORD_CMD" '{"session_id":"abc"}'
check "case_partial_absent_both_levels: session-record exits 0" "0" "$RC"
check "case_partial_absent_both_levels: session-record is silent" "" "$OUT$ERR"
check "case_partial_absent_both_levels: session-record wrote nothing" "no" "$( [ -e "$PROJ/.adlc/.session" ] && echo yes || echo no)"

# --- session-record ----------------------------------------------------------
# Sidecar values come back through sed, so nothing here parses JSON in sh. Temp
# paths on macOS sit under a symlink, so a value the hook derived from its own
# working directory is compared with `pwd -P`. No variable here is called `path`:
# zsh ties that name to PATH.
LF='
'
n=0
next_project() { n=$((n + 1)); new_project "$1-$n"; mkdir -p "$PROJ/.adlc"; }
field() { # field <sidecar> <key> — the value on that key's line
  command sed -n "s/^$2=//p" "$1" 2>/dev/null
}
keys_of() { # keys_of <sidecar> — the keys, in order, on one line
  command sed 's/=.*//' "$1" 2>/dev/null | tr '\n' ' '
}
sidecars() { # the sidecars in this project's .adlc/.session, one per line
  ls "$PROJ/.adlc/.session" 2>/dev/null
}
is_generated() { # the one sidecar is named gen-<16 hex>, and its session_id line agrees
  g=$(sidecars)
  [ "$(printf '%s\n' "$g" | command grep -cE '^gen-[0-9a-f]{16}$')" = "1" ] || return 0
  [ "$(printf '%s\n' "$g" | command grep -c '.')" = "1" ] || return 0
  [ "$(field "$PROJ/.adlc/.session/$g" session_id)" = "$g" ] && echo yes
}
age() { # age <file> <days> — set the mtime that many days back
  python3 -c 'import os, sys, time
t = time.time() - int(sys.argv[2]) * 86400
os.utime(sys.argv[1], (t, t))' "$1" "$2"
}
run_hook_from() { # run_hook_from <command> <stdin file> — run_hook, with stdin from a file or FIFO
  ( cd "$PROJ" || exit 99
    CLAUDE_PLUGIN_ROOT=$TOOLKIT; export CLAUDE_PLUGIN_ROOT
    HOME=$HOMEDIR; export HOME
    "$SUT" -c "$1" <"$2" >"$SANDBOX/out" 2>"$SANDBOX/err" )
  RC=$?
  OUT=$(cat "$SANDBOX/out")
  ERR=$(cat "$SANDBOX/err")
}

"$SUT" -c ". '$TOOLKIT/partials/session-record.sh'" >"$SANDBOX/out" 2>"$SANDBOX/err"
check "case_session_record_sources_silently: exit 0" "0" "$?"
check "case_session_record_sources_silently: prints nothing" "" "$(cat "$SANDBOX/out" "$SANDBOX/err")"

# The real payload's five keys (Claude Code 2.1.258, 2026-10-30).
next_project record
git -C "$PROJ" init -q 2>/dev/null
tp="$HOMEDIR/.claude/projects/p/s.jsonl"
run_hook "$RECORD_CMD" "{\"session_id\":\"sess-123_A\",\"transcript_path\":\"$tp\",\"cwd\":\"$PROJ\",\"hook_event_name\":\"SessionStart\",\"source\":\"startup\"}" "$TOOLKIT"
SC="$PROJ/.adlc/.session/sess-123_A"
check "case_session_record_writes: exit 0" "0" "$RC"
check "case_session_record_writes: stdout and stderr empty" "" "$OUT$ERR"
check "case_session_record_writes: the five lines, in order" "harness session_id transcript_path cwd started_at " "$(keys_of "$SC")"
check "case_session_record_writes: harness" "claude" "$(field "$SC" harness)"
check "case_session_record_writes: session_id" "sess-123_A" "$(field "$SC" session_id)"
check "case_session_record_writes: transcript_path, as the payload gave it" "$tp" "$(field "$SC" transcript_path)"
check "case_session_record_writes: cwd" "$PROJ" "$(field "$SC" cwd)"
check "case_session_record_writes: started_at is UTC ISO-8601" "1" \
  "$(command grep -cE '^started_at=[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$' "$SC")"
perm=$(ls -l "$SC" 2>/dev/null | cut -c1-10)
check "case_session_record_writes: mode 600" "-rw-------" "$perm"
check "case_session_record_writes: the directory ignores itself" "*" "$(cat "$PROJ/.adlc/.session/.gitignore" 2>/dev/null)"
check "case_session_record_writes: no temporary file stays" ".gitignore${LF}sess-123_A" "$(ls -A "$PROJ/.adlc/.session")"
check "case_session_record_writes: git status shows nothing" "" "$(git -C "$PROJ" status --porcelain 2>/dev/null)"

next_project nocwd
run_hook "$RECORD_CMD" '{"session_id":"s1"}' "$TOOLKIT"
check "case_session_record_writes: no payload cwd — the working directory" \
  "$(cd "$PROJ" && pwd -P)" "$(field "$PROJ/.adlc/.session/s1" cwd)"

new_project inert
run_hook "$RECORD_CMD" '{"session_id":"abc"}' "$TOOLKIT"
check "case_session_record_inert: no .adlc/ — exit 0" "0" "$RC"
check "case_session_record_inert: no .adlc/ — silent" "" "$OUT$ERR"
check "case_session_record_inert: no .adlc/ — nothing written" "" "$(ls -A "$PROJ")"
run_hook "$RECORD_CMD" '' "$TOOLKIT"
check "case_session_record_inert: no .adlc/, empty payload — nothing written" "" "$(ls -A "$PROJ")"

for payload in '' 'not json at all' '{"other":"x"}' '[1,2]' '"a string"' '{"session_id":123}' '{"session_id":null}'; do
  next_project shape
  run_hook "$RECORD_CMD" "$payload" "$TOOLKIT"
  check "case_session_record_inert: payload '$payload' — exit 0, silent" "0:" "$RC:$OUT$ERR"
  check "case_session_record_inert: payload '$payload' — one generated-id sidecar" "yes" "$(is_generated)"
  check "case_session_record_inert: payload '$payload' — harness unknown, no path" "unknown:" \
    "$(field "$PROJ/.adlc/.session/$(sidecars)" harness):$(field "$PROJ/.adlc/.session/$(sidecars)" transcript_path)"
done

next_project closed
run_hook "$RECORD_CMD <&-" '' "$TOOLKIT"
check "case_session_record_inert: closed stdin — exit 0, silent" "0:" "$RC:$OUT$ERR"
check "case_session_record_inert: closed stdin — a generated id" "yes" "$(is_generated)"

new_project linked
mkdir -p "$SANDBOX/real-adlc"
ln -s "$SANDBOX/real-adlc" "$PROJ/.adlc"
run_hook "$RECORD_CMD" '{"session_id":"abc"}' "$TOOLKIT"
check "case_session_record_inert: symlinked .adlc — exit 0" "0" "$RC"
check "case_session_record_inert: symlinked .adlc — nothing written" "" "$(ls -A "$SANDBOX/real-adlc")"

next_project linkeddir
mkdir -p "$SANDBOX/real-session"
ln -s "$SANDBOX/real-session" "$PROJ/.adlc/.session"
run_hook "$RECORD_CMD" '{"session_id":"abc"}' "$TOOLKIT"
check "case_session_record_inert: symlinked .adlc/.session — exit 0" "0" "$RC"
check "case_session_record_inert: symlinked .adlc/.session — nothing written" "" "$(ls -A "$SANDBOX/real-session")"

# BR-5: nothing beyond python3 and sh, and without python3 the hook does nothing.
next_project nopython
sut_path=$(command -v "$SUT")
( cd "$PROJ" && printf '{"session_id":"abc"}' | HOME=$HOMEDIR CLAUDE_PLUGIN_ROOT=$TOOLKIT PATH="$SANDBOX/no-such-dir" "$sut_path" -c "$RECORD_CMD" >"$SANDBOX/out" 2>"$SANDBOX/err" )
check "case_session_record_no_python: exit 0" "0" "$?"
check "case_session_record_no_python: silent" "" "$(cat "$SANDBOX/out" "$SANDBOX/err")"
check "case_session_record_no_python: nothing written" "no" "$( [ -e "$PROJ/.adlc/.session" ] && echo yes || echo no)"

# ADR-4: the repo is the hook's working directory, and it can hold anything.
next_project planted
printf 'import os\nopen("planted-ran", "w").close()\nraise SystemExit(7)\n' > "$PROJ/json.py"
run_hook "$RECORD_CMD" '{"session_id":"s1"}' "$TOOLKIT"
check "case_session_record_planted_module: the planted json.py never ran" "no" "$( [ -e "$PROJ/planted-ran" ] && echo yes || echo no)"
check "case_session_record_planted_module: the sidecar is written" "s1" "$(sidecars)"

next_project shadow
run_hook "python3() { echo SHADOWED; }
$RECORD_CMD" '{"session_id":"s1"}' "$TOOLKIT"
check "case_session_record_shadowed_python: the function is not called" "" "$OUT$ERR"
check "case_session_record_shadowed_python: the sidecar is written" "s1" "$(sidecars)"

long_id=$(printf 'a%.0s' 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32)
long_id="$long_id$long_id$long_id$long_id"
next_project longid
run_hook "$RECORD_CMD" "{\"session_id\":\"$long_id\"}" "$TOOLKIT"
check "case_session_record_unsafe_id: 128 characters is kept" "$long_id" "$(sidecars)"
for payload in '{"session_id":"../../etc"}' '{"session_id":"a/b"}' '{"session_id":".gitignore"}' '{"session_id":"."}' '{"session_id":".."}' '{"session_id":"abc\n"}' "{\"session_id\":\"${long_id}a\"}"; do
  next_project unsafe
  run_hook "$RECORD_CMD" "$payload" "$TOOLKIT"
  check "case_session_record_unsafe_id: $payload — exit 0, silent" "0:" "$RC:$OUT$ERR"
  check "case_session_record_unsafe_id: $payload — replaced by a generated id" "yes" "$(is_generated)"
  check "case_session_record_unsafe_id: $payload — .gitignore intact" "*" "$(cat "$PROJ/.adlc/.session/.gitignore")"
  check "case_session_record_unsafe_id: $payload — nothing left the directory" ".adlc" "$(ls -A "$PROJ")"
done

# transcript_path: under $HOME, or empty. The rejected values reach a sidecar with
# the claude marker where one fits, so the rejection is the path rule's, not the table's.
outside="$SANDBOX/outside"
mkdir -p "$outside"
for tp in '/etc/passwd' \
          "NEWHOME/../outside.jsonl" \
          "NEWHOME/a/../b/.claude/projects/s.jsonl" \
          'NEWHOME/.claude/projects/a\nb.jsonl' \
          'NEWHOME/.claude/projects/a\u0007b.jsonl' \
          '.claude/projects/p/s.jsonl' \
          "NEWHOME-sibling/.claude/projects/s.jsonl" \
          "NEWHOME/link/.claude/projects/s.jsonl"; do
  next_project contain
  ln -s "$outside" "$HOMEDIR/link"
  value=$(printf '%s' "$tp" | command sed "s|NEWHOME|$HOMEDIR|")
  run_hook "$RECORD_CMD" "{\"session_id\":\"s1\",\"transcript_path\":\"$value\"}" "$TOOLKIT"
  check "case_session_record_transcript_contained: $tp — recorded empty" "" "$(field "$PROJ/.adlc/.session/s1" transcript_path)"
  check "case_session_record_transcript_contained: $tp — still five lines" "harness session_id transcript_path cwd started_at " "$(keys_of "$PROJ/.adlc/.session/s1")"
done

next_project contained
mkdir -p "$HOMEDIR/real/.claude/projects"
ln -s "$HOMEDIR/real" "$HOMEDIR/inner"
for tp in "$HOMEDIR/inner/.claude/projects/s.jsonl" "$HOMEDIR/.claude/projects/a..b.jsonl"; do
  run_hook "$RECORD_CMD" "{\"session_id\":\"s1\",\"transcript_path\":\"$tp\"}" "$TOOLKIT"
  check "case_session_record_transcript_contained: $tp — recorded" "$tp" "$(field "$PROJ/.adlc/.session/s1" transcript_path)"
done

# With the working directory under $HOME, only the absolute-path rule rejects this one.
next_project relative
HOMEDIR=$PROJ
run_hook "$RECORD_CMD" '{"session_id":"s1","transcript_path":".claude/projects/p/s.jsonl"}' "$TOOLKIT"
check "case_session_record_transcript_contained: a relative path resolving under HOME — recorded empty" "" "$(field "$PROJ/.adlc/.session/s1" transcript_path)"

next_project emptyhome
HOMEDIR=
run_hook "$RECORD_CMD" "{\"session_id\":\"s1\",\"transcript_path\":\"$PROJ/s.jsonl\"}" "$TOOLKIT"
check "case_session_record_transcript_contained: an empty HOME contains nothing" "" "$(field "$PROJ/.adlc/.session/s1" transcript_path)"
check "case_session_record_transcript_contained: an empty HOME still writes the sidecar" "s1" "$(sidecars)"

next_project badcwd
run_hook "$RECORD_CMD" '{"session_id":"s1","cwd":"/x\ny=forged"}' "$TOOLKIT"
check "case_session_record_cwd_clean: a control character falls back to the working directory" \
  "$(cd "$PROJ" && pwd -P)" "$(field "$PROJ/.adlc/.session/s1" cwd)"
check "case_session_record_cwd_clean: still five lines" "harness session_id transcript_path cwd started_at " "$(keys_of "$PROJ/.adlc/.session/s1")"

next_project resume
mkdir -p "$PROJ/.adlc/.session"
SC="$PROJ/.adlc/.session/s1"
printf 'harness=claude\nsession_id=s1\ntranscript_path=\ncwd=/old\nstarted_at=2020-01-02T03:04:05Z\n' > "$SC"
age "$SC" 40
run_hook "$RECORD_CMD" '{"session_id":"s1","cwd":"/new"}' "$TOOLKIT"
check "case_session_record_resume: a re-fire keeps started_at" "2020-01-02T03:04:05Z" "$(field "$SC" started_at)"
check "case_session_record_resume: a re-fire rewrites the rest" "/new" "$(field "$SC" cwd)"
check "case_session_record_resume: one file, not two" "s1" "$(sidecars)"
run_hook "$RECORD_CMD" '{"session_id":"s2"}' "$TOOLKIT"
check "case_session_record_resume: two sessions, two files" "s1${LF}s2" "$(sidecars)"
printf 'started_at=yesterday\n' > "$SC"
run_hook "$RECORD_CMD" '{"session_id":"s1"}' "$TOOLKIT"
check "case_session_record_resume: an unreadable started_at is not carried over" "1" \
  "$(field "$SC" started_at | command grep -cE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$')"

next_project stublike
mkdir -p "$PROJ/.adlc/.session"
printf 'harness=claude\nsession_id=s1\n' > "$PROJ/.adlc/.session/s1"
run_hook "$RECORD_CMD" '{"session_id":"s1"}' "$TOOLKIT"
check "case_session_record_resume: a stub sidecar gains the full contract" "harness session_id transcript_path cwd started_at " "$(keys_of "$PROJ/.adlc/.session/s1")"

next_project linkedsidecar
mkdir -p "$PROJ/.adlc/.session"
printf 'started_at=2020-01-02T03:04:05Z\n' > "$SANDBOX/target"
ln -s "$SANDBOX/target" "$PROJ/.adlc/.session/s1"
run_hook "$RECORD_CMD" '{"session_id":"s1"}' "$TOOLKIT"
check "case_session_record_resume: a symlinked sidecar's target is untouched" "started_at=2020-01-02T03:04:05Z" "$(cat "$SANDBOX/target")"
check "case_session_record_resume: a symlinked sidecar is replaced by a file" "no" "$( [ -L "$PROJ/.adlc/.session/s1" ] && echo yes || echo no)"
check "case_session_record_resume: nothing is read through the symlink" "no" "$( [ "$(field "$PROJ/.adlc/.session/s1" started_at)" = "2020-01-02T03:04:05Z" ] && echo yes || echo no)"

next_project prunes
DIR="$PROJ/.adlc/.session"
mkdir -p "$DIR/keepdir"
printf '*\n' > "$DIR/.gitignore"
printf 'x\n' > "$DIR/old"
printf 'x\n' > "$DIR/recent"
printf 'x\n' > "$DIR/.tmp-1"
printf 'x\n' > "$DIR/.stranger"
age "$DIR/old" 31
age "$DIR/recent" 29
age "$DIR/.gitignore" 31
age "$DIR/.tmp-1" 31
age "$DIR/.stranger" 31
age "$DIR/keepdir" 31
run_hook "$RECORD_CMD" '{"session_id":"s1"}' "$TOOLKIT"
check "case_session_record_prunes: exit 0, silent" "0:" "$RC:$OUT$ERR"
check "case_session_record_prunes: a 31-day-old sidecar is gone" "no" "$( [ -e "$DIR/old" ] && echo yes || echo no)"
check "case_session_record_prunes: a 29-day-old sidecar is kept" "yes" "$( [ -e "$DIR/recent" ] && echo yes || echo no)"
check "case_session_record_prunes: .gitignore is never pruned" "*" "$(cat "$DIR/.gitignore" 2>/dev/null)"
check "case_session_record_prunes: a stale temporary file is gone" "no" "$( [ -e "$DIR/.tmp-1" ] && echo yes || echo no)"
check "case_session_record_prunes: a name the writer never uses is kept" "yes" "$( [ -e "$DIR/.stranger" ] && echo yes || echo no)"
check "case_session_record_prunes: a directory is kept" "yes" "$( [ -d "$DIR/keepdir" ] && echo yes || echo no)"
check "case_session_record_prunes: this run's sidecar is written" "yes" "$( [ -e "$DIR/s1" ] && echo yes || echo no)"

next_project sweepalways
DIR="$PROJ/.adlc/.session"
mkdir -p "$DIR"
printf 'x\n' > "$DIR/old"
age "$DIR/old" 31
run_hook "$RECORD_CMD" 'not json' "$TOOLKIT"
check "case_session_record_prunes: a run with no usable payload still sweeps" "no" "$( [ -e "$DIR/old" ] && echo yes || echo no)"

next_project harnessarg
tp="$HOMEDIR/.claude/projects/p/s.jsonl"
run_hook "$RECORD_CMD --harness codex --field session_id=sid" "{\"sid\":\"T-9\",\"session_id\":\"other\",\"cwd\":\"/not/read\",\"transcript_path\":\"$tp\"}" "$TOOLKIT"
SC="$PROJ/.adlc/.session/T-9"
check "case_session_record_harness_arg: exit 0" "0" "$RC"
check "case_session_record_harness_arg: harness from the arguments" "codex" "$(field "$SC" harness)"
check "case_session_record_harness_arg: the id from the named key" "T-9" "$(field "$SC" session_id)"
check "case_session_record_harness_arg: an item with no --field is not read (transcript_path)" "" "$(field "$SC" transcript_path)"
check "case_session_record_harness_arg: an item with no --field is not read (cwd)" "$(cd "$PROJ" && pwd -P)" "$(field "$SC" cwd)"

next_project allfields
tp="$HOMEDIR/x/s.jsonl"
run_hook "$RECORD_CMD --harness gemini --field session_id=sid --field cwd=dir --field transcript_path=log" "{\"sid\":\"T-9\",\"dir\":\"/work\",\"log\":\"$tp\"}" "$TOOLKIT"
SC="$PROJ/.adlc/.session/T-9"
check "case_session_record_harness_arg: every named item is read" "gemini:T-9:$tp:/work" \
  "$(field "$SC" harness):$(field "$SC" session_id):$(field "$SC" transcript_path):$(field "$SC" cwd)"

next_project noid
run_hook "$RECORD_CMD --harness cursor" '{"session_id":"not-named"}' "$TOOLKIT"
check "case_session_record_harness_arg: no --field session_id — a generated id" "yes" "$(is_generated)"
check "case_session_record_harness_arg: a harness in the enum needs no table row" "cursor" "$(field "$PROJ/.adlc/.session/$(sidecars)" harness)"

for bad in fake CLAUDE 'a/b' '../x' '""'; do
  next_project badharness
  run_hook "$RECORD_CMD --harness $bad --field session_id=sid" '{"sid":"T-9"}' "$TOOLKIT"
  check "case_session_record_harness_arg: invalid harness $bad records unknown" "unknown" "$(field "$PROJ/.adlc/.session/T-9" harness)"
done

next_project dangling
run_hook "$RECORD_CMD --field session_id=sid --harness" '{"session_id":"s1","sid":"s2"}' "$TOOLKIT"
check "case_session_record_harness_arg: a dangling --harness stays silent, exit 0" "0:" "$RC:$OUT$ERR"
check "case_session_record_harness_arg: without a harness name --field is ignored" "s1" "$(sidecars)"

# OQ-1: the shared render's other readers fail closed until a payload is captured.
next_project unknownpayload
tp="$HOMEDIR/elsewhere/s.jsonl"
run_hook "$RECORD_CMD" "{\"session_id\":\"s1\",\"transcript_path\":\"$tp\",\"cwd\":\"/w\"}" "$TOOLKIT"
SC="$PROJ/.adlc/.session/s1"
check "case_session_record_detection: no table row matches — unknown" "unknown" "$(field "$SC" harness)"
check "case_session_record_detection: an unknown payload reads the claude keys" "s1:$tp:/w" \
  "$(field "$SC" session_id):$(field "$SC" transcript_path):$(field "$SC" cwd)"
next_project markeronly
run_hook "$RECORD_CMD" "{\"transcript_path\":\"$HOMEDIR/.claude/projects/p/s.jsonl\"}" "$TOOLKIT"
check "case_session_record_detection: a row needs the id as well as the marker" "unknown" "$(field "$PROJ/.adlc/.session/$(sidecars)" harness)"

# BR-5: a writer that never closes stdin. It stays open past the wall-clock bound the
# case asserts, so a pass proves the hook's own deadline ended the read, not EOF.
# The cap: past 1 MiB the read stops, the text is not JSON, and the id is generated.
next_project deadline
mkfifo "$SANDBOX/held"
sleep 8 >"$SANDBOX/held" 2>/dev/null &
holder=$!
start=$(date +%s)
run_hook_from "$RECORD_CMD" "$SANDBOX/held"
elapsed=$(($(date +%s) - start))
kill "$holder" 2>/dev/null
wait "$holder" 2>/dev/null
check "case_session_record_timing: exit 0, silent" "0:" "$RC:$OUT$ERR"
if [ "$elapsed" -lt 8 ]; then pass "case_session_record_timing: an open stdin ended in ${elapsed}s, inside timeout_s"
else fail "case_session_record_timing: an open stdin took ${elapsed}s"; fi
check "case_session_record_timing: an open stdin still leaves a sidecar" "yes" "$(is_generated)"

next_project oversize
python3 -c 'import sys
sys.stdout.write("{\"session_id\":\"s1\",\"pad\":\"" + "x" * (2 * 1024 * 1024) + "\"}")' > "$SANDBOX/big.json"
run_hook_from "$RECORD_CMD" "$SANDBOX/big.json"
check "case_session_record_stdin_cap: exit 0, silent" "0:" "$RC:$OUT$ERR"
check "case_session_record_stdin_cap: an oversized payload is not parsed" "yes" "$(is_generated)"

# --- a python3 that fails ------------------------------------------------------
new_project pyfail
mkdir -p "$PROJ/.adlc" "$SANDBOX/badpy"
printf '#!/bin/sh\nexit 7\n' > "$SANDBOX/badpy/python3"
chmod +x "$SANDBOX/badpy/python3"
SR_PATH=$PATH
PATH="$SANDBOX/badpy:$PATH"
run_hook "$RECORD_CMD" '{"session_id":"abc"}' "$TOOLKIT"
PATH=$SR_PATH
check "case_session_record_python_fails: exit 0" "0" "$RC"
check "case_session_record_python_fails: silent" "" "$OUT$ERR"

# --- a committed .gitignore in the session directory -----------------------------
new_project ignorer
mkdir -p "$PROJ/.adlc/.session"
printf '!*\n' > "$PROJ/.adlc/.session/.gitignore"
run_hook "$RECORD_CMD" '{"session_id":"abc"}' "$TOOLKIT"
check "case_session_record_gitignore_restored: a preseeded file is replaced" "*" "$(cat "$PROJ/.adlc/.session/.gitignore" 2>/dev/null)"

# --- the source spelling -----------------------------------------------------
for f in "$SANDBOX"/*.cmd; do
  n=$(command grep -c '^if \[ -f \.adlc/partials/[a-z-]*\.sh \]; then \. \.adlc/partials/[a-z-]*\.sh; else \. "\$ADLC_TOOLKIT_ROOT/partials/[a-z-]*\.sh"; fi$' "$f")
  check "case_rendered_sources_guarded: $(basename "$f") has one canonical source line" "1" "$n"
done

# --- the Copilot render (REQ-656 BR-5) ----------------------------------------
COPILOT="$TOOLKIT/harness/copilot/rendered/adlc.json"
python3 - "$COPILOT" "$SANDBOX" <<'PY' || { echo "hooks.test.sh: could not read the copilot render" >&2; exit 1; }
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
assert doc["version"] == 1
for event, tag in (("sessionStart", "cs"), ("subagentStart", "ca")):
    for hook in doc["hooks"][event]:
        name = "ethos" if "adlc_ethos_inject" in hook["bash"] else "record"
        with open("%s/%s-%s.cop" % (sys.argv[2], tag, name), "w", encoding="utf-8") as fh:
            fh.write(hook["bash"])
PY
COP_ETHOS=$(cat "$SANDBOX/cs-ethos.cop")
COP_RECORD=$(cat "$SANDBOX/cs-record.cop")
check "case_copilot_subagent_same_command: both events carry one ethos-inject" \
  "$COP_ETHOS" "$(cat "$SANDBOX/ca-ethos.cop")"

new_project copilot
mkdir -p "$PROJ/.adlc"
printf 'He said "stop" \\ then\ttabbed\n\nlast line, no newline \001' > "$PROJ/.adlc/ETHOS.md"
run_hook "$COP_ETHOS" "" "$TOOLKIT"
check "case_copilot_ethos_json: exit 0" "0" "$RC"
check "case_copilot_ethos_json: stderr empty" "" "$ERR"
printf '%s' "$OUT" > "$SANDBOX/cop.out"
PARSED=$(python3 - "$SANDBOX/cop.out" "$PROJ/.adlc/ETHOS.md" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
want = open(sys.argv[2], encoding="utf-8").read().replace("\x01", "")
print("ok" if list(doc) == ["additionalContext"] and
      doc["additionalContext"].rstrip("\n") == want.rstrip("\n") else "differs")
PY
)
check "case_copilot_ethos_json: one object, additionalContext is the file" "ok" "$PARSED"

new_project copilot-noethos
mkdir -p "$PROJ/.adlc"
run_hook "$COP_ETHOS" "" "$TOOLKIT"
check "case_copilot_ethos_absent: exit 0" "0" "$RC"
check "case_copilot_ethos_absent: prints nothing" "" "$OUT$ERR"

new_project copilot-bad-key
mkdir -p "$PROJ/.adlc"
printf 'x\n' > "$PROJ/.adlc/ETHOS.md"
run_hook "$(printf '%s' "$COP_ETHOS" | sed 's/additionalContext/badkey-/')" "" "$TOOLKIT"
check "case_copilot_ethos_bad_key: a key outside the charset prints nothing" "" "$OUT"

new_project copilot-record
mkdir -p "$PROJ/.adlc"
run_hook "$COP_RECORD" '{"session_id":"cop-1"}' "$TOOLKIT"
# Every Copilot field is `unsupported` until REQ-660 OQ-1, so the render names no
# --field: the harness is recorded, the unverified id is not read, one is generated.
cop_sidecar=$(command find "$PROJ/.adlc/.session" -maxdepth 1 -type f ! -name '.*' 2>/dev/null)
check "case_copilot_record_harness: --harness copilot reaches the partial" "harness=copilot" "$(sed -n 1p "$cop_sidecar" 2>/dev/null)"
check "case_copilot_record_harness: no --field, so the id is generated" "gen-" "$(sed -n 's/^session_id=\(gen-\).*/\1/p' "$cop_sidecar" 2>/dev/null)"
check "case_copilot_record_harness: no --field, so no path is read" "transcript_path=" "$(sed -n 3p "$cop_sidecar" 2>/dev/null)"

mkdir -p "$SANDBOX/bare-copilot" && cd "$SANDBOX/bare-copilot" || exit 1
for cmd in "$COP_ETHOS" "$COP_RECORD"; do
  OUT=$(HOME="$SANDBOX/no-home" "$SUT" -c "$cmd" </dev/null 2>&1); RC=$?
  check "case_copilot_partial_absent: exit 0 with no partial at either level" "0" "$RC"
  check "case_copilot_partial_absent: silent" "" "$OUT"
done
cd "$SANDBOX" || exit 1

echo "hooks.test.sh: $CASES cases executed"
if [ "$CASES" -lt 160 ]; then
  echo "hooks.test.sh: FAIL — expected at least 160 cases, ran $CASES ($SUT)"
  exit 1
fi
if [ "$FAILS" -eq 0 ]; then
  echo "hooks.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "hooks.test.sh: $FAILS FAILURE(S) ($SUT)"
exit 1
