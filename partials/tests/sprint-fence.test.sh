#!/bin/sh
# partials/tests/sprint-fence.test.sh — REQ-669 ADR-1, ADR-6: /sprint Step 0's
# workflow-engine fence, the one that prints SCRIPT_PATH and AGENT_NAMESPACE.
#
# The fence is EXTRACTED from sprint/SKILL.md (the one shell fence that prints
# `SCRIPT_PATH=`) and run as Claude Code runs it, under the shell being tested:
#   - plugin route: `${CLAUDE_PLUGIN_ROOT}` textually replaced by a plugin path,
#     as the loader does before the fence runs (verification.md row 1);
#   - symlink route: the token left as written, so it expands empty, with
#     ~/.claude/skills a symlink to a toolkit clone.
# CLAUDE_PLUGIN_ROOT is never in the environment; HOME is a sandbox.
#
# Cases:
#   plugin_no_vendored        — the plugin's engine, AGENT_NAMESPACE=adlc:
#   plugin_vendored_current   — a vendored engine that has agentTypeFor wins
#   plugin_vendored_stale     — a vendored engine without agentTypeFor (pre-REQ-669:
#                               it would dispatch bare names that run as generic
#                               agents) is passed over for the plugin's, with ONE
#                               warning line that names /template-drift
#   plugin_stale_no_toolkit   — the same with no plugin copy: SCRIPT_PATH=missing,
#                               so /sprint falls back to legacy rather than run it
#   symlink_vendored_stale    — the benign path: on the symlink route bare names are
#                               right, so the stale vendored engine still wins, with
#                               no warning, and AGENT_NAMESPACE= (empty)
#   symlink_no_vendored       — the clone's engine through ~/.claude/skills
#   neither                   — SCRIPT_PATH=missing
# Every run: exit 0, empty stderr, and stdout is exactly the expected lines.
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL):
#   ADLC_TEST_SHELL=dash sh partials/tests/sprint-fence.test.sh
# or, for bash, zsh, /bin/sh and dash in turn:  sh partials/tests/run.sh
#
# Exits 0 iff every check passes and the executed-case count clears its floor.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
TOOLKIT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}
SKILL="$TOOLKIT/sprint/SKILL.md"
ENGINE="$TOOLKIT/workflows/adlc-sprint.workflow.js"

FAILS=0
CASES=0
pass() { echo "PASS: $1"; CASES=$((CASES + 1)); }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
check() { # check <desc> <expected> <actual> — compared raw, printed scrubbed
  if [ "$2" = "$3" ]; then pass "$1 (= $(scrub "$3"))"; else fail "$1 (expected '$(scrub "$2")', got '$(scrub "$3")')"; fi
}

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-sprintfence.XXXXXX") || { echo "sprint-fence.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "sprint-fence.test.sh: sandbox path invalid" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-sprintfence.*) ;;
  *) echo "sprint-fence.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
trap 'rm -rf "$SANDBOX"' EXIT INT TERM
scrub() { printf '%s' "$1" | sed "s#$SANDBOX#<sandbox>#g"; }
unset CLAUDE_PLUGIN_ROOT ADLC_TOOLKIT_ROOT

# ===========================================================================
# 1. Extraction: the one shell fence in sprint/SKILL.md that prints SCRIPT_PATH=.
# ===========================================================================
# Leading indentation is dropped (the fence sits in a list item). More or fewer
# than one such fence is a FAIL, never a skip: a moved fence must not pass vacuously.
FENCE="$SANDBOX/fence.sh"
awk '
  { t = $0; sub(/^[ \t]+/, "", t) }
  !inf && t ~ /^```(sh|bash|shell)[ \t]*$/ { inf = 1; buf = ""; next }
  inf && t ~ /^```[ \t]*$/ { inf = 0; if (index(buf, "SCRIPT_PATH=")) { body = buf; n++ }; next }
  inf { buf = buf t "\n" }
  END { printf "%s", body; exit (n == 1 ? 0 : 1) }' "$SKILL" > "$FENCE"
n_rc=$?
check "extraction: exactly one SCRIPT_PATH fence in sprint/SKILL.md" "0" "$n_rc"
check "extraction: the fence carries the root line" "1" "$(command grep -c '^ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; ' "$FENCE")"
check "extraction: the fence reads the namespace off the substituted token" "1" "$(command grep -c '^sprint_plugin_root="${CLAUDE_PLUGIN_ROOT}"$' "$FENCE")"

# ===========================================================================
# 2. The trees
# ===========================================================================
# A plugin copy and a symlink-install clone: each holds partials/ (the root line's
# arm-2 test) and the current engine. A stale engine is the current one with every
# agentTypeFor line removed, which is what a pre-REQ-669 vendored copy looks like
# to the fence.
PLUGIN="$SANDBOX/plugins/cache/adlc-toolkit/adlc/9.9.9"
CLONE="$SANDBOX/clone"
for d in "$PLUGIN" "$CLONE"; do
  mkdir -p "$d/partials" "$d/workflows" && cp "$ENGINE" "$d/workflows/adlc-sprint.workflow.js" || exit 1
done
STALE="$SANDBOX/stale.workflow.js"
command grep -v agentTypeFor "$ENGINE" > "$STALE"
check "trees: the current engine has agentTypeFor" "yes" "$(command grep -q agentTypeFor "$ENGINE" && echo yes || echo no)"
check "trees: the stale engine has none" "no" "$(command grep -q agentTypeFor "$STALE" && echo yes || echo no)"
NOPLUGIN="$SANDBOX/plugins/cache/adlc-toolkit/adlc/0.0.1"
mkdir -p "$NOPLUGIN/partials"

HOME_PLUGIN="$SANDBOX/home-plugin"     # plugin-only machine: no ~/.claude/skills
HOME_SYMLINK="$SANDBOX/home-symlink"   # symlink install
HOME_NONE="$SANDBOX/home-none"
mkdir -p "$HOME_PLUGIN/.claude" "$HOME_SYMLINK/.claude" "$HOME_NONE/.claude"
ln -s "$CLONE" "$HOME_SYMLINK/.claude/skills"

# ===========================================================================
# 3. Running the fence
# ===========================================================================
# run_fence <run> <plugin-root|-> <home> <vendored: none|current|stale> — the fence
# under $SUT from a fresh project dir. `-` leaves the token unsubstituted.
run_fence() {
  rf_work="$SANDBOX/work-$1"
  mkdir -p "$rf_work"
  case $4 in
    current) mkdir -p "$rf_work/.adlc/workflows" && cp "$ENGINE" "$rf_work/.adlc/workflows/adlc-sprint.workflow.js" ;;
    stale) mkdir -p "$rf_work/.adlc/workflows" && cp "$STALE" "$rf_work/.adlc/workflows/adlc-sprint.workflow.js" ;;
  esac
  if [ "$2" = "-" ]; then
    cp "$FENCE" "$SANDBOX/run-$1.sh"
  else
    sed "s#\${CLAUDE_PLUGIN_ROOT}#$2#g" "$FENCE" > "$SANDBOX/run-$1.sh"
  fi
  ( cd "$rf_work" && HOME=$3 && export HOME && exec "$SUT" "$SANDBOX/run-$1.sh" ) \
    </dev/null >"$SANDBOX/$1.out" 2>"$SANDBOX/$1.err"
  echo "$?" > "$SANDBOX/$1.rc"
}
# expect <run> <expected stdout> — exit 0, empty stderr, stdout exactly as given.
expect() {
  check "$1: exit 0" "0" "$(cat "$SANDBOX/$1.rc")"
  check "$1: stderr empty" "0" "$(wc -c < "$SANDBOX/$1.err" | tr -d ' ')"
  check "$1: output" "$2" "$(cat "$SANDBOX/$1.out")"
}
NL='
'
WARN_HEAD='WARNING: stale workflow engine: .adlc/workflows/adlc-sprint.workflow.js predates agent namespacing (no agentTypeFor)'

# --- plugin route -----------------------------------------------------------
run_fence plugin_no_vendored "$PLUGIN" "$HOME_PLUGIN" none
expect plugin_no_vendored "SCRIPT_PATH=$PLUGIN/workflows/adlc-sprint.workflow.js${NL}AGENT_NAMESPACE=adlc:"

run_fence plugin_vendored_current "$PLUGIN" "$HOME_PLUGIN" current
expect plugin_vendored_current "SCRIPT_PATH=.adlc/workflows/adlc-sprint.workflow.js${NL}AGENT_NAMESPACE=adlc:"

run_fence plugin_vendored_stale "$PLUGIN" "$HOME_PLUGIN" stale
check "plugin_vendored_stale: exit 0" "0" "$(cat "$SANDBOX/plugin_vendored_stale.rc")"
check "plugin_vendored_stale: stderr empty" "0" "$(wc -c < "$SANDBOX/plugin_vendored_stale.err" | tr -d ' ')"
check "plugin_vendored_stale: one warning line, first" "1" "$(sed -n 1p "$SANDBOX/plugin_vendored_stale.out" | command grep -c -F "$WARN_HEAD")"
check "plugin_vendored_stale: the warning names /template-drift" "1" "$(command grep -c -F 'Run /template-drift' "$SANDBOX/plugin_vendored_stale.out")"
check "plugin_vendored_stale: only one WARNING line" "1" "$(command grep -c '^WARNING:' "$SANDBOX/plugin_vendored_stale.out")"
check "plugin_vendored_stale: the plugin's engine is used" "SCRIPT_PATH=$PLUGIN/workflows/adlc-sprint.workflow.js${NL}AGENT_NAMESPACE=adlc:" \
  "$(sed -n '2,$p' "$SANDBOX/plugin_vendored_stale.out")"

run_fence plugin_stale_no_toolkit "$NOPLUGIN" "$HOME_PLUGIN" stale
check "plugin_stale_no_toolkit: the warning is printed" "1" "$(command grep -c '^WARNING: stale workflow engine' "$SANDBOX/plugin_stale_no_toolkit.out")"
check "plugin_stale_no_toolkit: the stale engine is not used" "SCRIPT_PATH=missing${NL}AGENT_NAMESPACE=adlc:" "$(sed -n '2,$p' "$SANDBOX/plugin_stale_no_toolkit.out")"

# --- symlink route ----------------------------------------------------------
run_fence symlink_vendored_stale - "$HOME_SYMLINK" stale
expect symlink_vendored_stale "SCRIPT_PATH=.adlc/workflows/adlc-sprint.workflow.js${NL}AGENT_NAMESPACE="

run_fence symlink_no_vendored - "$HOME_SYMLINK" none
expect symlink_no_vendored "SCRIPT_PATH=$HOME_SYMLINK/.claude/skills/workflows/adlc-sprint.workflow.js${NL}AGENT_NAMESPACE="

run_fence neither - "$HOME_NONE" none
expect neither "SCRIPT_PATH=missing${NL}AGENT_NAMESPACE="

# --- summary ----------------------------------------------------------------
echo "sprint-fence.test.sh: $CASES cases executed"
if [ "$CASES" -lt 25 ]; then
  echo "sprint-fence.test.sh: FAIL — expected at least 25 cases, ran $CASES ($SUT)"
  exit 1
fi
if [ "$FAILS" -eq 0 ]; then
  echo "sprint-fence.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "sprint-fence.test.sh: $FAILS FAILURE(S) ($SUT)"
exit 1
