#!/bin/sh
# tools/adlc/tests/e2e/plugin-sandbox.selftest.sh — a quick check of plugin-sandbox.sh's
# own contract, offline and without a model call (about 30 seconds):
#
#   list_names_every_case   — `--list` exits 0 and prints the five case names
#   help_names_gh_token     — `--help` exits 0 and names GH_TOKEN, the only GitHub
#                             credential the sandbox gets
#   bad_case_refused        — `--case <unknown>` and an unknown option exit 1, say so on
#                             stderr, and leave no sandbox behind
#   unrunnable_model_exit_2 — one case whose model check cannot run (no --with-model,
#                             no model credential in the environment) exits 2 with
#                             `RESULT: INCOMPLETE`, no FAIL line, and its sandbox removed
#
# Every run makes its sandbox under a fresh ADLC_E2E_TMPROOT, so "nothing left behind"
# is a directory listing. Usage: sh tools/adlc/tests/e2e/plugin-sandbox.selftest.sh

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT="$HERE/plugin-sandbox.sh"
FAILS=0
CASES=0
pass() { echo "PASS: $1"; CASES=$((CASES + 1)); }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
check() { if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi; }

TROOT=$(mktemp -d "${TMPDIR:-/tmp}/adlc-e2e-selftest.XXXXXX") || { echo "selftest: mktemp failed" >&2; exit 1; }
[ -n "$TROOT" ] && [ -d "$TROOT" ] || { echo "selftest: tmp root invalid" >&2; exit 1; }
case "$TROOT" in */adlc-e2e-selftest.*) ;; *) echo "selftest: tmp root is not one this script made" >&2; exit 1 ;; esac
trap 'chmod -R u+rwx "$TROOT" 2>/dev/null; rm -rf "$TROOT"' EXIT INT TERM
mkdir -p "$TROOT/sbx"
OUT="$TROOT/out"
ERR="$TROOT/err"
run() { ADLC_E2E_TMPROOT="$TROOT/sbx" sh "$SCRIPT" "$@" >"$OUT" 2>"$ERR"; echo "$?"; }
leftovers() { ( cd "$TROOT/sbx" && find . ! -name . -prune -print | sort | tr '\n' ' ' ); }

# --- list_names_every_case ----------------------------------------------------------
check "list_names_every_case: exit" 0 "$(run --list)"
check "list_names_every_case: five names" "init_spec_status_doctor lite_req_end_to_end_with_read_guard symlink_only_regressions printed_next_steps_runnable test_release_update " \
  "$(tr '\n' ' ' < "$OUT")"

# --- help_names_gh_token ------------------------------------------------------------
check "help_names_gh_token: exit" 0 "$(run --help)"
check "help_names_gh_token: GH_TOKEN is the GitHub credential" "1" "$(command grep -c '^GH_TOKEN (required for the GitHub case' "$OUT")"

# --- bad_case_refused ---------------------------------------------------------------
check "bad_case_refused: an unknown case exits 1" 1 "$(run --case no_such_case)"
check "bad_case_refused: it says so" "1" "$(command grep -c "unknown case 'no_such_case'" "$ERR")"
check "bad_case_refused: an unknown option exits 1" 1 "$(run --no-such-option)"
check "bad_case_refused: no sandbox left behind" "" "$(leftovers)"

# --- unrunnable_model_exit_2 --------------------------------------------------------
rc=$(unset CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_API_KEY; run --case printed_next_steps_runnable)
check "unrunnable_model_exit_2: exit 2 (incomplete)" 2 "$rc"
check "unrunnable_model_exit_2: RESULT: INCOMPLETE" "1" "$(command grep -c '^RESULT: INCOMPLETE' "$OUT")"
check "unrunnable_model_exit_2: no FAIL line" "0" "$(command grep -c '\[FAIL\]' "$OUT")"
check "unrunnable_model_exit_2: the model check is SKIPPED with a reason" "1" \
  "$(command grep -c '^  \[SKIPPED\] printed_next_steps_runnable.printed_steps_typed — .' "$OUT")"
check "unrunnable_model_exit_2: its sandbox is removed" "" "$(leftovers)"

echo "plugin-sandbox.selftest.sh: $CASES checks"
if [ "$CASES" -lt 13 ]; then echo "plugin-sandbox.selftest.sh: FAIL — expected at least 13 checks, ran $CASES"; exit 1; fi
if [ "$FAILS" -eq 0 ]; then echo "plugin-sandbox.selftest.sh: ALL PASS"; exit 0; fi
echo "plugin-sandbox.selftest.sh: $FAILS FAILURE(S)"
exit 1
