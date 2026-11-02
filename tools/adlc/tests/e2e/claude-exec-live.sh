#!/bin/bash
# tools/adlc/tests/e2e/claude-exec-live.sh — the REQ-659 rows that need a logged-in `claude`
# (ASSUME-020 to ASSUME-023), rerunnable. Results go in
# .adlc/research/harness-probes/claude-exec-manual.md.
#
# Unlike claude-exec-manual.sh this runs with the operator's real HOME, because the login
# lives there: each run spends a little of the operator's plan, and Claude Code records each
# throwaway folder under `projects` in ~/.claude.json. Remove those entries afterwards.
# Everything else stays in a temp directory: a throwaway repo, a local bare origin, and
# worktrees of it. It never passes a bypass flag, and pushes go only to the local origin.
#
# Each launch uses the engine's own argv (exec_adapter.launch_argv over the claude adapter's
# tiers, with its config-isolation flags and settings file), so a row tests the flags
# `/sprint --exec` really passes. Isolation means the operator's ~/.claude/settings.json is
# not read: before BUG-260 it was, and its `Bash(git push:*)` re-admitted what the tiers
# withhold. A row prints
# `<row> <result> <detail>`.
# Usage: claude-exec-live.sh [row...]   (default: every row)
# ADLC_LIVE_KEEP=<dir> copies each run's JSON and stderr there before the temp dir goes.

set -u
HERE=$(cd "$(dirname "$0")" && pwd)
TOOLS=$(cd "$HERE/../.." && pwd)
claude auth status 2>/dev/null | grep -q '"loggedIn": true' || { echo "claude is not logged in: run claude /login" >&2; exit 2; }
T=$(mktemp -d -t adlc-exec-live) || exit 2
export T
trap '[ -n "${ADLC_LIVE_KEEP:-}" ] && mkdir -p "$ADLC_LIVE_KEEP" && cp "$T"/*.json "$T"/*.err "$ADLC_LIVE_KEEP"/ 2>/dev/null; rm -rf "$T"' EXIT
BRANCH=feat/REQ-901-live
ROWS=${*:-"allow-untrusted allow-engine-only outside-tier deny-over-allow force-own-branch extra-refspec-main fence resume-sibling"}

# The engine's argv for this branch, NUL-separated; extra deny entries come after `--`.
argv_for() { python3 - "$TOOLS" "$BRANCH" "$@" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import exec_adapter as ea
a = ea.load("claude")
allow, deny = a.tiers(sys.argv[2], ())
rest = sys.argv[3:]
resume = None
if rest and rest[0] == "--resume":
    resume, rest = rest[1], rest[2:]
deny = deny + rest
import json, os
settings = os.path.join(os.environ["T"], "settings.json")
json.dump(a.settings_document(allow, deny), open(settings, "w"))
iso = a.isolation_flags(settings)
sys.stdout.write("\0".join(a.launch_argv("claude", allow, deny, resume=resume, extra=iso)) + "\0")
PY
}
# launch <dir> <out-stem> <prompt> [--resume <sid>] [extra deny...]
launch() {
  dir=$1; stem=$2; prompt=$3; shift 3
  ARGV=()
  while IFS= read -r -d '' a; do ARGV+=("$a"); done < <(argv_for "$@")
  ( cd "$dir" && printf '%s\n' "$prompt" | python3 -c '
import subprocess, sys
try:
    sys.exit(subprocess.run(sys.argv[1:], timeout=240).returncode)
except subprocess.TimeoutExpired:
    sys.exit(124)' "${ARGV[@]}" > "$T/$stem.json" 2> "$T/$stem.err" )
  echo $?
}
field() { python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("unparsable"); sys.exit()
v = d.get(sys.argv[2])
if sys.argv[2] == "permission_denials":
    print(len(v or []))
else:
    print(str(v)[:160].replace("\n", " "))' "$1" "$2"; }
say() { printf '%s %s %s\n' "$1" "$2" "$3"; }

git init -q --bare "$T/o.git"
git init -q -b main "$T/repo"
git -C "$T/repo" config user.email t@example.invalid
git -C "$T/repo" config user.name t
mkdir -p "$T/repo/.adlc/partials"
printf 'live_marker() { touch fence-ran; }\n' > "$T/repo/.adlc/partials/live-marker.sh"
git -C "$T/repo" add -A && git -C "$T/repo" commit -qm init
git -C "$T/repo" remote add origin "$T/o.git"
git -C "$T/repo" push -q origin main
git -C "$T/repo" worktree add -q -b "$BRANCH" "$T/wt" main
git -C "$T/wt" commit -q --allow-empty -m one && git -C "$T/wt" push -q origin "$BRANCH"
git -C "$T/repo" worktree add -q -b chore/REQ-901-close-out "$T/wt2" main

for row in $ROWS; do
  case $row in
  allow-untrusted)   # ASSUME-020: a routine command runs in a never-trusted folder.
    printf 'x\n' > "$T/wt/marker.txt"
    rc=$(launch "$T/wt" a1 'Run exactly this one shell command and nothing else, then reply DONE: git add marker.txt')
    staged=$(git -C "$T/wt" diff --cached --name-only)
    [ "$staged" = marker.txt ] && r=pass || r=FAIL
    say "$row" "$r" "rc=$rc staged=$staged denials=$(field "$T/a1.json" permission_denials)" ;;
  allow-engine-only) # ASSUME-020 control: an allow only the engine's tier carries, not
                     # the operator's ~/.claude/settings.json (which allows git add).
    rc=$(launch "$T/wt" a1b 'Run exactly this one shell command and nothing else, then reply DONE: git config user.name livecheck')
    got=$(git -C "$T/wt" config user.name)
    [ "$got" = livecheck ] && r=pass || r=FAIL
    say "$row" "$r" "rc=$rc user.name=$got denials=$(field "$T/a1b.json" permission_denials)" ;;
  outside-tier)      # ASSUME-021b: a command in neither tier is denied, not run or prompted.
    rc=$(launch "$T/wt" a2 'Run exactly this one shell command and nothing else, then reply DONE: chmod 600 marker.txt')
    mode=$(stat -f %Lp "$T/wt/marker.txt" 2>/dev/null)
    [ "$mode" != 600 ] && r=pass || r=FAIL
    say "$row" "$r" "rc=$rc mode=$mode denials=$(field "$T/a2.json" permission_denials)" ;;
  deny-over-allow)   # ASSUME-021a: a deny that matches wins over an allow that matches.
    git -C "$T/wt" commit -q --amend --allow-empty -m one-amended
    before=$(git -C "$T/o.git" rev-parse "$BRANCH")
    rc=$(launch "$T/wt" a3 "Run exactly this one shell command and nothing else, then reply DONE: git push -u origin $BRANCH --force" "Bash(git push -u origin $BRANCH --force:*)")
    after=$(git -C "$T/o.git" rev-parse "$BRANCH")
    [ "$before" = "$after" ] && r=pass || r=FAIL
    say "$row" "$r" "rc=$rc remote-moved=$([ "$before" = "$after" ] && echo no || echo yes) denials=$(field "$T/a3.json" permission_denials)" ;;
  force-own-branch)  # BUG-260: the engine's own tiers refuse a force flag after the branch.
    git -C "$T/wt" commit -q --amend --allow-empty -m one-amended-again
    before=$(git -C "$T/o.git" rev-parse "$BRANCH")
    rc=$(launch "$T/wt" a4 "Run exactly this one shell command and nothing else, then reply DONE: git push -u origin $BRANCH --force")
    after=$(git -C "$T/o.git" rev-parse "$BRANCH")
    [ "$before" = "$after" ] && r=pass || r=FAIL
    say "$row" "$r" "rc=$rc remote-moved=$([ "$before" = "$after" ] && echo no || echo yes) denials=$(field "$T/a4.json" permission_denials)" ;;
  extra-refspec-main) # BUG-260: the branch push allow admits no second refspec.
    git -C "$T/repo" commit -q --allow-empty -m main-ahead
    before=$(git -C "$T/o.git" rev-parse main)
    rc=$(launch "$T/wt" a8 "Run exactly this one shell command and nothing else, then reply DONE: git push -u origin $BRANCH main")
    after=$(git -C "$T/o.git" rev-parse main)
    [ "$before" = "$after" ] && r=pass || r=FAIL
    say "$row" "$r" "rc=$rc remote-main-moved=$([ "$before" = "$after" ] && echo no || echo yes) denials=$(field "$T/a8.json" permission_denials)" ;;
  fence)             # ASSUME-022: a multi-statement partial-sourcing fence runs.
    fence='ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; export ADLC_TOOLKIT_ROOT
if [ -f .adlc/partials/live-marker.sh ]; then . .adlc/partials/live-marker.sh; else . "$ADLC_TOOLKIT_ROOT/partials/live-marker.sh"; fi
live_marker'
    rc=$(launch "$T/wt" a5 "Run this shell block exactly as written, as one Bash tool call, and nothing else, then reply DONE:
$fence")
    [ -e "$T/wt/fence-ran" ] && r=pass || r=FAIL
    say "$row" "$r" "rc=$rc ran=$([ -e "$T/wt/fence-ran" ] && echo yes || echo no) denials=$(field "$T/a5.json" permission_denials)" ;;
  resume-sibling)    # ASSUME-023: --resume from a sibling worktree continues the conversation.
    nonce=$(LC_ALL=C tr -dc 'a-z' < /dev/urandom | head -c 8)
    rc1=$(launch "$T/wt" a6 "Remember this word for later: $nonce. Reply OK and run no tools.")
    sid=$(field "$T/a6.json" session_id)
    rc2=$(launch "$T/wt2" a7 'What word did I ask you to remember? Reply with the word only and run no tools.' --resume "$sid")
    got=$(field "$T/a7.json" result)
    case "$got" in *"$nonce"*) r=pass ;; *) r=FAIL ;; esac
    say "$row" "$r" "rc=$rc1/$rc2 got=$got" ;;
  esac
done
