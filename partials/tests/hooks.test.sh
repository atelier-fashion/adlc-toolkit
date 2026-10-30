#!/bin/sh
# partials/tests/hooks.test.sh — REQ-657 BR-10, BR-16, AC-8, AC-14.
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
#   case_session_record_writes: a claude-shaped payload writes
#       .adlc/.session/<id> (harness=claude, session_id=<id>), mode 600, with a
#       self-ignoring .gitignore, so `git status` shows nothing; stdout empty.
#   case_session_record_inert (benign path): no .adlc/, an empty payload, a
#       non-JSON payload and an id carrying `..` or `/` write nothing, exit 0.
#   case_session_record_harness_arg: `--harness codex --field session_id=sid`
#       records harness=codex from the payload's `sid` key.
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
pass() { echo "PASS: $1"; CASES=$((CASES + 1)); }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
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
new_project record
mkdir -p "$PROJ/.adlc"
git -C "$PROJ" init -q 2>/dev/null
run_hook "$RECORD_CMD" '{"session_id":"sess-123_A","transcript_path":"/x/.claude/projects/p/s.jsonl","cwd":"/x"}' "$TOOLKIT"
check "case_session_record_writes: exit 0" "0" "$RC"
check "case_session_record_writes: stdout empty" "" "$OUT"
check "case_session_record_writes: sidecar content" "harness=claude
session_id=sess-123_A" "$(cat "$PROJ/.adlc/.session/sess-123_A" 2>/dev/null)"
perm=$(ls -l "$PROJ/.adlc/.session/sess-123_A" 2>/dev/null | cut -c1-10)
check "case_session_record_writes: mode 600" "-rw-------" "$perm"
check "case_session_record_writes: the directory ignores itself" "*" "$(cat "$PROJ/.adlc/.session/.gitignore" 2>/dev/null)"
check "case_session_record_writes: git status shows nothing" "" "$(git -C "$PROJ" status --porcelain 2>/dev/null)"

new_project inert
run_hook "$RECORD_CMD" '{"session_id":"abc"}' "$TOOLKIT"
check "case_session_record_inert: no .adlc/ — exit 0" "0" "$RC"
check "case_session_record_inert: no .adlc/ — nothing written" "" "$(ls -A "$PROJ")"
mkdir -p "$PROJ/.adlc"
for payload in '' 'not json at all' '{"session_id":"../../etc"}' '{"session_id":"a/b"}' '{"other":"x"}'; do
  run_hook "$RECORD_CMD" "$payload" "$TOOLKIT"
  check "case_session_record_inert: payload '$payload' — exit 0, silent" "0:" "$RC:$OUT"
  check "case_session_record_inert: payload '$payload' — nothing written" "no" "$( [ -e "$PROJ/.adlc/.session" ] && echo yes || echo no)"
done

new_project harnessarg
mkdir -p "$PROJ/.adlc"
run_hook "$RECORD_CMD --harness codex --field session_id=sid" '{"sid":"T-9","session_id":"other"}' "$TOOLKIT"
check "case_session_record_harness_arg: exit 0" "0" "$RC"
check "case_session_record_harness_arg: harness and key from the arguments" "harness=codex
session_id=T-9" "$(cat "$PROJ/.adlc/.session/T-9" 2>/dev/null)"

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
check "case_copilot_record_harness: --harness copilot reaches the partial" "harness=copilot
session_id=cop-1" "$(cat "$PROJ/.adlc/.session/cop-1" 2>/dev/null)"

mkdir -p "$SANDBOX/bare-copilot" && cd "$SANDBOX/bare-copilot" || exit 1
for cmd in "$COP_ETHOS" "$COP_RECORD"; do
  OUT=$(HOME="$SANDBOX/no-home" "$SUT" -c "$cmd" </dev/null 2>&1); RC=$?
  check "case_copilot_partial_absent: exit 0 with no partial at either level" "0" "$RC"
  check "case_copilot_partial_absent: silent" "" "$OUT"
done
cd "$SANDBOX" || exit 1

echo "hooks.test.sh: $CASES cases executed"
if [ "$CASES" -lt 42 ]; then
  echo "hooks.test.sh: FAIL — expected at least 42 cases, ran $CASES ($SUT)"
  exit 1
fi
if [ "$FAILS" -eq 0 ]; then
  echo "hooks.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "hooks.test.sh: $FAILS FAILURE(S) ($SUT)"
exit 1
