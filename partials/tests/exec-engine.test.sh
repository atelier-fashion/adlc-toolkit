#!/bin/sh
# partials/tests/exec-engine.test.sh — the /sprint exec engine end to end (REQ-659 BR-18).
#
# launch → awaiting_approval → approve → merge → close-out → cleanup, from a plain shell,
# with a fake harness, the stateful mock forge and a throwaway bare origin: no network and
# no model. Every path is a throwaway. The only process this harness signals is the
# supervisor it started, by the pid it recorded: another runner may share this machine.
#
# Run under each shell by partials/tests/run.sh; exits 0 iff every case passes.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
FAILS=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }
check() {
  if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (expected '$2', got '$3')"; fi
}
contains() {
  case "$3" in
    *"$2"*) pass "$1" ;;
    *) fail "$1 (missing '$2' in: $3)" ;;
  esac
}

SBX=$(mktemp -d)
SUP_PID=
cleanup() {
  [ -n "$SUP_PID" ] && kill "$SUP_PID" 2>/dev/null
  rm -rf "$SBX"
}
trap cleanup EXIT INT TERM

HOME=$SBX/home; export HOME
mkdir -p "$HOME" "$SBX/bin" "$SBX/acme" "$SBX/store" "$SBX/state"
printf '[user]\n\tname = op\n\temail = op@example.invalid\n[init]\n\tdefaultBranch = main\n' > "$HOME/.gitconfig"
ADLC_HOME=$HOME/.claude; export ADLC_HOME
XDG_STATE_HOME=$SBX/state; export XDG_STATE_HOME
ADLC_FORGE_MOCK=1; export ADLC_FORGE_MOCK
ADLC_FORGE_MOCK_STORE=$SBX/store; export ADLC_FORGE_MOCK_STORE
ADLC_RUN_OUTCOMES_LOG=$SBX/outcomes.log; export ADLC_RUN_OUTCOMES_LOG
ADLC_DISABLE_DELEGATE=1; export ADLC_DISABLE_DELEGATE
unset ADLC_TOOLKIT_ROOT GH_TOKEN GITHUB_TOKEN ADLC_EXEC_RUN

printf '#!/bin/sh\nexec python3 "%s" "$@"\n' "$ROOT/tools/adlc/tests/fake_harness/exec_harness.py" > "$SBX/bin/claude"
chmod +x "$SBX/bin/claude"
PATH=$SBX/bin:$PATH; export PATH

BARE=$SBX/acme/widgets.git
REPO=$SBX/widgets
git init -q --bare -b main "$BARE"
git init -q -b main "$REPO"
SPEC=.adlc/specs/REQ-901-thing
mkdir -p "$REPO/$SPEC"
printf -- '---\nid: REQ-901\ntitle: "Thing"\nstatus: approved\ndeployable: false\ncomponent: "adlc/x"\n---\n\n## Description\n' > "$REPO/$SPEC/requirement.md"
printf '.worktrees/\n.adlc/specs/*/pipeline-state.json\n' > "$REPO/.gitignore"
echo seed > "$REPO/README.md"
git -C "$REPO" add -A
git -C "$REPO" commit -qm seed
git -C "$REPO" remote add origin "$BARE"
git -C "$REPO" push -q origin main
REPO=$(CDPATH= cd -P -- "$REPO" && pwd -P)

printf '{"remote": "%s", "owner": "acme", "name": "widgets"}\n' "$BARE" > "$SBX/store/config.json"
LESSON=$(python3 -c 'import json,sys
print(json.dumps(open(sys.argv[1]).read()))' "$ROOT/partials/tests/fixtures/exec-lesson.md")
cat > "$HOME/.exec-scenario.json" <<JSON
{"store": "$SBX/store", "toolkit": "$ROOT", "primary": "$REPO", "repoId": "widgets", "ib": "main",
 "specDirs": {"REQ-901": "$SPEC"}, "reqs": {"REQ-901": {}}, "lesson": $LESSON}
JSON

adlc() { python3 "$ROOT/tools/adlc/adlc.py" "$@"; }

cd "$REPO" || exit 1
adlc sprint-exec run --harness codex --shared-credentials REQ-901 > "$SBX/refused.out" 2>&1
check "a harness with no exec block is refused" "2" "$?"
contains "the refusal names the sibling REQ" "REQ-662" "$(cat "$SBX/refused.out")"

adlc sprint-exec run REQ-901 --shared-credentials --harness-flag=--yolo > "$SBX/refused.out" 2>&1
check "a forbidden flag is refused" "2" "$?"
contains "the refusal names Rule B" "Rule B" "$(cat "$SBX/refused.out")"

adlc sprint-exec run REQ-901 --shared-credentials > "$SBX/sup.out" 2>&1 &
SUP_PID=$!

i=0
while [ "$i" -lt 300 ]; do
  grep -q 'approve: /sprint approve REQ-901' "$SBX/sup.out" 2>/dev/null && break
  sleep 0.1
  i=$((i + 1))
done
contains "the dashboard shows the gate" "Awaiting approval" "$(cat "$SBX/sup.out")"
TOKEN=$(sed -n 's/.*approve REQ-901 --token \([0-9a-f]*\).*/\1/p' "$SBX/sup.out" | head -n 1)
check "a token was printed" "32" "${#TOKEN}"
contains "status has the row" "Awaiting approval" "$(adlc sprint-exec status 2>&1)"
case "$(adlc sprint-exec status 2>&1)" in
  *"$TOKEN"*) fail "status must not print the token" ;;
  *) pass "status does not print the token" ;;
esac

out=$(adlc sprint-exec approve REQ-901 --token 00000000000000000000000000000000 2>&1); rc=$?
check "a wrong token is refused" "2" "$rc"
contains "the refusal names the token" "token" "$out"
out=$(ADLC_EXEC_RUN=REQ-901 adlc sprint-exec approve REQ-901 --token "$TOKEN" 2>&1); rc=$?
check "an approve from inside a run is refused" "2" "$rc"
contains "that refusal names Rule B" "Rule B" "$out"
contains "the dashboard shows the attempt" "from inside a run" "$(adlc sprint-exec status 2>&1)"

out=$(adlc sprint-exec approve REQ-901 --token "$TOKEN" 2>&1); rc=$?
check "the approve is accepted" "0" "$rc"
contains "it reads approved" "approved" "$out"
out=$(adlc sprint-exec approve REQ-901 --token "$TOKEN" 2>&1); rc=$?
check "the token is spent by its first use" "2" "$rc"

i=0
while [ "$i" -lt 300 ] && kill -0 "$SUP_PID" 2>/dev/null; do
  sleep 0.1
  i=$((i + 1))
done
if kill -0 "$SUP_PID" 2>/dev/null; then fail "the supervisor exited"; else pass "the supervisor exited"; fi
wait "$SUP_PID" 2>/dev/null
check "the supervisor's exit status" "0" "$?"
SUP_PID=

STATE=$REPO/$SPEC/pipeline-state.json
field() { python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."):
    d=d[k]
print(d)' "$STATE" "$1"; }
check "status merged" "merged" "$(field status)"
check "the close-out wrote completed" "True" "$(field completed)"
check "closeOut ok" "ok" "$(field closeOut.status)"
check "merged in state" "True" "$(field repos.widgets.merged)"
check "channel shell" "shell" "$(field approval.channel)"
[ -e "$REPO/.worktrees/REQ-901" ] && fail "the worktree was removed" || pass "the worktree was removed"
[ -e "$REPO/.worktrees/REQ-901-close-out" ] && fail "the close-out worktree was removed" || pass "the close-out worktree was removed"
contains "origin carries the feature merge" "REQ-901: thing" "$(git -C "$BARE" log --format=%s main)"
contains "origin carries the chore merge" "close-out" "$(git -C "$BARE" log --format=%s main)"
contains "every merge is pinned" "--match-head-commit" "$(grep pr_merge "$SBX/store/calls.log")"
check "two merges" "2" "$(grep -c '"op": "pr_merge"' "$SBX/store/calls.log")"
contains "the run-outcome line says exec" '"engine":"exec"' "$(tr -d ' ' < "$ADLC_RUN_OUTCOMES_LOG")"

echo ""
if [ "$FAILS" -eq 0 ]; then
  echo "exec-engine.test.sh: ALL CASES PASS"
  exit 0
fi
echo "exec-engine.test.sh: $FAILS FAILURE(S)"
exit 1
