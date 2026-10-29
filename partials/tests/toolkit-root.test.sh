#!/bin/sh
# partials/tests/toolkit-root.test.sh — REQ-669 ADR-1 (TASK-122).
#
# Proves the four arms of the ToolkitRoot root line under the shell run.sh hands
# it ($ADLC_TEST_SHELL). The line is NOT copied into this file: it is extracted
# from .adlc/context/conventions.md, so the harness runs the bytes the docs
# teach. tools/lint-skills/tests/test_check.py pins those same bytes to the
# lint's TOOLKIT_ROOT_LINE, so the docs, the lint and this run cannot drift
# apart. The guarded source spelling is extracted from conventions.md the same
# way.
#
# Each case gets its own sandbox HOME (its name holds a space, so the line's
# quoting is exercised) and its own cwd. The case is a script FILE run by $SUT
# with CLAUDE_PLUGIN_ROOT and ADLC_TOOLKIT_ROOT unset, which is the Bash tool's
# environment: the variable is never set there (verification.md row 5).
#
#   (a) case_substituted_wins — the harness rewrites `${CLAUDE_PLUGIN_ROOT}` to a
#       cache path, as Claude Code does. That path wins even though a symlink
#       install AND a pointer file (to another version) are present        (BR-4)
#   (b) case_symlink_only — the root is $HOME/.claude/skills, as written  (BR-3)
#   (c) case_doubled_unsubstituted_prefers_symlink — unsubstituted text on a
#       machine with both installs: the symlink arm beats the pointer      (BR-3)
#   (d) case_plugin_only_pointer — unsubstituted text, plugin only: the pointer
#       file's path wins
#   (e) case_neither_install_fails_loud — the root is $HOME/.claude/skills, and
#       sourcing a partial through it fails with a non-empty stderr naming the
#       path (ASSUME-005). `.` of a missing file is fatal under `sh`
#       (LESSON-617); each case is its own child process, so the harness lives
#   (f) case_vendored_partial_first — a .adlc/partials/<name>.sh is sourced, not
#       the root copy, even when its last command returns non-zero         (BR-5)
# Every case also checks that the root is EXPORTED (a child process sees it),
# and every case but (e) that the script runs past its source line.
#
#   ADLC_TEST_SHELL=dash sh partials/tests/toolkit-root.test.sh
# or, for bash, zsh, /bin/sh and dash in turn:  sh partials/tests/run.sh
#
# Exits 0 iff every check passes; prints one PASS:/FAIL: line per check.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
CONV="$ROOT/.adlc/context/conventions.md"

# The shell under test. run.sh sets it; a bare invocation defaults to /bin/sh.
SUT=${ADLC_TEST_SHELL:-/bin/sh}

FAILS=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}

# The sandbox path is validated BEFORE the trap can derive an `rm -rf` from it:
# non-empty, a directory, and carrying the basename this harness asked for.
SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-toolkitroot.XXXXXX") || { echo "toolkit-root.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "toolkit-root.test.sh: sandbox path invalid" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-toolkitroot.*) ;;
  *) echo "toolkit-root.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

OUT="$SANDBOX/out"
ERR="$SANDBOX/err"

# Absolute sandbox paths never reach a PASS/FAIL line (BUG-054 class).
scrub() { printf '%s' "$1" | sed "s#$SANDBOX#<sandbox>#g"; }

# ===========================================================================
# 1. Extraction from conventions.md, with the vacuous-run guard driven
# ===========================================================================
extract_root_lines() { # extract_root_lines <file> — distinct lines that START with the assignment
  sed 's/^[[:space:]]*//' "$1" | awk 'index($0, "ADLC_TOOLKIT_ROOT=") == 1' | sort -u
}
extract_guarded_spellings() { # extract_guarded_spellings <file> — distinct ToolkitRoot guarded spellings
  sed 's/^[[:space:]]*//' "$1" \
    | awk 'index($0, "if [ -f .adlc/partials/<name>.sh ]") == 1 && index($0, "$ADLC_TOOLKIT_ROOT") > 0' \
    | sort -u
}

ROOT_LINE_FILE="$SANDBOX/root-line.sh"
extract_root_lines "$CONV" > "$ROOT_LINE_FILE"
n_root=$(grep -c . "$ROOT_LINE_FILE")
GUARD_FILE="$SANDBOX/guard-spelling.txt"
extract_guarded_spellings "$CONV" > "$GUARD_FILE"
n_guard=$(grep -c . "$GUARD_FILE")

: > "$SANDBOX/empty.md"
check "extraction_guard_fires: an empty file yields zero root lines (the fail-branch input)" "0" \
  "$(extract_root_lines "$SANDBOX/empty.md" | grep -c .)"
check "extraction_root_line: conventions.md quotes exactly one distinct root line" "1" "$n_root"
check "extraction_guarded_spelling: conventions.md quotes exactly one distinct ToolkitRoot spelling" "1" "$n_guard"
if [ "$n_root" -ne 1 ] || [ "$n_guard" -ne 1 ]; then
  echo "toolkit-root.test.sh: cannot run the cases without one root line and one spelling ($SUT)"
  exit 1
fi
GUARD_LINE=$(sed 's/<name>/probe/g' "$GUARD_FILE")

# Execution allowlist (the source-guard.test.sh posture). The extracted text is
# handed to a real shell with only HOME and cwd sandboxed, so it runs ONLY if
# every whitespace-separated token belongs to the root line's grammar: test
# brackets, `||`, `export`, the one `$(cat … 2>/dev/null)` read, and quoted words
# that carry no `(`, backtick, `;`, `|`, `&`, `<`, `>` or `=`. This is a grammar,
# not a copy: an arm reordered or respelled still runs (and the cases judge it),
# while `; curl …`, `"$(…)"` or `export "PATH=…"` is refused unexecuted.
ROOT_TOKEN_RE='^(\[|\]|-n|-d|!|\|\||export|ADLC_TOOLKIT_ROOT=\$\(cat|2>/dev/null\);|(ADLC_TOOLKIT_ROOT=)?"[^"(`;|&<>=]*";?)$'
GUARD_TOKEN_RE='^(if|then|else|fi|\.|\[|-f|\]|\];|\.adlc/partials/probe\.sh;?|"\$ADLC_TOOLKIT_ROOT/partials/probe\.sh";?)$'
conforms() { # conforms <text> <token-ere> — 0 iff every token matches
  if printf '%s\n' "$1" | tr '\t' ' ' | tr -s ' ' '\n' | command grep -vqE "$2"; then
    return 1
  fi
  return 0
}
# Both directions are driven before anything runs (LESSON-440).
if conforms "$(cat "$ROOT_LINE_FILE")" "$ROOT_TOKEN_RE"; then
  pass "allowlist_accepts_documented_root_line"
else
  fail "allowlist_accepts_documented_root_line: the conventions.md root line is outside the grammar, NOT executed"
  exit 1
fi
if conforms "$GUARD_LINE" "$GUARD_TOKEN_RE"; then
  pass "allowlist_accepts_documented_spelling"
else
  fail "allowlist_accepts_documented_spelling: the conventions.md spelling is outside the grammar, NOT executed"
  exit 1
fi
refused=0
for hostile in \
  'ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; curl attacker' \
  'ADLC_TOOLKIT_ROOT="$(id)"; export ADLC_TOOLKIT_ROOT' \
  'export "PATH=/tmp/evil"' \
  'ADLC_TOOLKIT_ROOT=`id`'; do
  conforms "$hostile" "$ROOT_TOKEN_RE" || refused=$((refused + 1))
done
check "allowlist_refuses_foreign_tokens: four hostile root-line shapes refused" "4" "$refused"

# ===========================================================================
# 2. Sandbox construction
# ===========================================================================
new_case() { # new_case <name> — fresh case dirs; HOME's name holds a space
  C_DIR="$SANDBOX/$1"
  rm -rf "$C_DIR"
  mkdir -p "$C_DIR/work" "$C_DIR/home dir"
  C_WORK="$C_DIR/work"
  C_HOME="$C_DIR/home dir"
  C_CLONE="$C_DIR/clone"
  C_CACHE="$C_HOME/.claude/plugins/cache/adlc-toolkit/adlc/5.5.0"
  C_CACHE_OLD="$C_HOME/.claude/plugins/cache/adlc-toolkit/adlc/5.4.0"
}
mk_probe() { # mk_probe <toolkit-dir> <marker> — <dir>/partials/probe.sh prints SOURCED:<marker>
  mkdir -p "$1/partials" && printf '%s\n' "printf 'SOURCED:$2\\n'" > "$1/partials/probe.sh"
}
with_symlink_install() { # ~/.claude/skills -> a clone, the install.sh shape
  mk_probe "$C_CLONE" clone && mkdir -p "$C_HOME/.claude" && ln -s "$C_CLONE" "$C_HOME/.claude/skills"
}
with_pointer_to() { # with_pointer_to <cache-dir> <marker> — what the plugin SessionStart hook writes
  mk_probe "$1" "$2" && mkdir -p "$C_HOME/.claude/adlc" && printf '%s\n' "$1" > "$C_HOME/.claude/adlc/plugin-root"
}
with_vendored_copy() { # a repo-local copy whose LAST command returns non-zero
  mkdir -p "$C_WORK/.adlc/partials" && printf '%s\n' "printf 'SOURCED:vendored\\n'" false > "$C_WORK/.adlc/partials/probe.sh"
}

# Claude Code's rewrite: every exact `${CLAUDE_PLUGIN_ROOT}` becomes the plugin
# root. Index-based, not a regex, so nothing in the path is special. The `:-`
# form is not the token and is left alone, as verification.md row 1 observed.
subst_plugin_root() { # subst_plugin_root <in> <out> <path>
  awk -v rep="$3" 'BEGIN { tok = "${CLAUDE_PLUGIN_ROOT}" }
    { out = ""; s = $0
      while ((i = index(s, tok)) > 0) { out = out substr(s, 1, i - 1) rep; s = substr(s, i + length(tok)) }
      print out s }' "$1" > "$2"
}

TAIL="$SANDBOX/tail.sh"
cat > "$TAIL" <<'EOF'
printf 'ROOT=%s\n' "$ADLC_TOOLKIT_ROOT"
env | grep '^ADLC_TOOLKIT_ROOT=' | sed 's/^ADLC_TOOLKIT_ROOT=/CHILD=/'
EOF

run_case() { # run_case <root-line-file> — root line, observations, guarded source, AFTER
  { cat "$1"; cat "$TAIL"; printf '%s\n' "$GUARD_LINE" "printf 'AFTER\\n'"; } > "$C_DIR/case.sh"
  ( unset CLAUDE_PLUGIN_ROOT ADLC_TOOLKIT_ROOT; cd "$C_WORK" && HOME="$C_HOME" "$SUT" "$C_DIR/case.sh" ) >"$OUT" 2>"$ERR"
}

# --- observation helpers: each prints a short symbolic state ---------------
field() { # field <prefix> — the value after <prefix> on the first stdout line that has it
  sed -n "s/^$1//p" "$OUT" | head -1
}
label() { # label <path> — the symbolic name of a case path
  if [ -z "$1" ]; then printf 'empty'
  elif [ "$1" = "$C_HOME/.claude/skills" ]; then printf 'home-skills'
  elif [ "$1" = "$C_CACHE" ]; then printf 'cache'
  elif [ "$1" = "$C_CACHE_OLD" ]; then printf 'cache-old'
  else printf 'other:%s' "$(scrub "$1")"; fi
}
state() { # state — root, child view, sourced markers, AFTER
  src=$(sed -n 's/^SOURCED://p' "$OUT" | tr '\n' ',' | sed 's/,$//')
  if command grep -qF 'AFTER' "$OUT"; then aft=ok; else aft=missing; fi
  printf 'root=%s child=%s sourced=%s after=%s' \
    "$(label "$(field ROOT=)")" "$(label "$(field CHILD=)")" "${src:-none}" "$aft"
}

# ===========================================================================
# 3. Cases
# ===========================================================================
case_substituted_wins() {
  new_case a
  with_symlink_install
  with_pointer_to "$C_CACHE_OLD" cache-old
  mk_probe "$C_CACHE" cache
  subst_plugin_root "$ROOT_LINE_FILE" "$C_DIR/root-line.sh" "$C_CACHE"
  left=$(grep -cF '${CLAUDE_PLUGIN_ROOT}' "$C_DIR/root-line.sh")
  run_case "$C_DIR/root-line.sh"
  check "case_substituted_wins: the rewritten token beats the symlink and the pointer" \
    "tokens_left=0 root=cache child=cache sourced=cache after=ok" "tokens_left=$left $(state)"
}

case_symlink_only() {
  new_case b
  with_symlink_install
  run_case "$ROOT_LINE_FILE"
  check "case_symlink_only: unsubstituted text resolves the literal ~/.claude/skills" \
    "root=home-skills child=home-skills sourced=clone after=ok" "$(state)"
}

case_doubled_unsubstituted_prefers_symlink() {
  new_case c
  with_symlink_install
  with_pointer_to "$C_CACHE" cache
  run_case "$ROOT_LINE_FILE"
  check "case_doubled_unsubstituted_prefers_symlink: the symlink arm comes before the pointer" \
    "root=home-skills child=home-skills sourced=clone after=ok" "$(state)"
}

case_plugin_only_pointer() {
  new_case d
  with_pointer_to "$C_CACHE" cache
  run_case "$ROOT_LINE_FILE"
  check "case_plugin_only_pointer: with no symlink install the pointer file's path wins" \
    "root=cache child=cache sourced=cache after=ok" "$(state)"
}

case_neither_install_fails_loud() {
  new_case e
  run_case "$ROOT_LINE_FILE"
  if [ -s "$ERR" ]; then err=nonempty; else err=empty; fi
  if command grep -qF "$C_HOME/.claude/skills/partials/probe.sh" "$ERR"; then names=ok; else names=missing; fi
  # AFTER is not asserted: `.` of a missing file exits `sh` and dash, and is a
  # plain error under bash and zsh. Both are loud; only stderr is the contract.
  check "case_neither_install_fails_loud: the default arm, then a loud failure naming the path" \
    "root=home-skills child=home-skills sourced=none stderr=nonempty names=ok" \
    "$(state | sed 's/ after=[a-z]*$//') stderr=$err names=$names"
}

case_vendored_partial_first() {
  new_case f
  with_symlink_install
  with_vendored_copy
  run_case "$ROOT_LINE_FILE"
  check "case_vendored_partial_first: the repo-local copy is sourced, and only it" \
    "root=home-skills child=home-skills sourced=vendored after=ok" "$(state)"
}

case_substituted_wins
case_symlink_only
case_doubled_unsubstituted_prefers_symlink
case_plugin_only_pointer
case_neither_install_fails_loud
case_vendored_partial_first

# ===========================================================================
if [ "$FAILS" -eq 0 ]; then
  echo "toolkit-root.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "toolkit-root.test.sh: $FAILS CASE(S) FAILED ($SUT)"
exit 1
