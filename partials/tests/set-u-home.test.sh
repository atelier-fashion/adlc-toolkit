#!/bin/sh
# partials/tests/set-u-home.test.sh — REQ-669 review fix: the partials' default-
# expansion operand under `set -u` with HOME unset.
#
# A partial that sources another partial (or reads a toolkit file) falls back to
# "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/...". With ADLC_TOOLKIT_ROOT unset
# that reads a bare $HOME, which ABORTS a `set -u` shell when HOME is unset too.
# Each such site is guarded with `[ -n "${ADLC_TOOLKIT_ROOT:-}${HOME+x}" ]`, as
# delegate-tools-path.sh, forge.sh and intake.sh already were, and the operand
# itself stays byte-identical (the lint and source-guard.test.sh pin it).
#
# Cases, each run as `set -u; . <partial>` from an empty directory with HOME and
# ADLC_TOOLKIT_ROOT removed from the environment:
#   lane_check_sources      — partials/lane-check.sh loads; its call is a check-error
#                             (lane-check.test.sh covers the call in full)
#   emit_step_telemetry     — loads with DELEGATE_TOOLS at its defensive default,
#                             and the emit call returns: telemetry never blocks a
#                             skill (REQ-424)
#   id_recheck              — loads, and a recheck returns instead of aborting (no
#                             repo is reachable from its sandbox repos root)
#   ethos_include           — prints "No ethos found" instead of aborting
#   home_set_benign         — the benign path: with HOME set to a sandbox whose
#                             ~/.claude/skills is this checkout, ethos-include
#                             still prints the toolkit's ETHOS.md and
#                             emit-step-telemetry resolves the toolkit's
#                             tools/delegate, so the guard changes nothing there
#
# Native zsh sets HOME from the password database when it is unset, so under zsh
# every case runs as `zsh --emulate sh`, the mode in which HOME can be unset.
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL):
#   ADLC_TEST_SHELL=dash sh partials/tests/set-u-home.test.sh
# or, for bash, zsh, /bin/sh and dash in turn:  sh partials/tests/run.sh
#
# Exits 0 iff every check passes and the executed-case count clears its floor.

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

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-setuhome.XXXXXX") || { echo "set-u-home.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "set-u-home.test.sh: sandbox path invalid" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-setuhome.*) ;;
  *) echo "set-u-home.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
trap 'rm -rf "$SANDBOX"' EXIT INT TERM
mkdir -p "$SANDBOX/empty" "$SANDBOX/norepos" "$SANDBOX/home/.claude" || exit 1
ln -s "$TOOLKIT" "$SANDBOX/home/.claude/skills"

# run_u <name> <script-body> — the body after `set -u`, from the empty directory,
# with HOME and ADLC_TOOLKIT_ROOT unset. Output in $SANDBOX/<name>.out/.err/.rc.
run_u() {
  printf 'set -u\n%s\nprintf "SURVIVED\\n"\n' "$2" > "$SANDBOX/$1.sh"
  case "$SUT" in
    *zsh) ( cd "$SANDBOX/empty" && unset HOME ADLC_TOOLKIT_ROOT CLAUDE_PLUGIN_ROOT && exec "$SUT" --emulate sh "$SANDBOX/$1.sh" ) ;;
    *) ( cd "$SANDBOX/empty" && unset HOME ADLC_TOOLKIT_ROOT CLAUDE_PLUGIN_ROOT && exec "$SUT" "$SANDBOX/$1.sh" ) ;;
  esac >"$SANDBOX/$1.out" 2>"$SANDBOX/$1.err"
  echo "$?" > "$SANDBOX/$1.rc"
}
survived() { command grep -c -x 'SURVIVED' "$SANDBOX/$1.out"; }
no_abort_msg() { # the shells' unbound-variable wording, none of which may appear
  command grep -c -i -E 'parameter not set|unbound variable|parameter null or not set' "$SANDBOX/$1.err"
}

# The probe itself: HOME really is unset in the shell under test.
run_u probe 'printf "HOME=[%s]\n" "${HOME-}"'
check "probe: HOME is unset in the shell under test" "HOME=[]" "$(sed -n 1p "$SANDBOX/probe.out")"

# --- lane_check_sources -----------------------------------------------------
run_u lanecheck ". '$PARTIALS/lane-check.sh'
adlc_lane_check '$SANDBOX/empty' main >/dev/null 2>&1; printf 'call_rc=%s\n' \"\$?\""
check "lane_check_sources: no abort" "1" "$(survived lanecheck)"
check "lane_check_sources: no unbound-variable error" "0" "$(no_abort_msg lanecheck)"
check "lane_check_sources: the call is an error, never a pass" "call_rc=2" "$(command grep '^call_rc=' "$SANDBOX/lanecheck.out")"

# --- emit_step_telemetry ----------------------------------------------------
run_u telemetry ". '$PARTIALS/emit-step-telemetry.sh'
printf 'DELEGATE_TOOLS=%s\n' \"\$DELEGATE_TOOLS\"
flag='$SANDBOX/flag'
_adlc_emit_step_telemetry spec step-1 >/dev/null 2>&1
printf 'emitted\n'"
check "emit_step_telemetry: no abort" "1" "$(survived telemetry)"
check "emit_step_telemetry: no unbound-variable error" "0" "$(no_abort_msg telemetry)"
check "emit_step_telemetry: DELEGATE_TOOLS keeps its defensive default" "DELEGATE_TOOLS=tools/delegate" "$(command grep '^DELEGATE_TOOLS=' "$SANDBOX/telemetry.out")"
check "emit_step_telemetry: the emit call returns" "1" "$(command grep -c -x 'emitted' "$SANDBOX/telemetry.out")"

# --- id_recheck -------------------------------------------------------------
# ADLC_REPOS_ROOT is an empty directory, so no remote is ever contacted.
run_u recheck "ADLC_REPOS_ROOT='$SANDBOX/norepos'; export ADLC_REPOS_ROOT
. '$PARTIALS/id-recheck.sh'
adlc_recheck_id req REQ-001 REQ-001-own >/dev/null 2>&1; printf 'call_rc=%s\n' \"\$?\""
check "id_recheck: no abort" "1" "$(survived recheck)"
check "id_recheck: no unbound-variable error" "0" "$(no_abort_msg recheck)"
case "$(command grep '^call_rc=' "$SANDBOX/recheck.out")" in
  call_rc=0 | call_rc=2) pass "id_recheck: the recheck returned ($(command grep '^call_rc=' "$SANDBOX/recheck.out"))" ;;
  *) fail "id_recheck: the recheck gave '$(command grep '^call_rc=' "$SANDBOX/recheck.out")', want call_rc=0 or 2" ;;
esac

# --- ethos_include ----------------------------------------------------------
run_u ethos ". '$PARTIALS/ethos-include.sh'"
check "ethos_include: no abort" "1" "$(survived ethos)"
check "ethos_include: no unbound-variable error" "0" "$(no_abort_msg ethos)"
check "ethos_include: prints the no-ethos line" "No ethos found" "$(sed -n 1p "$SANDBOX/ethos.out")"

# --- home_set_benign --------------------------------------------------------
# HOME set (ADLC_TOOLKIT_ROOT still unset): the guards pass and the default
# operand reads the symlink install, exactly as before.
benign() { # benign <name> <body>
  printf 'set -u\n%s\n' "$2" > "$SANDBOX/$1.sh"
  ( cd "$SANDBOX/empty" && unset ADLC_TOOLKIT_ROOT CLAUDE_PLUGIN_ROOT && HOME="$SANDBOX/home" && export HOME \
    && exec "$SUT" "$SANDBOX/$1.sh" ) >"$SANDBOX/$1.out" 2>"$SANDBOX/$1.err"
}
benign ethos_set ". '$PARTIALS/ethos-include.sh'"
check "home_set_benign: ethos-include prints the toolkit's ETHOS.md" "$(head -n 1 "$TOOLKIT/ETHOS.md")" "$(sed -n 1p "$SANDBOX/ethos_set.out")"
benign telemetry_set ". '$PARTIALS/emit-step-telemetry.sh'
printf 'DELEGATE_TOOLS=%s\n' \"\$DELEGATE_TOOLS\""
check "home_set_benign: emit-step-telemetry resolves the toolkit's tools/delegate" \
  "DELEGATE_TOOLS=$SANDBOX/home/.claude/skills/tools/delegate" "$(command grep '^DELEGATE_TOOLS=' "$SANDBOX/telemetry_set.out")"

# --- summary ----------------------------------------------------------------
echo "set-u-home.test.sh: $CASES cases executed"
if [ "$CASES" -lt 16 ]; then
  echo "set-u-home.test.sh: FAIL — expected at least 16 cases, ran $CASES ($SUT)"
  exit 1
fi
if [ "$FAILS" -eq 0 ]; then
  echo "set-u-home.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "set-u-home.test.sh: $FAILS FAILURE(S) ($SUT)"
exit 1
