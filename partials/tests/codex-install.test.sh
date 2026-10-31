#!/bin/sh
# partials/tests/codex-install.test.sh — REQ-655 BR-8, BR-12.
#
# Runs the delegation installer's Codex block, extracted from tools/delegate/install.sh
# so the harness executes the bytes that ship, under the shell run.sh hands it
# ($ADLC_TEST_SHELL), with a sandbox HOME and a stub `codex`:
#   (a) no binary on PATH: nothing under the sandbox's home, and the output says so
#   (b) binary and delegation present: the routing block and the rules, once
#   (c) a second run reports them present and changes neither file
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
SUT=${ADLC_TEST_SHELL:-sh}
FAILS=0
ok() { echo "ok   $1"; }
bad() { echo "FAIL $1"; FAILS=$((FAILS + 1)); }

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-codex-install.XXXXXX") || exit 1
trap 'rm -rf "$SANDBOX"' EXIT
HOME_DIR="$SANDBOX/home"
BIN="$SANDBOX/bin"
VENV="$SANDBOX/venv"
mkdir -p "$HOME_DIR/bin" "$BIN" "$VENV/bin"
ln -s "$(command -v python3)" "$VENV/bin/python3"
printf '#!/bin/sh\necho stub\n' > "$HOME_DIR/bin/adlc-read"
chmod +x "$HOME_DIR/bin/adlc-read"

BLOCK="$SANDBOX/block.sh"
{
  printf 'set -eu\n'
  printf 'VENV_DIR=%s\nREPO_ROOT=%s\n' "'$VENV'" "'$ROOT'"
  awk '/^# --- the same routing for Codex CLI/{f=1} /^# --- next steps/{f=0} f' \
    "$ROOT/tools/delegate/install.sh"
} > "$BLOCK"

run_block() { # run_block <PATH>
  (cd "$SANDBOX" && env -i HOME="$HOME_DIR" ADLC_HOME="$HOME_DIR/.claude" PATH="$1" \
    PYTHONDONTWRITEBYTECODE=1 "$SUT" "$BLOCK")
}

out=$(run_block "/usr/bin:/bin" 2>&1)
if [ -e "$HOME_DIR/.codex" ]; then bad "absent: wrote under the home"; else ok "absent: nothing written"; fi
case "$out" in
  *"not detected"*) ok "absent: says so" ;;
  *) bad "absent: output was: $out" ;;
esac

printf '#!/bin/sh\necho "codex-cli 0.0.0"\n' > "$BIN/codex"
chmod +x "$BIN/codex"
out=$(run_block "$BIN:/usr/bin:/bin" 2>&1) || bad "present: exit status: $out"
RULES="$HOME_DIR/.codex/rules/adlc.rules"
ROUTING="$HOME_DIR/.codex/AGENTS.md"
if [ "$(grep -c '^prefix_rule' "$RULES" 2>/dev/null)" = 3 ]; then ok "present: three rules"; else bad "present: rules"; fi
if [ "$(grep -c 'delegate-routing:start' "$ROUTING" 2>/dev/null)" = 1 ]; then ok "present: one block"; else bad "present: routing"; fi

before=$(cat "$RULES" "$ROUTING")
out=$(run_block "$BIN:/usr/bin:/bin" 2>&1)
if [ "$before" = "$(cat "$RULES" "$ROUTING")" ]; then ok "second run: unchanged"; else bad "second run: changed"; fi
case "$out" in
  *"already present"*) ok "second run: reports it" ;;
  *) bad "second run: output was: $out" ;;
esac

[ "$FAILS" -eq 0 ]
