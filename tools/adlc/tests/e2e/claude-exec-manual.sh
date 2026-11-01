#!/bin/bash
# tools/adlc/tests/e2e/claude-exec-manual.sh — the table in
# .adlc/research/harness-probes/claude-exec-manual.md, rerunnable (REQ-659).
#
# Runs the installed `claude -p` in a throwaway repo with a throwaway HOME, under `env -i`,
# so it reads none of the operator's credentials or settings and spends nothing: a logged-out
# run still reads settings, fires hooks, starts MCP servers and writes a transcript
# (LESSON-759). Prints one `<row> <result>` line each and exits non-zero on a surprise. It
# touches no file outside its temp directory, and never passes a bypass flag.
set -u
command -v claude >/dev/null 2>&1 || { echo "claude is not on PATH"; exit 2; }
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
FAILS=0
row() { # row <name> <expected> <actual>
  if [ "$2" = "$3" ]; then echo "$1 pass"; else echo "$1 FAIL: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
BIN=$(dirname "$(command -v claude)")
cl() { env -i HOME="$T/home" PATH="$BIN:/usr/bin:/bin" ADLC_HOME="$T/home/.claude" TERM=dumb claude "$@"; }
sid() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("session_id",""))' "$1" 2>/dev/null; }
key() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(",".join(sorted(k for k in ("type","session_id","is_error","num_turns","result","permission_denials") if k in d)))' "$1" 2>/dev/null; }

mkdir -p "$T/home" "$T/bare"
git init -q --bare "$T/bare/o.git"
git init -q -b main "$T/repo"
git -C "$T/repo" config user.email t@example.invalid
git -C "$T/repo" config user.name t
mkdir -p "$T/repo/.claude"
printf '{"permissions":{"allow":["Read","Bash(ls:*)"]},"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"touch %s/hook-fired"}]}]}}\n' "$T" > "$T/repo/.claude/settings.json"
printf '{"mcpServers":{"x":{"command":"touch","args":["%s/mcp-fired"]}}}\n' "$T" > "$T/repo/.mcp.json"
git -C "$T/repo" add -A
git -C "$T/repo" commit -qm init
git -C "$T/repo" remote add origin "$T/bare/o.git"
git -C "$T/repo" push -q origin main
git -C "$T/repo" worktree add -q -b feat/x "$T/wt1" main
git -C "$T/repo" worktree add -q -b chore/y "$T/wt2" main
mkdir -p "$T/unrelated"

cd "$T/wt1" || exit 2
printf 'hello\n' | cl -p --output-format json --allowedTools Read "Bash(git status:*)" --disallowedTools "Bash(gh pr merge:*)" > "$T/o1.json" 2> "$T/e1"
row stdin-json-exit 1 "$?"
row stdin-json-keys "is_error,num_turns,permission_denials,result,session_id,type" "$(key "$T/o1.json")"
SID=$(sid "$T/o1.json")
row default-launch-hook yes "$([ -e "$T/hook-fired" ] && echo yes || echo no)"
row default-launch-mcp yes "$([ -e "$T/mcp-fired" ] && echo yes || echo no)"

printf 'x\n' | cl -p --resume "$SID" --output-format json > "$T/o2.json" 2>/dev/null
row resume-same-cwd "$SID" "$(sid "$T/o2.json")"
cd "$T/wt2" || exit 2
printf 'x\n' | cl -p --resume "$SID" --output-format json > "$T/o3.json" 2>/dev/null
row resume-sibling "$SID" "$(sid "$T/o3.json")"
cd "$T/unrelated" || exit 2
printf 'x\n' | cl -p --resume "$SID" --output-format json > "$T/o4.json" 2>/dev/null
row resume-unrelated "$SID" "$(sid "$T/o4.json")"
printf 'x\n' | cl -p --resume 00000000-0000-4000-8000-000000000000 --output-format json > "$T/o5.json" 2> "$T/e5"
row resume-control 1 "$?"
case "$(cat "$T/e5")" in *"No conversation found"*) echo "resume-control-message pass" ;; *) row resume-control-message found missing ;; esac

cd "$T/wt2" || exit 2
rm -f "$T/hook-fired" "$T/mcp-fired"
printf '{"permissions":{"allow":["Read"]}}\n' > "$T/s.json"
printf 'x\n' | cl -p --output-format json --setting-sources user --settings "$T/s.json" --strict-mcp-config > /dev/null 2>&1
row isolate-hook no "$([ -e "$T/hook-fired" ] && echo yes || echo no)"
row isolate-mcp no "$([ -e "$T/mcp-fired" ] && echo yes || echo no)"
printf 'x\n' | cl -p --output-format json --setting-sources project,local > /dev/null 2>&1
row isolate-control-hook yes "$([ -e "$T/hook-fired" ] && echo yes || echo no)"
row isolate-control-mcp yes "$([ -e "$T/mcp-fired" ] && echo yes || echo no)"

cl -p --no-such-flag </dev/null >/dev/null 2>"$T/e7"
row unknown-flag 1 "$?"

python3 - "$T" "$T/wt2" <<'PY'
import json, os, sys
path = sys.argv[1] + "/home/.claude.json"
doc = json.load(open(path))
doc.setdefault("projects", {}).setdefault(os.path.realpath(sys.argv[2]), {})["hasTrustDialogAccepted"] = True
json.dump(doc, open(path, "w"))
PY
printf 'x\n' | cl -p --output-format json > /dev/null 2> "$T/e8"
case "$(cat "$T/e8")" in *"Ignoring"*) echo "trust-key-worktree pass" ;; *) row trust-key-worktree notice none ;; esac
python3 - "$T" "$T/repo" <<'PY'
import json, os, sys
path = sys.argv[1] + "/home/.claude.json"
doc = json.load(open(path))
doc.setdefault("projects", {}).setdefault(os.path.realpath(sys.argv[2]), {})["hasTrustDialogAccepted"] = True
json.dump(doc, open(path, "w"))
PY
printf 'x\n' | cl -p --output-format json > /dev/null 2> "$T/e9"
row trust-key-root 0 "$(wc -c < "$T/e9" | tr -d ' ')"
exit "$FAILS"
