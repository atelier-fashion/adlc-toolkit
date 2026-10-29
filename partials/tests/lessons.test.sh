#!/bin/sh
# partials/tests/lessons.test.sh — REQ-647 BR-12: the LessonSet wrapper, end to end.
#
# tools/adlc/tests/test_lessons.py covers every selection rule of the engine. This
# harness proves the shell half: that `adlc_lessons` runs the installed engine
# under bash, zsh, /bin/sh and dash, hands its stdout and return code through, and
# turns every way it cannot run the engine into rc 2 with one
# `lessons: unavailable — <reason>` line (retrieval never halts a pipeline).
#
#   passthrough            — wrapper stdout and rc are byte-identical to the engine run directly
#   select_step0           — the log line names the fixture lessons, rc 0
#   select_task_state      — --state-out writes lessons.tasks.TASK-001 and keeps other keys
#   log_line               — log-line reads the recorded set back
#   ack_check              — an unacknowledged applicable lesson is listed
#   engine_rc2             — an engine usage error passes through as rc 2 and its one line
#   usage                  — no arguments                              -> rc 2, unavailable
#   engine_not_found       — HOME has no .claude/skills, ADLC_TOOLKIT_ROOT unset -> rc 2
#   engine_not_found_root_set — ADLC_TOOLKIT_ROOT names a root with no engine -> rc 2
#   relative_root          — ADLC_TOOLKIT_ROOT is relative             -> rc 2
#   engine_via_toolkit_root — no .claude/skills at all, ADLC_TOOLKIT_ROOT is the checkout -> rc 0
#   resolver_undefined     — `_adlc_forge_python` is not defined       -> rc 2
#   rc_outside_contract    — the interpreter exits 7                    -> rc 2, `lessons.py exited 7`
#   set_u_home_unset       — sourced by a `set -u` shell with HOME and ADLC_TOOLKIT_ROOT unset:
#                            no abort, and the call is rc 2
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL). HOME is pointed at a
# sandbox whose ~/.claude/skills is THIS toolkit checkout, so the installed engine the
# wrapper finds is the one under test.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
TOOLKIT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}

FAILS=0
CASES=0
pass() { echo "PASS: $1"; CASES=$((CASES + 1)); }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-lessons.XXXXXX") || { echo "lessons.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "lessons.test.sh: sandbox path invalid" >&2; exit 1; }
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

mkdir -p "$SANDBOX/home/.claude" && ln -s "$TOOLKIT" "$SANDBOX/home/.claude/skills"
HOME="$SANDBOX/home"; export HOME
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE ADLC_TOOLKIT_ROOT CLAUDE_PLUGIN_ROOT

. "$PARTIALS/forge.sh"
. "$PARTIALS/lessons.sh"

# A fixture project: two lessons, one spec, a git repo for ack-check.
P="$SANDBOX/project"
mkdir -p "$P/.adlc/knowledge/lessons" "$P/.adlc/specs/REQ-900-fixture"
printf '%s\n' '---' 'id: LESSON-100' 'title: "partials rule"' 'component: "adlc/partials"' 'domain: "adlc"' 'created: 2026-01-01' '---' '' '## Lesson' '' 'rule' '' '## Applies When' '' '- always' > "$P/.adlc/knowledge/lessons/LESSON-100-a.md"
printf '%s\n' '---' 'id: LESSON-101' 'title: "forge rule"' 'component: "adlc/partials/forge"' 'domain: "adlc"' 'created: 2026-03-01' '---' '' '## Lesson' '' 'rule' > "$P/.adlc/knowledge/lessons/LESSON-101-b.md"
SPEC="$P/.adlc/specs/REQ-900-fixture/requirement.md"
printf '%s\n' '---' 'id: REQ-900' 'title: "fixture"' 'component: "adlc/partials"' 'domain: "adlc"' 'created: 2026-02-01' '---' > "$SPEC"
STATE="$P/.adlc/specs/REQ-900-fixture/pipeline-state.json"
printf '%s\n' '{"req": "REQ-900", "currentPhase": 4}' > "$STATE"
git -C "$P" init -q -b main . && git -C "$P" config user.email t@t && git -C "$P" config user.name t
git -C "$P" add -A && git -C "$P" commit -qm base && git -C "$P" checkout -qb feat
git -C "$P" commit -q --allow-empty -m 'feat: x' -m 'Lessons: LESSON-100'

# --- passthrough --------------------------------------------------------------
want=$(command "$(_adlc_forge_python)" -E "$TOOLKIT/tools/adlc/lessons.py" select --set step0 --root "$P" --spec "$SPEC" --retrieved-at 2026-10-29T00:00:00Z); want_rc=$?
got=$(adlc_lessons select --set step0 --root "$P" --spec "$SPEC" --retrieved-at 2026-10-29T00:00:00Z); got_rc=$?
check "passthrough: rc" "$want_rc" "$got_rc"
check "passthrough: stdout identical" "yes" "$([ "$want" = "$got" ] && echo yes || echo no)"

# --- select_step0 -------------------------------------------------------------
out=$(adlc_lessons select --set step0 --root "$P" --spec "$SPEC"); rc=$?
check "select_step0: rc" 0 "$rc"
check "select_step0: log line" "Lessons loaded (step0): LESSON-100 [newer-than-spec: LESSON-101]" "$(printf '%s\n' "$out" | sed -n 1p)"
check "select_step0: loaded text present" "1" "$(printf '%s\n' "$out" | grep -c '^### LESSON-100 — partials rule')"

# --- select_task_state --------------------------------------------------------
out=$(adlc_lessons select --set task --task-id TASK-001 --root "$P" --spec "$SPEC" --component adlc/partials/forge --state-out "$STATE" 2>/dev/null); rc=$?
check "select_task_state: rc" 0 "$rc"
check "select_task_state: task set recorded" "1" "$(grep -c '"TASK-001"' "$STATE")"
check "select_task_state: other keys kept" "1" "$(grep -c '"currentPhase": 4' "$STATE")"
check "select_task_state: no loaded text in state" "0" "$(grep -c '"text"' "$STATE")"

# --- log_line -----------------------------------------------------------------
out=$(adlc_lessons log-line --state "$STATE" --key tasks.TASK-001 --root "$P"); rc=$?
check "log_line: rc" 0 "$rc"
check "log_line: names the set" "Lessons loaded (task TASK-001): LESSON-100 [newer-than-spec: LESSON-101]" "$out"

# --- ack_check ----------------------------------------------------------------
adlc_lessons select --set phase5 --root "$P" --spec "$SPEC" --component adlc/partials/forge --state-out "$STATE" >/dev/null 2>&1
out=$(adlc_lessons ack-check --state "$STATE" --root "$P" --worktree "$P" --base main); rc=$?
check "ack_check: rc" 0 "$rc"
check "ack_check: the unacknowledged lesson is listed" "Applicable lesson not acknowledged: LESSON-101 — forge rule" "$out"

# --- engine_rc2 ---------------------------------------------------------------
out=$(adlc_lessons select --set task --root "$P" --spec "$SPEC" 2>/dev/null); rc=$?
check "engine_rc2: rc" 2 "$rc"
check "engine_rc2: one contract line" "lessons: unavailable — --set task needs --task-id TASK-nnn" "$out"

# --- usage --------------------------------------------------------------------
out=$(adlc_lessons 2>/dev/null); rc=$?
check "usage: rc" 2 "$rc"
check "usage: unavailable line" "1" "$(printf '%s\n' "$out" | grep -c '^lessons: unavailable — usage')"

# --- engine_not_found ---------------------------------------------------------
mkdir -p "$SANDBOX/empty-home"
out=$(HOME="$SANDBOX/empty-home"; export HOME; adlc_lessons select --set step0 --root "$P" --spec "$SPEC" 2>/dev/null); rc=$?
check "engine_not_found: rc" 2 "$rc"
check "engine_not_found: line" "lessons: unavailable — lessons.py not found in the installed toolkit" "$out"

# --- engine_not_found_root_set ------------------------------------------------
out=$(ADLC_TOOLKIT_ROOT="$SANDBOX/no-such-root"; export ADLC_TOOLKIT_ROOT; adlc_lessons select --set step0 --root "$P" --spec "$SPEC" 2>/dev/null); rc=$?
check "engine_not_found_root_set: rc" 2 "$rc"
check "engine_not_found_root_set: line" "lessons: unavailable — lessons.py not found in the installed toolkit" "$out"

# --- relative_root ------------------------------------------------------------
out=$(ADLC_TOOLKIT_ROOT="relative/root"; export ADLC_TOOLKIT_ROOT; adlc_lessons select --set step0 --root "$P" --spec "$SPEC" 2>/dev/null); rc=$?
check "relative_root: rc" 2 "$rc"
check "relative_root: line" "lessons: unavailable — ADLC_TOOLKIT_ROOT is not an absolute path" "$out"

# --- engine_via_toolkit_root --------------------------------------------------
out=$(HOME="$SANDBOX/empty-home"; ADLC_TOOLKIT_ROOT="$TOOLKIT"; export HOME ADLC_TOOLKIT_ROOT; adlc_lessons select --set step0 --root "$P" --spec "$SPEC"); rc=$?
check "engine_via_toolkit_root: rc" 0 "$rc"
check "engine_via_toolkit_root: log line" "Lessons loaded (step0): LESSON-100 [newer-than-spec: LESSON-101]" "$(printf '%s\n' "$out" | sed -n 1p)"

# --- resolver_undefined -------------------------------------------------------
out=$(unset -f _adlc_forge_python; adlc_lessons select --set step0 --root "$P" --spec "$SPEC" 2>/dev/null); rc=$?
check "resolver_undefined: rc" 2 "$rc"
check "resolver_undefined: line" "lessons: unavailable — interpreter resolver _adlc_forge_python is not defined" "$out"

# --- rc_outside_contract ------------------------------------------------------
STUB="$SANDBOX/stub-python"
printf '%s\n' '#!/bin/sh' 'exit 7' > "$STUB" && chmod +x "$STUB"
out=$(_adlc_forge_python() { printf '%s\n' "$STUB"; }; adlc_lessons select --set step0 --root "$P" --spec "$SPEC" 2>/dev/null); rc=$?
check "rc_outside_contract: rc" 2 "$rc"
check "rc_outside_contract: line" "lessons: unavailable — lessons.py exited 7" "$out"

# --- set_u_home_unset ---------------------------------------------------------
# Native zsh sets HOME itself when it is unset, so zsh runs in sh emulation here.
SETU="$SANDBOX/setu.sh"
printf '%s\n' 'set -u' ". '$PARTIALS/lessons.sh'" 'adlc_lessons select --set step0 --root "$1" --spec "$2"; printf "rc=%s\n" "$?"' > "$SETU"
case "$SUT" in
  *zsh) setu_out=$(cd "$SANDBOX" && env -u HOME -u ADLC_TOOLKIT_ROOT "$SUT" --emulate sh "$SETU" "$P" "$SPEC" 2>/dev/null) ;;
  *) setu_out=$(cd "$SANDBOX" && env -u HOME -u ADLC_TOOLKIT_ROOT "$SUT" "$SETU" "$P" "$SPEC" 2>/dev/null) ;;
esac
check "set_u_home_unset: sourced and called without aborting" "rc=2" "$(printf '%s\n' "$setu_out" | tail -n 1)"
check "set_u_home_unset: the call is an unavailable line" "1" "$(printf '%s\n' "$setu_out" | grep -c '^lessons: unavailable — ')"

# --- summary ------------------------------------------------------------------
# Case-count floor: a harness that ran nothing must not read as a pass.
echo "lessons.test.sh: $CASES cases executed"
if [ "$CASES" -lt 30 ]; then
  echo "lessons.test.sh: FAIL — expected at least 30 cases, ran $CASES ($SUT)"
  exit 1
fi
if [ "$FAILS" -eq 0 ]; then
  echo "lessons.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "lessons.test.sh: $FAILS FAILURE(S) ($SUT)"
exit 1
