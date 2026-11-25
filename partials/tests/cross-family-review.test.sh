#!/bin/sh
# partials/tests/cross-family-review.test.sh — partials/cross-family-review.sh (REQ-722).
#
# Runs adlc_cross_family_review end to end against a throwaway git repository, with
# `adlc-read` replaced by a stub on PATH that appends one line per invocation to a
# call log (the delegate-gate.test.sh pattern): `print-gate`, `print-family`, or
# `delegate` for the one call that carries a corpus. That log is what the zero-call
# cases assert. Everything else is the real code: the gate partial, `adlc harness
# family`, cross_family.py and run_outcome.py, all from this checkout as ToolkitRoot.
#
# The stub answers the two probes the way the real CLI does for the configs written
# here: `--print-gate` prints `$STUB_GATE` (default `1 ok`), and `--print-family`
# reads `delegate.family` from $ADLC_CONFIG, `unknown` when absent. Reading it in
# shell keeps the harness free of PyYAML; the real resolver is covered by
# tools/delegate/tests/test_print_family.py. The delegate call copies the corpus it
# was handed to $STUB_SAW, prints $STUB_OUT_FILE and exits $STUB_RC.
#
# The implementer family comes from the real `adlc harness family` with CLAUDECODE=1
# and CLAUDE_CODE_ENTRYPOINT=cli (it needs both), which reads harness/claude.yml:
# `anthropic`. `env -i` keeps any CODEX_* or CURSOR_* variable, which would make it
# `unknown`, out of the child.
#
# Each case runs the function in a child shell under `env -i` (HOME, USER, LOGNAME,
# PATH and TMPDIR passed through), so nothing from the developer's environment
# (ADLC_DISABLE_DELEGATE, a delegate key, ADLC_EXEC_RUN) reaches it. The child
# shell is $ADLC_TEST_SHELL (run.sh sets it), default sh; runs_under_sh_and_zsh
# runs sh and zsh explicitly. Case names match the REQ-722 TASK-282 Verification
# table:
#   authorized_cross_family_runs, same_family_zero_calls, no_family_key_zero_calls,
#   disable_env_zero_calls, redaction_failure_never_sent, invalid_output_recorded,
#   skip_never_fails_caller, skip_prints_one_stderr_line_and_records,
#   runs_under_sh_and_zsh
# and further cases for api-error, subagent mode, the redacted corpus, secret files
# left out of the corpus, a multi-repo state, temp files, bad arguments and repo
# ids, and LESSON-718's toolkit-only rule.
#
#   sh partials/tests/cross-family-review.test.sh     (or: sh partials/tests/run.sh)
#
# Exits 0 iff every case passes; prints one line per assertion.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TOOLKIT=$(CDPATH= cd -- "$HERE/../.." && pwd)
SUT=${ADLC_TEST_SHELL:-sh}

FAILS=0
CASE=
pass() { echo "PASS: $CASE: $1"; }
fail() { echo "FAIL: $CASE: $1"; FAILS=$((FAILS + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}
begin() { CASE=$1; echo "=== $1 ==="; }

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-xfamtest.XXXXXX") || { echo "cross-family-review.test.sh: mktemp failed" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-xfamtest.*) [ -d "$SANDBOX" ] || { echo "cross-family-review.test.sh: sandbox missing" >&2; exit 1; } ;;
  *) echo "cross-family-review.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

BIN="$SANDBOX/bin"
SEDFAIL="$SANDBOX/sedfail"
FAKEHOME="$SANDBOX/home"
mkdir -p "$BIN" "$SEDFAIL" "$FAKEHOME"

# --- the adlc-read stub -------------------------------------------------------
cat > "$BIN/adlc-read" <<'STUB'
#!/bin/sh
case "${1-}" in
  --print-gate)
    echo print-gate >> "$STUB_CALLS"
    printf '%s\n' "${STUB_GATE:-1 ok}"
    exit 0 ;;
  --print-family)
    echo print-family >> "$STUB_CALLS"
    fam=unknown
    if [ -n "${ADLC_CONFIG-}" ] && [ -f "$ADLC_CONFIG" ]; then
      while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in '  family: '*) fam=${line#'  family: '} ;; esac
      done < "$ADLC_CONFIG"
    fi
    printf '%s\n' "$fam"
    exit 0 ;;
esac
echo delegate >> "$STUB_CALLS"
while [ $# -gt 0 ]; do
  if [ "$1" = --paths ] && [ $# -gt 1 ]; then cp "$2" "$STUB_SAW"; fi
  shift
done
[ -z "${STUB_OUT_FILE-}" ] || cat "$STUB_OUT_FILE"
exit "${STUB_RC:-0}"
STUB
chmod +x "$BIN/adlc-read"

# A sed that always fails, first on PATH for the redaction case only. It notes that
# it ran, so that case cannot pass without reaching the redaction step.
printf '#!/bin/sh\necho sed >> "%s"\nexit 1\n' "$SANDBOX/sed-ran" > "$SEDFAIL/sed"
chmod +x "$SEDFAIL/sed"

# PATH with no adlc-read anywhere on it, for no-binary.
NOBIN_PATH=
_rest="$PATH:"
while [ -n "$_rest" ]; do
  _dir=${_rest%%:*}
  _rest=${_rest#*:}
  case "$_dir" in /*) ;; *) continue ;; esac
  [ -e "$_dir/adlc-read" ] && continue
  NOBIN_PATH="${NOBIN_PATH:+$NOBIN_PATH:}$_dir"
done

# --- configs and delegate answers -----------------------------------------------
CFG_MOONSHOT="$SANDBOX/moonshot.yml";   printf 'delegate:\n  enabled: true\n  family: moonshot\n' > "$CFG_MOONSHOT"
CFG_ANTHROPIC="$SANDBOX/anthropic.yml"; printf 'delegate:\n  enabled: true\n  family: anthropic\n' > "$CFG_ANTHROPIC"
CFG_NOFAMILY="$SANDBOX/nofamily.yml";   printf 'delegate:\n  enabled: true\n' > "$CFG_NOFAMILY"
OUT_VALID="$SANDBOX/valid.out"
printf 'Here is the review.\nFINDING\tMajor\tapp.py\t12\tmissing-error-handling\tThe loop ignores the return code\nRULE\tBR-1\tmet\tChecked\nRULE\tAC-1\tmet\tIt stops\n' > "$OUT_VALID"
OUT_UNMET="$SANDBOX/unmet.out"
printf 'RULE\tBR-1\tunmet\tNo check of the return code\nRULE\tAC-1\tmet\tIt stops\n' > "$OUT_UNMET"
OUT_INVALID="$SANDBOX/invalid.out"
printf 'FINDING\tMajor\t../etc/passwd\t1\tpath-traversal\tEscapes the tree\nFINDING\tSevere\tapp.py\t3\toff-by-one\tNot a severity\nFINDING\tMajor\tother.py\t3\toff-by-one\tNot in the diff\n' > "$OUT_INVALID"

# --- the repository under review ---------------------------------------------------
# Assembled here so this file holds nothing credential-shaped.
KEY="sk-$(printf 'a1b2%.0s' 1 2 3 4 5 6)"
REPO="$SANDBOX/repo"
gitr() { # gitr <dir> <git args...> — no global or system config, no signing
  _g=$1; shift
  HOME="$FAKEHOME" GIT_CONFIG_NOSYSTEM=1 git -C "$_g" -c user.name=t -c user.email=t@example.invalid \
    -c commit.gpgsign=false -c init.defaultBranch=integ "$@"
}
mkdir -p "$REPO"
gitr "$REPO" init -q
gitr "$REPO" checkout -q -b integ 2>/dev/null
mkdir -p "$REPO/.adlc/specs/REQ-001-loop"
SPEC="$REPO/.adlc/specs/REQ-001-loop/requirement.md"
printf '# REQ-001\n\n## Business Rules\n\n- [ ] BR-1: The loop checks every return code.\n\n## Acceptance Criteria\n\n- [ ] A failing step stops the loop.\n' > "$SPEC"
_i=1; : > "$REPO/app.py"
while [ "$_i" -le 10 ]; do printf 'step_%s()\n' "$_i" >> "$REPO/app.py"; _i=$((_i + 1)); done
gitr "$REPO" add -A && gitr "$REPO" commit -q -m base
gitr "$REPO" checkout -q -b feature
_i=11
while [ "$_i" -le 30 ]; do printf 'step_%s()\n' "$_i" >> "$REPO/app.py"; _i=$((_i + 1)); done
printf 'client = connect("%s")\nGITHUB_TOKEN=abc123def456\n' "$KEY" >> "$REPO/app.py"
# Files named as secrets, which the partial must leave out of the corpus by name: none
# of these markers is credential-shaped, so only the pathspec can keep them out. And
# their neighbours, named alike but not secrets, which must still be sent.
mkdir -p "$REPO/config" "$REPO/deploy/keys" "$REPO/certs" "$REPO/docs"
printf 'DB_PASSWORD=dotenv-marker-5520\n' > "$REPO/.env"
printf 'DB_PASSWORD=dotenv-local-marker-5521\n' > "$REPO/config/.env.local"
printf -- '-----BEGIN FAKE-----\npem-marker-7731\n' > "$REPO/x.pem"
printf -- 'pem-nested-marker-7732\n' > "$REPO/certs/server.pem"
printf -- 'rsa-marker-7733\n' > "$REPO/deploy/keys/id_rsa"
printf -- 'npmrc-marker-7734\n' > "$REPO/.npmrc"
printf -- 'pemcase-marker-7735\n' > "$REPO/certs/CLIENT.PEM"
mkdir -p "$REPO/infra"
printf -- 'tfvars-marker-7736\n' > "$REPO/infra/prod.tfvars"
printf -- 'gitcred-marker-7737\n' > "$REPO/config/.git-credentials"
printf -- 'pemdoc-marker-8801\n' > "$REPO/docs/x.pem.md"
printf -- 'envrc-marker-8802\n' > "$REPO/config/env.sample"
gitr "$REPO" add -A && gitr "$REPO" commit -q -m change
[ "$(gitr "$REPO" rev-list --count integ..feature)" = 1 ] || { echo "cross-family-review.test.sh: repository setup failed" >&2; exit 1; }

# --- running one review -------------------------------------------------------------
# run_xf <dir> <shell> <subagent> [VAR=value...] — runs the function in a child shell,
# cwd $RUN_CWD (default $SANDBOX), against $RUN_REPO/$RUN_SPEC/$RUN_BASE (default the
# repo above), with $RUN_STATE (default `{}`) as the state file's first content.
# Leaves <dir>/{stdout,stderr,rc,caller,calls,state.json,saw,tmp}. The
# caller sets an EXIT trap of its own and runs a statement after the call, so a
# case can assert the function neither clobbers the one nor skips the other.
run_xf() {
  _d=$1; _sh=$2; _sub=$3; shift 3
  rm -rf "$_d"; mkdir -p "$_d/tmp"
  : > "$_d/calls"; : > "$_d/caller"
  _st=${RUN_STATE-}; [ -n "$_st" ] || _st='{}'
  printf '%s\n' "$_st" > "$_d/state.json"
  (
    cd "${RUN_CWD:-$SANDBOX}" || exit 1
    env -i HOME="$FAKEHOME" USER="${USER:-adlc}" LOGNAME="${LOGNAME:-adlc}" PATH="$BIN:$PATH" \
      TMPDIR="$_d/tmp" ADLC_TOOLKIT_ROOT="$TOOLKIT" ADLC_CONFIG="$CFG_MOONSHOT" CLAUDECODE=1 \
      CLAUDE_CODE_ENTRYPOINT=cli ADLC_RUN_OUTCOMES_LOG="$_d/run-outcomes.log" \
      STUB_CALLS="$_d/calls" STUB_SAW="$_d/saw" STUB_OUT_FILE="$OUT_VALID" "$@" \
      "$_sh" -c 'trap "echo caller-exit-trap >> \"\$8\"" EXIT
        . "$1/partials/cross-family-review.sh"
        adlc_cross_family_review app "$2" "$3" "$4" "$5" "$6"
        printf "%s\n" "$?" > "$7"
        echo caller-continued >> "$8"' \
      _ "$TOOLKIT" "${RUN_REPO:-$REPO}" "${RUN_BASE:-integ}" "${RUN_SPEC:-$SPEC}" "$_d/state.json" "$_sub" "$_d/rc" "$_d/caller" \
      > "$_d/stdout" 2> "$_d/stderr"
  )
}

rec() { # rec <dir> — "status reason implementer reviewer findings dropped", or "-"
  python3 -c 'import json, sys
r = json.load(open(sys.argv[1])).get("crossFamilyReview", {}).get("app")
print("-" if r is None else "%s %s %s %s %s %s" % (r["status"], r.get("reason", "-"), r["implementerFamily"],
      r["reviewerFamily"], r["findingCount"], r["droppedCount"]))' "$1/state.json"
}
count() { # count <word> <dir> — lines of the call log equal to <word>
  grep -c "^$1\$" "$2/calls" 2>/dev/null || :
}
lines() { # lines <file>
  wc -l < "$1" | tr -d ' '
}
has() { # has <text> <literal> — yes/no; no `case` inside `$( )` (LESSON-582)
  case "$1" in *"$2"*) echo yes ;; *) echo no ;; esac
}
leftovers() { # leftovers <dir> — temp files the run left behind
  find "$1/tmp" -name 'adlc-xfam.*' 2>/dev/null | wc -l | tr -d ' '
}

# --- the runs --------------------------------------------------------------------------
V="$SANDBOX/v"
run_xf "$V/ran" "$SUT" 0
run_xf "$V/subagent-mode" "$SUT" 1
run_xf "$V/delegation-disabled" "$SUT" 0 ADLC_DISABLE_DELEGATE=1
run_xf "$V/no-binary" "$SUT" 0 PATH="$NOBIN_PATH"
run_xf "$V/family-unknown" "$SUT" 0 ADLC_CONFIG="$CFG_NOFAMILY"
run_xf "$V/same-family" "$SUT" 0 ADLC_CONFIG="$CFG_ANTHROPIC"
run_xf "$V/redaction-failed" "$SUT" 0 PATH="$SEDFAIL:$BIN:$PATH"
run_xf "$V/api-error" "$SUT" 0 STUB_RC=1
run_xf "$V/invalid-output" "$SUT" 0 STUB_OUT_FILE="$OUT_INVALID"
run_xf "$V/unmet-one-repo" "$SUT" 0 STUB_OUT_FILE="$OUT_UNMET"
RUN_STATE='{"repos": {"app": {"touched": true}, "web": {"touched": true}}}'
run_xf "$V/unmet-two-repos" "$SUT" 0 STUB_OUT_FILE="$OUT_UNMET"
RUN_STATE='{"repos": ["app", "web"]}'
run_xf "$V/malformed-state" "$SUT" 0 STUB_OUT_FILE="$OUT_UNMET"
unset RUN_STATE
# The skip variants, as positional parameters: a list in one string depends on word
# splitting, which zsh does not do for a parameter (BUG-118).
skips() { set -- subagent-mode delegation-disabled no-binary family-unknown same-family \
  redaction-failed api-error invalid-output; printf '%s\n' "$@"; }

begin authorized_cross_family_runs
check "returns 0" 0 "$(cat "$V/ran/rc")"
check "exactly one delegate call" 1 "$(count delegate "$V/ran")"
check "records ran with both families and one finding" "ran - anthropic moonshot 1 0" "$(rec "$V/ran")"
check "stdout opens the findings block" '<cross-family-findings repo="app">' "$(sed -n 1p "$V/ran/stdout")"
check "stdout closes the findings block" '</cross-family-findings>' "$(sed -n 3p "$V/ran/stdout")"
check "the block is three lines" 3 "$(lines "$V/ran/stdout")"
_json=$(sed -n 2p "$V/ran/stdout")
check "the finding carries source cross-family" yes "$(has "$_json" '"source":["cross-family"]')"
check "the finding names its file and line" yes "$(has "$_json" '"file":"app.py","line":12')"
check "nothing on stderr" 0 "$(lines "$V/ran/stderr")"
check "no temp file left" 0 "$(leftovers "$V/ran")"

begin corpus_is_redacted_before_send
check "the delegate was handed a corpus" yes "$([ -s "$V/ran/saw" ] && echo yes || echo no)"
check "the key never reached the delegate" 0 "$(grep -c "$KEY" "$V/ran/saw" || :)"
check "the token assignment never reached the delegate" 0 "$(grep -c 'abc123def456' "$V/ran/saw" || :)"
check "both credential lines read [REDACTED]" 2 "$(grep -c '\[REDACTED\]' "$V/ran/saw" || :)"
check "the corpus holds the diff against the base" 1 "$(grep -c '^=== DIFF integ\.\.\.HEAD' "$V/ran/saw" || :)"
check "the diff carries wide context" yes "$(grep -q '^ step_1()$' "$V/ran/saw" && echo yes || echo no)"
check "the corpus holds the changed-files list" yes "$(sed -n '/^=== CHANGED FILES ===$/,/^=== SPEC/p' "$V/ran/saw" | grep -qx 'app.py' && echo yes || echo no)"
check "the corpus holds BR-1" 1 "$(grep -c '^BR-1: The loop checks every return code\.$' "$V/ran/saw" || :)"
check "the corpus holds AC-1" 1 "$(grep -c '^AC-1: A failing step stops the loop\.$' "$V/ran/saw" || :)"

begin secret_files_never_sent
for _m in dotenv-marker-5520 dotenv-local-marker-5521 pem-marker-7731 pem-nested-marker-7732 \
  rsa-marker-7733 npmrc-marker-7734 pemcase-marker-7735 tfvars-marker-7736 gitcred-marker-7737 'BEGIN FAKE'; do
  check "$_m never reached the delegate" 0 "$(grep -c "$_m" "$V/ran/saw" || :)"
done
for _f in .env config/.env.local x.pem certs/server.pem deploy/keys/id_rsa .npmrc certs/CLIENT.PEM infra/prod.tfvars config/.git-credentials; do
  check "$_f is not in the changed-files list" 0 "$(grep -cxF "$_f" "$V/ran/saw" || :)"
done
# Must-not-fire neighbours: named like a secret file, but not one.
check "docs/x.pem.md is still sent" 1 "$(grep -c 'pemdoc-marker-8801' "$V/ran/saw" || :)"
check "config/env.sample is still sent" 1 "$(grep -c 'envrc-marker-8802' "$V/ran/saw" || :)"
check "docs/x.pem.md is in the changed-files list" 1 "$(grep -cxF docs/x.pem.md "$V/ran/saw" || :)"

begin multi_repo_state_reaches_validate
_one=$(sed -n 2p "$V/unmet-one-repo/stdout")
_two=$(sed -n 2p "$V/unmet-two-repos/stdout")
check "one touched repo: unmet is a must-fix Major" yes "$(has "$_one" '"severity":"Major","file":".adlc/specs/REQ-001-loop/requirement.md","line":5,"class":"omitted-requirement","title":"BR-1 unmet: No check of the return code","mustFix":true')"
check "two touched repos: unmet is a Minor that never blocks" yes "$(has "$_two" '"severity":"Minor","file":".adlc/specs/REQ-001-loop/requirement.md","line":5,"class":"omitted-requirement","title":"BR-1 unmet in this repo, may be met in another repo: No check of the return code","mustFix":false')"
check "two touched repos: recorded ran" "ran - anthropic moonshot 1 0" "$(rec "$V/unmet-two-repos")"
check "a malformed state is refused, recorded invalid-output" "skipped invalid-output anthropic moonshot 0 0" "$(rec "$V/malformed-state")"
check "a malformed state prints no block" 0 "$(lines "$V/malformed-state/stdout")"

begin same_family_zero_calls
check "records skipped same-family" "skipped same-family anthropic anthropic 0 0" "$(rec "$V/same-family")"
check "zero delegate calls" 0 "$(count delegate "$V/same-family")"
check "one stderr line" 1 "$(lines "$V/same-family/stderr")"
check "nothing on stdout" 0 "$(lines "$V/same-family/stdout")"

begin no_family_key_zero_calls
check "records skipped family-unknown" "skipped family-unknown anthropic unknown 0 0" "$(rec "$V/family-unknown")"
check "zero delegate calls" 0 "$(count delegate "$V/family-unknown")"
check "the family was asked of adlc-read" 1 "$(count print-family "$V/family-unknown")"

begin disable_env_zero_calls
check "records skipped delegation-disabled" "skipped delegation-disabled anthropic unknown 0 0" "$(rec "$V/delegation-disabled")"
check "zero calls of adlc-read of any kind" 0 "$(lines "$V/delegation-disabled/calls")"

begin redaction_failure_never_sent
check "the failing sed ran" yes "$([ -s "$SANDBOX/sed-ran" ] && echo yes || echo no)"
check "records skipped redaction-failed" "skipped redaction-failed anthropic moonshot 0 0" "$(rec "$V/redaction-failed")"
check "zero delegate calls" 0 "$(count delegate "$V/redaction-failed")"
check "the delegate saw no corpus" no "$([ -e "$V/redaction-failed/saw" ] && echo yes || echo no)"
check "the temp file is gone after return" 0 "$(leftovers "$V/redaction-failed")"

begin api_error_recorded
check "records skipped api-error" "skipped api-error anthropic moonshot 0 0" "$(rec "$V/api-error")"
check "the one call was made" 1 "$(count delegate "$V/api-error")"
check "nothing on stdout" 0 "$(lines "$V/api-error/stdout")"

begin invalid_output_recorded
check "records skipped invalid-output with every line dropped" "skipped invalid-output anthropic moonshot 0 3" "$(rec "$V/invalid-output")"
check "the one call was made" 1 "$(count delegate "$V/invalid-output")"
check "no findings block" 0 "$(lines "$V/invalid-output/stdout")"

begin subagent_mode_recorded
check "records skipped subagent-mode, the reviewer never asked" "skipped subagent-mode anthropic unknown 0 0" "$(rec "$V/subagent-mode")"
check "zero calls of adlc-read of any kind, no gate probe" 0 "$(lines "$V/subagent-mode/calls")"

begin skip_never_fails_caller
skips > "$SANDBOX/skips"
while IFS= read -r _r; do
  check "$_r: returns 0" 0 "$(cat "$V/$_r/rc")"
  check "$_r: the caller's next statement ran" 1 "$(grep -c '^caller-continued$' "$V/$_r/caller" || :)"
  check "$_r: the caller's own EXIT trap still fired" 1 "$(grep -c '^caller-exit-trap$' "$V/$_r/caller" || :)"
done < "$SANDBOX/skips"

begin skip_prints_one_stderr_line_and_records
while IFS= read -r _r; do
  check "$_r: exactly one stderr line" 1 "$(lines "$V/$_r/stderr")"
  check "$_r: the line names the repo and the reason" "/proceed: cross-family review skipped for app: $_r" "$(cat "$V/$_r/stderr")"
  check "$_r: recorded skipped with that reason" "skipped $_r" "$(rec "$V/$_r" | cut -d' ' -f1-2)"
done < "$SANDBOX/skips"

begin no_case_leaves_a_temp_file
{ echo ran; skips; } > "$SANDBOX/runs"
while IFS= read -r _r; do
  check "$_r: no adlc-xfam file left" 0 "$(leftovers "$V/$_r")"
done < "$SANDBOX/runs"

begin bad_arguments_return_zero_and_record_nothing
rm -rf "$SANDBOX/bad"; mkdir -p "$SANDBOX/bad/tmp"; : > "$SANDBOX/bad/calls"; printf '{}\n' > "$SANDBOX/bad/state.json"
env -i HOME="$FAKEHOME" USER="${USER:-adlc}" LOGNAME="${LOGNAME:-adlc}" PATH="$BIN:$PATH" TMPDIR="$SANDBOX/bad/tmp" \
  ADLC_TOOLKIT_ROOT="$TOOLKIT" ADLC_CONFIG="$CFG_MOONSHOT" CLAUDECODE=1 CLAUDE_CODE_ENTRYPOINT=cli \
  STUB_CALLS="$SANDBOX/bad/calls" \
  "$SUT" -c '. "$1/partials/cross-family-review.sh"
    adlc_cross_family_review "a b" "$2" integ "$3" "$4"; echo "rc=$?"
    adlc_cross_family_review app "$2" "--upload-pack=x" "$3" "$4"; echo "rc=$?"
    adlc_cross_family_review app "$2" integ "$3" "$4" yes; echo "rc=$?"
    adlc_cross_family_review app; echo "rc=$?"
    adlc_cross_family_review -app "$2" integ "$3" "$4"; echo "rc=$?"
    adlc_cross_family_review .app "$2" integ "$3" "$4"; echo "rc=$?"' \
  _ "$TOOLKIT" "$REPO" "$SPEC" "$SANDBOX/bad/state.json" > "$SANDBOX/bad/stdout" 2> "$SANDBOX/bad/stderr"
check "every bad call returns 0" "rc=0 rc=0 rc=0 rc=0 rc=0 rc=0" "$(tr '\n' ' ' < "$SANDBOX/bad/stdout" | sed 's/ $//')"
check "one not-run line per bad call" 6 "$(grep -c '^/proceed: cross-family review not run for ' "$SANDBOX/bad/stderr" || :)"
check "a space, a leading - and a leading . are each refused as a repo id" 3 "$(grep -c '^/proceed: cross-family review not run for <no repo id>: the repo id must be ' "$SANDBOX/bad/stderr" || :)"
check "nothing recorded" '{}' "$(tr -d '\n' < "$SANDBOX/bad/state.json")"
check "zero calls of adlc-read" 0 "$(lines "$SANDBOX/bad/calls")"

begin repo_id_inner_punctuation_accepted
# Must-not-fire neighbour of the leading-character refusal: `_` may lead, and `.` and
# `-` may follow. Delegation is disabled so the run records at once.
rm -rf "$SANDBOX/okid"; mkdir -p "$SANDBOX/okid/tmp"; printf '{}\n' > "$SANDBOX/okid/state.json"
env -i HOME="$FAKEHOME" USER="${USER:-adlc}" LOGNAME="${LOGNAME:-adlc}" PATH="$BIN:$PATH" TMPDIR="$SANDBOX/okid/tmp" \
  ADLC_TOOLKIT_ROOT="$TOOLKIT" ADLC_CONFIG="$CFG_MOONSHOT" CLAUDECODE=1 CLAUDE_CODE_ENTRYPOINT=cli \
  ADLC_DISABLE_DELEGATE=1 STUB_CALLS="$SANDBOX/okid/calls" \
  "$SUT" -c '. "$1/partials/cross-family-review.sh"
    adlc_cross_family_review _a.b-c "$2" integ "$3" "$4"' \
  _ "$TOOLKIT" "$REPO" "$SPEC" "$SANDBOX/okid/state.json" > "$SANDBOX/okid/stdout" 2> "$SANDBOX/okid/stderr"
check "_a.b-c is recorded" "skipped delegation-disabled" "$(python3 -c 'import json, sys
r = json.load(open(sys.argv[1])).get("crossFamilyReview", {}).get("_a.b-c") or {}
print(r.get("status", "-"), r.get("reason", "-"))' "$SANDBOX/okid/state.json")"

begin worktree_copies_never_executed
# A clone of the repo under review, run from inside it, holding planted copies of
# everything the partial runs. Each one notes it ran. LESSON-718: none may run.
R2="$SANDBOX/repo2"
HOME="$FAKEHOME" GIT_CONFIG_NOSYSTEM=1 git clone -q "$REPO" "$R2"
PLANTED="$SANDBOX/planted-ran"
mkdir -p "$R2/.adlc/partials" "$R2/tools/delegate" "$R2/tools/adlc"
_plant="echo planted >> \"$PLANTED\""
printf '%s\nADLC_READ_BIN=/bin/echo\nadlc_delegate_gate_check() { %s; return 0; }\n' "$_plant" "$_plant" > "$R2/.adlc/partials/delegate-gate.sh"
printf '%s\n' "$_plant" > "$R2/.adlc/partials/delegate-tools-path.sh"
for _f in emit-telemetry.sh emit-run-outcome.sh; do
  printf '#!/bin/sh\n%s\n' "$_plant" > "$R2/tools/delegate/$_f"; chmod +x "$R2/tools/delegate/$_f"
done
_pyplant="open(\"$PLANTED\", \"a\").write(\"planted\\n\")"
for _f in tools/delegate/cross_family.py tools/delegate/model_family.py tools/delegate/run_outcome.py tools/adlc/adlc.py json.py model_family.py; do
  printf '%s\n' "$_pyplant" > "$R2/$_f"
done
# Set and unset around the call: an assignment prefixed to a function call persists
# after it under some shells.
RUN_CWD="$R2"; RUN_REPO="$R2"; RUN_BASE=origin/integ; RUN_SPEC="$R2/.adlc/specs/REQ-001-loop/requirement.md"
run_xf "$SANDBOX/planted" "$SUT" 0
unset RUN_CWD RUN_REPO RUN_BASE RUN_SPEC
check "no planted file ran" no "$([ -e "$PLANTED" ] && echo yes || echo no)"
check "the review ran on the toolkit's own code" "ran - anthropic moonshot 1 0" "$(rec "$SANDBOX/planted")"
check "one delegate call, to the stub" 1 "$(count delegate "$SANDBOX/planted")"

begin runs_under_sh_and_zsh
for _sh in sh zsh; do
  if ! command -v "$_sh" >/dev/null 2>&1; then
    echo "SKIP: $CASE: $_sh is not installed"
    continue
  fi
  run_xf "$SANDBOX/shell-$_sh" "$_sh" 0
  check "$_sh: returns 0" 0 "$(cat "$SANDBOX/shell-$_sh/rc")"
  check "$_sh: records ran" "ran - anthropic moonshot 1 0" "$(rec "$SANDBOX/shell-$_sh")"
  check "$_sh: one delegate call" 1 "$(count delegate "$SANDBOX/shell-$_sh")"
  check "$_sh: stdout is the one block" 3 "$(lines "$SANDBOX/shell-$_sh/stdout")"
  check "$_sh: nothing on stderr" 0 "$(lines "$SANDBOX/shell-$_sh/stderr")"
  check "$_sh: no temp file left" 0 "$(leftovers "$SANDBOX/shell-$_sh")"
done
if [ -f "$SANDBOX/shell-sh/stdout" ] && [ -f "$SANDBOX/shell-zsh/stdout" ]; then
  check "sh and zsh print the same block" yes "$(cmp -s "$SANDBOX/shell-sh/stdout" "$SANDBOX/shell-zsh/stdout" && echo yes || echo no)"
  check "sh and zsh send the same corpus" yes "$(cmp -s "$SANDBOX/shell-sh/saw" "$SANDBOX/shell-zsh/saw" && echo yes || echo no)"
fi

echo
if [ "$FAILS" -eq 0 ]; then
  echo "cross-family-review.test.sh: all cases passed ($SUT)"
  exit 0
fi
echo "cross-family-review.test.sh: $FAILS assertion(s) failed ($SUT)"
exit 1
