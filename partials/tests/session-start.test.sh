#!/bin/sh
# partials/tests/session-start.test.sh — REQ-669 ADR-4, BR-6, BR-7, BR-17, BR-20, AC-5 (TASK-127).
#
# The plugin's SessionStart hook (scripts/session-start.sh) and its CLI shim
# (scripts/adlc), run the way Claude Code runs them: the hook under the shell
# being tested, from a cache-shaped copy of the plugin, with CLAUDE_PLUGIN_ROOT
# and (when a case says so) CLAUDE_ENV_FILE in the environment. Every case has
# its own sandbox HOME, so nothing here reads or writes the real ~/.claude.
#
# Every hook run is also held to the hook contract: exit 0, nothing on stdout (a
# SessionStart hook's stdout becomes session context), at most one stderr line,
# and that line starts `adlc: `.
#
# Cases:
#   case_valid_root_writes_pointer: the pointer holds the root, resolved, and a
#       newline, and a pointer naming an older root is replaced.
#   case_second_run_no_write: a second run rewrites neither file (by mtime).
#   case_invalid_root_rejected_no_write (BR-20): a root that is unset, relative,
#       lacks plugin.json, names a different plugin (author.name "adlc" as the
#       decoy), lacks partials/, holds `..`, a newline, a `$`, a `"`, a backtick,
#       a backslash, a `:` or a `::` writes nothing, not even to CLAUDE_ENV_FILE,
#       and still exits 0 with one `adlc:` line. So does an unset or relative
#       HOME.
#   case_pointer_cache_only (LESSON-718): only a root that resolves under
#       ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/cache/ is recorded. A
#       --plugin-dir style checkout, a cache entry that is a symlink to one, the
#       cache directory itself, and a cache under a relative CLAUDE_CONFIG_DIR
#       never overwrite (or create) the pointer, and the config and PATH steps
#       still run; with CLAUDE_CONFIG_DIR unset or relative, $HOME/.claude is
#       the default and its cache copy is recorded (the benign path).
#   case_existing_config_untouched (BR-6, benign path): a config already there,
#       as a file or a dangling symlink, is left byte-identical.
#   case_config_absent_scaffolded_disabled (BR-6): an absent config is created
#       with `enabled: false`. Byte parity with install.sh is
#       tools/adlc/tests/test_config_scaffold_parity.py.
#   case_config_no_clobber: a config another writer creates after the hook's
#       existence check (a mktemp shim plants it) is kept byte-identical, with
#       no temp file left and no stderr line.
#   case_env_file_path_appended_once (BR-7): across two runs one marked PATH
#       line is appended, after $PATH, on its own line; sourcing the file puts
#       the shim on PATH and `adlc --version` runs.
#   case_env_file_other_root_replaced: a marker line for another root is
#       replaced in place by this root's line (duplicates collapse to one), the
#       other lines are kept, and a second run rewrites nothing.
#   case_env_file_rejected: a relative CLAUDE_ENV_FILE and a directory each get
#       one `adlc:` line and no file, and the pointer and config are still written.
#   case_env_file_unset_no_file: with CLAUDE_ENV_FILE unset the hook creates the
#       two ~/.claude/adlc files and nothing else.
#   case_unwritable_targets_fail_soft: a read-only ~/.claude and a directory at
#       the pointer path each fail soft, exit 0, one `adlc:` line.
#   case_shim_doctor_from_cache_copy (AC-5): scripts/adlc is executable and runs
#       `adlc doctor` from the cache copy with no ~/bin/adlc and no venv. The run
#       sets PYTHONDONTWRITEBYTECODE=1: the Xcode python3 otherwise writes its
#       bytecode under $HOME/Library/Caches/com.apple.python (sys.pycache_prefix),
#       which is not the shim's doing.
#   case_shim_no_python3: with no python3 on PATH the shim exits 127 with one line.
#   case_hook_registration: hooks/hooks.json registers the hook command, and
#       there is no top-level bin/ (BR-20).
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL):
#   ADLC_TEST_SHELL=dash sh partials/tests/session-start.test.sh
# or, for bash, zsh, /bin/sh and dash in turn:  sh partials/tests/run.sh
#
# Exits 0 iff every check passes and the executed-case count clears its floor.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TOOLKIT=$(CDPATH= cd -- "$HERE/../.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}
# The shell's own path, so a case can run it under a PATH that cannot find it.
SUT_BIN=$(command -v "$SUT")

FAILS=0
CASES=0
pass() { echo "PASS: $1"; CASES=$((CASES + 1)); }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
check() { # check <desc> <expected> <actual> — compared raw, printed scrubbed
  if [ "$2" = "$3" ]; then pass "$1 (= $(scrub "$3"))"; else fail "$1 (expected '$(scrub "$2")', got '$(scrub "$3")')"; fi
}

# The sandbox path is validated BEFORE any cleanup can derive an `rm -rf` from
# it: non-empty, a directory, and carrying the basename this harness asked for
# (LESSON-619).
SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-sessionstart.XXXXXX") || { echo "session-start.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "session-start.test.sh: sandbox path invalid" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-sessionstart.*) ;;
  *) echo "session-start.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
# Write bits come back first: the read-only case leaves directories `rm -rf`
# cannot empty.
cleanup() {
  chmod -R u+w "$SANDBOX" 2>/dev/null
  rm -rf "$SANDBOX"
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

# Absolute sandbox paths never reach a PASS/FAIL line (BUG-054 class).
scrub() { printf '%s' "$1" | sed "s#$SANDBOX#<sandbox>#g"; }

unset CLAUDE_PLUGIN_ROOT CLAUDE_ENV_FILE ADLC_TOOLKIT_ROOT CLAUDE_CONFIG_DIR
mkdir -p "$SANDBOX/out" "$SANDBOX/work" "$SANDBOX/homes" "$SANDBOX/roots" || exit 1
WORK="$SANDBOX/work"
NL='
'

# ===========================================================================
# 1. The plugin, as the cache holds it
# ===========================================================================
# What the hook validates (the real manifest, partials/), what it runs from
# (scripts/), and what the shim runs (tools/adlc, VERSION). Test trees and
# bytecode are dropped.
mk_plugin_copy() { # mk_plugin_copy <dir>
  mkdir -p "$1/tools" \
    && cp -R "$TOOLKIT/.claude-plugin" "$TOOLKIT/partials" "$TOOLKIT/scripts" "$TOOLKIT/hooks" "$1/" \
    && cp "$TOOLKIT/VERSION" "$1/" \
    && cp -R "$TOOLKIT/tools/adlc" "$1/tools/" \
    && rm -rf "$1/partials/tests" "$1/tools/adlc/tests" \
    && find "$1" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
}
# The cache sits under $SANDBOX/plugins/cache, so run_hook points
# CLAUDE_CONFIG_DIR at $SANDBOX by default; case_pointer_cache_only covers the
# $HOME/.claude default.
CACHE="$SANDBOX/plugins/cache/adlc-toolkit/adlc/$(cat "$TOOLKIT/VERSION")"
mk_plugin_copy "$CACHE" || { echo "session-start.test.sh: could not build the plugin copy" >&2; exit 1; }
# What the pointer holds: the root resolved with `cd -P` ($TMPDIR is a symlink
# on macOS).
CACHE_REAL=$(CDPATH= cd -P -- "$CACHE" && pwd -P) || exit 1
HOOK="$CACHE/scripts/session-start.sh"
SHIM="$CACHE/scripts/adlc"

# mk_root <dir> <manifest-file|-> <with-partials:1|0> — a candidate plugin root.
mk_root() {
  mkdir -p "$1" || return 1
  if [ "$2" != "-" ]; then mkdir -p "$1/.claude-plugin" && cp "$2" "$1/.claude-plugin/plugin.json" || return 1; fi
  if [ "$3" = 1 ]; then mkdir -p "$1/partials" || return 1; fi
  return 0
}

# ===========================================================================
# 2. Running the hook
# ===========================================================================
# new_home <name> — a fresh, empty sandbox HOME, in $CASE_HOME.
new_home() {
  CASE_HOME="$SANDBOX/homes/$1"
  mkdir -p "$CASE_HOME"
}

# run_hook <run> <plugin-root|-> [<env-file>] — the hook under $SUT, as
# hooks.json runs it, with HOME=$CASE_HOME, CLAUDE_CONFIG_DIR=$SANDBOX and cwd a
# scratch project. `-` leaves CLAUDE_PLUGIN_ROOT unset; no third argument leaves
# CLAUDE_ENV_FILE unset. RH_HOME and RH_CFG, when set, replace HOME and
# CLAUDE_CONFIG_DIR for the run (`-` unsets it); a case resets them after.
RH_HOME=
RH_CFG=
run_hook() {
  ( cd "$WORK" || exit 99
    case $RH_HOME in
      -) unset HOME ;;
      '') HOME=$CASE_HOME; export HOME ;;
      *) HOME=$RH_HOME; export HOME ;;
    esac
    case $RH_CFG in
      -) unset CLAUDE_CONFIG_DIR ;;
      '') CLAUDE_CONFIG_DIR=$SANDBOX; export CLAUDE_CONFIG_DIR ;;
      *) CLAUDE_CONFIG_DIR=$RH_CFG; export CLAUDE_CONFIG_DIR ;;
    esac
    if [ "$2" != "-" ]; then CLAUDE_PLUGIN_ROOT=$2; export CLAUDE_PLUGIN_ROOT; fi
    if [ -n "${3-}" ]; then CLAUDE_ENV_FILE=$3; export CLAUDE_ENV_FILE; fi
    exec "$SUT" "$HOOK" ) </dev/null >"$SANDBOX/out/$1.out" 2>"$SANDBOX/out/$1.err"
  echo "$?" > "$SANDBOX/out/$1.rc"
}
rc_of() { cat "$SANDBOX/out/$1.rc"; }
err_lines() { wc -l < "$SANDBOX/out/$1.err" | tr -d ' '; }

# hook_contract <run> <stderr-lines: 0|1> — exit 0, no stdout, exactly that many
# stderr lines, and every one of them an `adlc:` line.
hook_contract() {
  check "contract: $1 exits 0" "0" "$(rc_of "$1")"
  check "contract: $1 prints nothing on stdout" "0" "$(wc -c < "$SANDBOX/out/$1.out" | tr -d ' ')"
  check "contract: $1 stderr line count" "$2" "$(err_lines "$1")"
  check "contract: $1 stderr is only adlc: lines" "0" "$(command grep -c -v '^adlc: ' "$SANDBOX/out/$1.err")"
}

# listing <dir> — every path under <dir>, relative and sorted ("" when empty).
listing() { ( cd "$1" && find . ! -name . -print | sort | tr '\n' ' ' ); }

# not_newer <desc> <file> — <file> was not rewritten since it was backdated.
backdate() { touch -t 200001010000 "$@"; }
not_newer() {
  check "$1" "" "$(find "$2" -newer "$SANDBOX/stamp" -print)"
}
backdate_ref() { : > "$SANDBOX/stamp" && backdate "$SANDBOX/stamp"; }

# ===========================================================================
# 3. case_valid_root_writes_pointer
# ===========================================================================
new_home valid
run_hook valid "$CACHE"
hook_contract valid 0
if printf '%s\n' "$CACHE_REAL" | cmp -s - "$CASE_HOME/.claude/adlc/plugin-root"; then
  pass "case_valid_root_writes_pointer: plugin-root is the resolved root and one newline"
else
  fail "case_valid_root_writes_pointer: plugin-root is '$(scrub "$(cat "$CASE_HOME/.claude/adlc/plugin-root" 2>/dev/null)")'"
fi
# The ToolkitRoot line's pointer arm reads it back as the root.
check "case_valid_root_writes_pointer: \$(cat plugin-root) is the root" "$CACHE_REAL" "$(cat "$CASE_HOME/.claude/adlc/plugin-root" 2>/dev/null)"
check "case_valid_root_writes_pointer: no temp file left behind" "./config.yml ./plugin-root " "$(listing "$CASE_HOME/.claude/adlc")"

new_home stale
mkdir -p "$CASE_HOME/.claude/adlc" && printf '%s\n' "$SANDBOX/plugins/cache/adlc-toolkit/adlc/0.0.1" > "$CASE_HOME/.claude/adlc/plugin-root"
run_hook stale "$CACHE"
hook_contract stale 0
check "case_valid_root_writes_pointer: a pointer to an older root is replaced" "$CACHE_REAL" "$(cat "$CASE_HOME/.claude/adlc/plugin-root")"

# ===========================================================================
# 4. case_second_run_no_write — by mtime
# ===========================================================================
CASE_HOME="$SANDBOX/homes/valid"
backdate "$CASE_HOME/.claude/adlc/plugin-root" "$CASE_HOME/.claude/adlc/config.yml"
backdate_ref
run_hook again "$CACHE"
hook_contract again 0
not_newer "case_second_run_no_write: plugin-root not rewritten" "$CASE_HOME/.claude/adlc/plugin-root"
not_newer "case_second_run_no_write: config.yml not rewritten" "$CASE_HOME/.claude/adlc/config.yml"
check "case_second_run_no_write: nothing added" "./config.yml ./plugin-root " "$(listing "$CASE_HOME/.claude/adlc")"

# ===========================================================================
# 5. case_invalid_root_rejected_no_write (BR-20)
# ===========================================================================
REAL_MANIFEST="$TOOLKIT/.claude-plugin/plugin.json"
# A different plugin whose author is named adlc: a nested "name" must not pass.
OTHER_MANIFEST="$SANDBOX/other-plugin.json"
cat > "$OTHER_MANIFEST" <<'EOF'
{
  "name": "other",
  "version": "1.0.0",
  "author": {
    "name": "adlc"
  }
}
EOF
# A relative root that resolves, from the hook's cwd, to a valid one.
mk_root "$WORK/relroot" "$REAL_MANIFEST" 1
mk_root "$SANDBOX/roots/nomanifest" - 1
mk_root "$SANDBOX/roots/other" "$OTHER_MANIFEST" 1
mk_root "$SANDBOX/roots/nopartials" "$REAL_MANIFEST" 0
# Valid roots whose PATH spelling is not safe to write. `..` resolves to $CACHE.
DOTDOT="$CACHE/scripts/.."
DOLLAR="$SANDBOX/roots/cost\$HOME"
mk_root "$DOLLAR" "$REAL_MANIFEST" 1
NLROOT="$SANDBOX/roots/new${NL}line"
NL_OK=1
mk_root "$NLROOT" "$REAL_MANIFEST" 1 2>/dev/null || NL_OK=0
# Each is live inside the double-quoted PATH line, and `:` splits it: `co:lon`
# would add `.../co` and `lon/scripts`, and `::` the current directory.
QUOTE="$SANDBOX/roots/q\"uote"
BTICK="$SANDBOX/roots/back\`tick"
BSLASH="$SANDBOX/roots/back\\slash"
COLON="$SANDBOX/roots/co:lon"
DCOLON="$SANDBOX/roots/two::colons"
for r in "$QUOTE" "$BTICK" "$BSLASH" "$COLON" "$DCOLON"; do
  mk_root "$r" "$REAL_MANIFEST" 1 || { echo "session-start.test.sh: could not make $(scrub "$r")" >&2; exit 1; }
done

# reject <run> <root|-> — nothing under HOME, no env file, one adlc: line.
reject() {
  new_home "$1"
  run_hook "$1" "$2" "$SANDBOX/env-$1"
  hook_contract "$1" 1
  check "case_invalid_root_rejected_no_write: $1 wrote nothing under HOME" "" "$(listing "$CASE_HOME")"
  if [ -e "$SANDBOX/env-$1" ]; then
    fail "case_invalid_root_rejected_no_write: $1 created CLAUDE_ENV_FILE"
  else
    pass "case_invalid_root_rejected_no_write: $1 left CLAUDE_ENV_FILE alone"
  fi
}
reject unset -
reject empty ""
reject relative relroot
reject nomanifest "$SANDBOX/roots/nomanifest"
reject otherplugin "$SANDBOX/roots/other"
reject nopartials "$SANDBOX/roots/nopartials"
reject dotdot "$DOTDOT"
reject dollar "$DOLLAR"
reject quote "$QUOTE"
reject backtick "$BTICK"
reject backslash "$BSLASH"
reject colon "$COLON"
reject doublecolon "$DCOLON"
if [ "$NL_OK" = 1 ]; then
  reject newline "$NLROOT"
else
  echo "NOTE: this filesystem refused a newline in a directory name; newline case skipped"
fi
check "case_invalid_root_rejected_no_write: the relative case names the reason" "1" \
  "$(command grep -c 'not an absolute path' "$SANDBOX/out/relative.err")"
check "case_invalid_root_rejected_no_write: the decoy author.name is reported as another plugin" "1" \
  "$(command grep -c 'not the adlc plugin' "$SANDBOX/out/otherplugin.err")"
check "case_invalid_root_rejected_no_write: the colon case names ':'" "1" \
  "$(command grep -c "'..', ':' or a shell metacharacter" "$SANDBOX/out/colon.err")"

# A valid root with an unset or relative HOME: nothing anywhere, one adlc: line.
# Native zsh sets HOME from the password database when it is unset, which would
# be the real one, so the unset case runs only under a shell that leaves it unset.
reject_home() { # reject_home <run> <HOME: - for unset, or a relative path>
  new_home "$1"
  RH_HOME=$2
  run_hook "$1" "$CACHE" "$SANDBOX/env-$1"
  RH_HOME=
  hook_contract "$1" 1
  check "case_invalid_root_rejected_no_write: $1 names HOME" "1" \
    "$(command grep -c 'HOME is unset or not an absolute path; nothing written' "$SANDBOX/out/$1.err")"
  check "case_invalid_root_rejected_no_write: $1 created no CLAUDE_ENV_FILE" "no" \
    "$([ -e "$SANDBOX/env-$1" ] && echo yes || echo no)"
  check "case_invalid_root_rejected_no_write: $1 wrote nothing in the project directory" "no" \
    "$([ -e "$WORK/.claude" ] || [ -e "$WORK/relhome" ] && echo yes || echo no)"
}
SUT_HOME=$( unset HOME; "$SUT" -c 'printf %s "${HOME-}"' 2>/dev/null )
if [ -z "$SUT_HOME" ]; then
  reject_home homeunset -
else
  echo "NOTE: $SUT sets HOME itself when it is unset; the unset-HOME case is skipped under it"
fi
reject_home homerelative relhome

# ===========================================================================
# 6. case_existing_config_untouched (BR-6, benign path)
# ===========================================================================
new_home cfgkept
mkdir -p "$CASE_HOME/.claude/adlc"
printf 'delegate:\n  enabled: true\n  provider: example\n' > "$CASE_HOME/.claude/adlc/config.yml"
cp "$CASE_HOME/.claude/adlc/config.yml" "$SANDBOX/cfgkept.before"
backdate "$CASE_HOME/.claude/adlc/config.yml"
backdate_ref
run_hook cfgkept "$CACHE"
hook_contract cfgkept 0
if cmp -s "$SANDBOX/cfgkept.before" "$CASE_HOME/.claude/adlc/config.yml"; then
  pass "case_existing_config_untouched: an existing config.yml is byte-identical"
else
  fail "case_existing_config_untouched: config.yml changed"
fi
not_newer "case_existing_config_untouched: an existing config.yml is not rewritten" "$CASE_HOME/.claude/adlc/config.yml"
check "case_existing_config_untouched: the run still recorded the root" "$CACHE_REAL" "$(cat "$CASE_HOME/.claude/adlc/plugin-root" 2>/dev/null)"

new_home cfglink
mkdir -p "$CASE_HOME/.claude/adlc" && ln -s "$SANDBOX/nowhere.yml" "$CASE_HOME/.claude/adlc/config.yml"
run_hook cfglink "$CACHE"
hook_contract cfglink 0
check "case_existing_config_untouched: a dangling config.yml symlink is kept" "$SANDBOX/nowhere.yml" "$(readlink "$CASE_HOME/.claude/adlc/config.yml")"
check "case_existing_config_untouched: nothing written through it" "no" "$([ -e "$SANDBOX/nowhere.yml" ] && echo yes || echo no)"

# ===========================================================================
# 7. case_config_absent_scaffolded_disabled (BR-6)
# ===========================================================================
CFG="$SANDBOX/homes/valid/.claude/adlc/config.yml"
check "case_config_absent_scaffolded_disabled: delegate: block" "1" "$(command grep -c -x -F 'delegate:' "$CFG")"
check "case_config_absent_scaffolded_disabled: enabled: false" "1" "$(command grep -c -x -F '  enabled: false' "$CFG")"
check "case_config_absent_scaffolded_disabled: no enabled: true" "0" "$(command grep -c 'enabled:[[:space:]]*true$' "$CFG")"
check "case_config_absent_scaffolded_disabled: ends in a newline" "" "$(tail -c 1 "$CFG")"

# ===========================================================================
# 8. case_env_file_path_appended_once (BR-7)
# ===========================================================================
WANT_LINE="export PATH=\"\$PATH:$CACHE/scripts\" # adlc-plugin-path"
new_home envfile
ENVF="$SANDBOX/session-env/s1/sessionstart-hook-0.sh"
mkdir -p "$(dirname "$ENVF")"
# An earlier writer that left no trailing newline.
printf 'export ADLC_EARLIER=1' > "$ENVF"
run_hook env1 "$CACHE" "$ENVF"
hook_contract env1 0
run_hook env2 "$CACHE" "$ENVF"
hook_contract env2 0
check "case_env_file_path_appended_once: one marker line across two runs" "1" "$(command grep -c -F '# adlc-plugin-path' "$ENVF")"
check "case_env_file_path_appended_once: one PATH line across two runs" "1" "$(command grep -c 'PATH=' "$ENVF")"
check "case_env_file_path_appended_once: the earlier line is intact" "export ADLC_EARLIER=1" "$(sed -n 1p "$ENVF")"
check "case_env_file_path_appended_once: the PATH line is its own line" "$WANT_LINE" "$(sed -n 2p "$ENVF")"
check "case_env_file_path_appended_once: two lines in all" "2" "$(wc -l < "$ENVF" | tr -d ' ')"
# Sourced the way Claude Code's shell sources it: the plugin comes AFTER $PATH.
SOURCED=$( PATH=/usr/bin:/bin; . "$ENVF"; printf '%s' "$PATH" )
check "case_env_file_path_appended_once: appended after \$PATH, not before" "/usr/bin:/bin:$CACHE/scripts" "$SOURCED"
PY_DIR=$(dirname "$(command -v python3)")
ON_PATH=$( PATH="/usr/bin:/bin:$PY_DIR"; . "$ENVF"; command -v adlc )
check "case_env_file_path_appended_once: adlc resolves to the plugin's shim" "$SHIM" "$ON_PATH"
VIA_PATH=$( cd "$WORK" && HOME=$CASE_HOME && export HOME && PATH="/usr/bin:/bin:$PY_DIR" && . "$ENVF" && adlc --version 2>&1 )
check "case_env_file_path_appended_once: adlc --version runs through PATH" "$(cat "$TOOLKIT/VERSION")" "$VIA_PATH"

new_home envabsent
ENVF2="$SANDBOX/session-env/s2/sessionstart-hook-0.sh"
mkdir -p "$(dirname "$ENVF2")"
run_hook envabsent "$CACHE" "$ENVF2"
hook_contract envabsent 0
check "case_env_file_path_appended_once: an absent env file gets just the line" "$WANT_LINE" "$(cat "$ENVF2" 2>/dev/null)"

# ===========================================================================
# 9. case_env_file_unset_no_file
# ===========================================================================
new_home envunset
run_hook envunset "$CACHE"
hook_contract envunset 0
check "case_env_file_unset_no_file: only the two adlc files under HOME" \
  "./.claude ./.claude/adlc ./.claude/adlc/config.yml ./.claude/adlc/plugin-root " "$(listing "$CASE_HOME")"
check "case_env_file_unset_no_file: nothing in the project directory" "./relroot ./relroot/.claude-plugin ./relroot/.claude-plugin/plugin.json ./relroot/partials " "$(listing "$WORK")"

# ===========================================================================
# 9b. case_pointer_cache_only (LESSON-718)
# ===========================================================================
# The pointer is machine-global: only a plugin-cache copy may write it. A
# checkout a session loads with --plugin-dir (or a local-path marketplace's
# source directory) must not become every other session's ToolkitRoot.
DEV="$SANDBOX/dev/adlc-checkout"
mk_plugin_copy "$DEV" || { echo "session-start.test.sh: could not build the dev checkout" >&2; exit 1; }
DEV_LINE="export PATH=\"\$PATH:$DEV/scripts\" # adlc-plugin-path"

# A dev root with a pointer already naming the cache copy: left byte-identical
# and not rewritten, one note, and the config and PATH steps still run.
new_home devptr
mkdir -p "$CASE_HOME/.claude/adlc" && printf '%s\n' "$CACHE_REAL" > "$CASE_HOME/.claude/adlc/plugin-root"
backdate "$CASE_HOME/.claude/adlc/plugin-root"
backdate_ref
run_hook devptr "$DEV" "$SANDBOX/env-devptr"
hook_contract devptr 1
check "case_pointer_cache_only: a dev root leaves the cache copy's pointer" "$CACHE_REAL" "$(cat "$CASE_HOME/.claude/adlc/plugin-root")"
not_newer "case_pointer_cache_only: the pointer is not rewritten" "$CASE_HOME/.claude/adlc/plugin-root"
check "case_pointer_cache_only: the note says why" "1" \
  "$(command grep -c 'not a plugin-cache copy (a --plugin-dir or local-path checkout); ~/.claude/adlc/plugin-root left as it was' "$SANDBOX/out/devptr.err")"
check "case_pointer_cache_only: the config is still scaffolded" "1" "$(command grep -c -x -F '  enabled: false' "$CASE_HOME/.claude/adlc/config.yml" 2>/dev/null)"
check "case_pointer_cache_only: the session's PATH line names the dev root" "$DEV_LINE" "$(cat "$SANDBOX/env-devptr" 2>/dev/null)"
check "case_pointer_cache_only: no temp file left behind" "./config.yml ./plugin-root " "$(listing "$CASE_HOME/.claude/adlc")"

# A dev root and no pointer: none is created, and with nothing left as it was
# there is nothing to report.
new_home devnoptr
run_hook devnoptr "$DEV"
hook_contract devnoptr 0
check "case_pointer_cache_only: a dev root creates no pointer" "./config.yml " "$(listing "$CASE_HOME/.claude/adlc")"

# A cache entry that is a symlink to the dev checkout resolves outside the cache.
LINKED="$SANDBOX/plugins/cache/adlc-toolkit/adlc/9.9.9-link"
ln -s "$DEV" "$LINKED"
new_home cachelink
mkdir -p "$CASE_HOME/.claude/adlc" && printf '%s\n' "$CACHE_REAL" > "$CASE_HOME/.claude/adlc/plugin-root"
run_hook cachelink "$LINKED"
hook_contract cachelink 1
check "case_pointer_cache_only: a symlink in the cache to a checkout is not recorded" "$CACHE_REAL" "$(cat "$CASE_HOME/.claude/adlc/plugin-root")"
rm -f "$LINKED"

# The cache directory itself is not a copy inside it.
CFG_EDGE="$SANDBOX/cfgedge"
mk_root "$CFG_EDGE/plugins/cache" "$REAL_MANIFEST" 1
new_home cacheitself
RH_CFG=$CFG_EDGE
run_hook cacheitself "$CFG_EDGE/plugins/cache"
RH_CFG=
hook_contract cacheitself 0
check "case_pointer_cache_only: the cache directory itself is not recorded" "./config.yml " "$(listing "$CASE_HOME/.claude/adlc")"

# CLAUDE_CONFIG_DIR unset: the cache is $HOME/.claude/plugins/cache, and a copy
# there is recorded (the benign path).
new_home defaultcfg
HOMECACHE="$CASE_HOME/.claude/plugins/cache/adlc-toolkit/adlc/5.0.0"
mk_root "$HOMECACHE" "$REAL_MANIFEST" 1
RH_CFG=-
run_hook defaultcfg "$HOMECACHE"
RH_CFG=
hook_contract defaultcfg 0
check "case_pointer_cache_only: with CLAUDE_CONFIG_DIR unset, ~/.claude's cache copy is recorded" \
  "$(CDPATH= cd -P -- "$HOMECACHE" && pwd -P)" "$(cat "$CASE_HOME/.claude/adlc/plugin-root" 2>/dev/null)"
# ...and the $SANDBOX cache is not ~/.claude's, so its copy is not.
new_home defaultcfg2
RH_CFG=-
run_hook defaultcfg2 "$CACHE"
RH_CFG=
hook_contract defaultcfg2 0
check "case_pointer_cache_only: with CLAUDE_CONFIG_DIR unset, another directory's cache is not recorded" \
  "./config.yml " "$(listing "$CASE_HOME/.claude/adlc")"

# A relative CLAUDE_CONFIG_DIR is not taken: a cache it would name from the cwd
# is not recorded, and the default applies instead.
RELCACHE="$WORK/relcfg/plugins/cache/adlc-toolkit/adlc/5.0.0"
mk_root "$RELCACHE" "$REAL_MANIFEST" 1
new_home relcfg
RH_CFG=relcfg
run_hook relcfg "$RELCACHE"
hook_contract relcfg 0
check "case_pointer_cache_only: a relative CLAUDE_CONFIG_DIR's cache is not recorded" "./config.yml " "$(listing "$CASE_HOME/.claude/adlc")"
new_home relcfg2
HOMECACHE2="$CASE_HOME/.claude/plugins/cache/adlc-toolkit/adlc/5.0.0"
mk_root "$HOMECACHE2" "$REAL_MANIFEST" 1
run_hook relcfg2 "$HOMECACHE2"
RH_CFG=
hook_contract relcfg2 0
check "case_pointer_cache_only: with a relative CLAUDE_CONFIG_DIR, ~/.claude's cache copy is recorded" \
  "$(CDPATH= cd -P -- "$HOMECACHE2" && pwd -P)" "$(cat "$CASE_HOME/.claude/adlc/plugin-root" 2>/dev/null)"
rm -rf "$WORK/relcfg"

# ===========================================================================
# 9c. case_config_no_clobber
# ===========================================================================
# Another writer creates config.yml after the hook's existence check: a mktemp
# shim plants it when the hook asks for the config's temp file. The hook's
# no-clobber `ln` then fails, and the other writer's file stands.
SHIMBIN="$SANDBOX/shim-bin"
REAL_MKTEMP=$(command -v mktemp)
mkdir -p "$SHIMBIN"
printf '#!/bin/sh\ncase $1 in\n  */config.yml.tmp.*) printf "other: writer\\n" > "${1%%.tmp.*}" ;;\nesac\nexec %s "$@"\n' "$REAL_MKTEMP" > "$SHIMBIN/mktemp"
chmod +x "$SHIMBIN/mktemp"
new_home noclobber
( PATH="$SHIMBIN:$PATH"; export PATH; run_hook noclobber "$CACHE" )
hook_contract noclobber 0
check "case_config_no_clobber: the other writer's config stands" "other: writer" "$(cat "$CASE_HOME/.claude/adlc/config.yml" 2>/dev/null)"
check "case_config_no_clobber: no temp file left behind" "./config.yml ./plugin-root " "$(listing "$CASE_HOME/.claude/adlc")"
# The control: the same race against a copy of the hook whose create step is the
# old check-then-`mv -f`. It replaces the other writer's file, so the case above
# can fail, and the shim really plants the file inside the window.
MUTANT="$SANDBOX/mutant-hook.sh"
sed 's/&& ln "\$adlc_ss_tmp" "\$1"; then adlc_ss_rc=0/\&\& mv -f "$adlc_ss_tmp" "$1"; then adlc_ss_rc=0/' "$HOOK" > "$MUTANT"
check "case_config_no_clobber: control: the mutation applied" "1" "$(command grep -c -F 'mv -f "$adlc_ss_tmp" "$1"; then adlc_ss_rc=0' "$MUTANT")"
new_home noclobber2
( PATH="$SHIMBIN:$PATH"; export PATH; HOOK=$MUTANT; run_hook noclobber2 "$CACHE" )
check "case_config_no_clobber: control: check-then-mv replaces the other writer's config" "1" \
  "$(command grep -c -x -F '  enabled: false' "$CASE_HOME/.claude/adlc/config.yml" 2>/dev/null)"
new_home noclobber3
run_hook noclobber3 "$CACHE"
hook_contract noclobber3 0
check "case_config_no_clobber: a single link, not a copy left beside a temp file" "1" \
  "$(ls -l "$CASE_HOME/.claude/adlc/config.yml" | awk '{print $2}')"

# ===========================================================================
# 9d. case_env_file_other_root_replaced
# ===========================================================================
new_home envother
ENVO="$SANDBOX/session-env/s4/sessionstart-hook-0.sh"
mkdir -p "$(dirname "$ENVO")"
printf '%s\n' 'export ADLC_EARLIER=1' 'export PATH="$PATH:/old/plugin/root/scripts" # adlc-plugin-path' 'export ADLC_LATER=1' > "$ENVO"
run_hook envother "$CACHE" "$ENVO"
hook_contract envother 0
check "case_env_file_other_root_replaced: the line before is kept" "export ADLC_EARLIER=1" "$(sed -n 1p "$ENVO")"
check "case_env_file_other_root_replaced: the old root's line is replaced in place" "$WANT_LINE" "$(sed -n 2p "$ENVO")"
check "case_env_file_other_root_replaced: the line after is kept" "export ADLC_LATER=1" "$(sed -n 3p "$ENVO")"
check "case_env_file_other_root_replaced: three lines in all" "3" "$(wc -l < "$ENVO" | tr -d ' ')"
check "case_env_file_other_root_replaced: no temp file left behind" "./sessionstart-hook-0.sh " "$(listing "$(dirname "$ENVO")")"
backdate "$ENVO"
backdate_ref
run_hook envother2 "$CACHE" "$ENVO"
hook_contract envother2 0
not_newer "case_env_file_other_root_replaced: the same root's line is a no-op" "$ENVO"
# A stale line beside the current one: the two collapse to the current one.
printf '%s\n' 'export PATH="$PATH:/old/plugin/root/scripts" # adlc-plugin-path' >> "$ENVO"
run_hook envother3 "$CACHE" "$ENVO"
hook_contract envother3 0
check "case_env_file_other_root_replaced: duplicate marker lines collapse to one" "1" "$(command grep -c -F '# adlc-plugin-path' "$ENVO")"
check "case_env_file_other_root_replaced: and it is this root's" "1" "$(command grep -c -x -F "$WANT_LINE" "$ENVO")"
SOURCED_O=$( PATH=/usr/bin:/bin; . "$ENVO"; printf '%s' "$PATH" )
check "case_env_file_other_root_replaced: the old root is off PATH" "/usr/bin:/bin:$CACHE/scripts" "$SOURCED_O"

# ===========================================================================
# 9e. case_env_file_rejected
# ===========================================================================
new_home envrel
run_hook envrel "$CACHE" "relative/env.sh"
hook_contract envrel 1
check "case_env_file_rejected: a relative CLAUDE_ENV_FILE is named" "1" \
  "$(command grep -c 'CLAUDE_ENV_FILE is not an absolute path; adlc not added to PATH' "$SANDBOX/out/envrel.err")"
check "case_env_file_rejected: no file relative to the cwd" "no" "$([ -e "$WORK/relative" ] && echo yes || echo no)"
check "case_env_file_rejected: the pointer and config are still written" "./config.yml ./plugin-root " "$(listing "$CASE_HOME/.claude/adlc")"
new_home envdir
mkdir -p "$SANDBOX/envdir"
run_hook envdir "$CACHE" "$SANDBOX/envdir"
hook_contract envdir 1
check "case_env_file_rejected: a CLAUDE_ENV_FILE directory is named" "1" \
  "$(command grep -c 'CLAUDE_ENV_FILE is a directory; adlc not added to PATH' "$SANDBOX/out/envdir.err")"
check "case_env_file_rejected: nothing written into it" "" "$(listing "$SANDBOX/envdir")"
check "case_env_file_rejected: the pointer and config are still written (directory case)" "./config.yml ./plugin-root " "$(listing "$CASE_HOME/.claude/adlc")"

# ===========================================================================
# 10. case_unwritable_targets_fail_soft
# ===========================================================================
if [ "$(id -u)" -eq 0 ]; then
  echo "NOTE: uid 0 ignores write bits; the read-only ~/.claude case is skipped"
else
  new_home readonly
  ROENV="$CASE_HOME/.claude/session-env/s3/sessionstart-hook-0.sh"
  mkdir -p "$(dirname "$ROENV")" && : > "$ROENV"
  chmod -R a-w "$CASE_HOME/.claude"
  run_hook readonly "$CACHE" "$ROENV"
  chmod -R u+w "$CASE_HOME/.claude"
  hook_contract readonly 1
  check "case_unwritable_targets_fail_soft: read-only ~/.claude: no adlc directory" "no" "$([ -e "$CASE_HOME/.claude/adlc" ] && echo yes || echo no)"
  check "case_unwritable_targets_fail_soft: read-only ~/.claude: env file still empty" "0" "$(wc -c < "$ROENV" | tr -d ' ')"

  # ~/.claude/adlc exists but is read-only: both writes fail, no temp file stays.
  new_home roadlc
  mkdir -p "$CASE_HOME/.claude/adlc" && chmod a-w "$CASE_HOME/.claude/adlc"
  run_hook roadlc "$CACHE"
  chmod u+w "$CASE_HOME/.claude/adlc"
  hook_contract roadlc 1
  check "case_unwritable_targets_fail_soft: read-only ~/.claude/adlc stays empty" "" "$(listing "$CASE_HOME/.claude/adlc")"
fi

new_home ptrdir
mkdir -p "$CASE_HOME/.claude/adlc/plugin-root"
run_hook ptrdir "$CACHE"
hook_contract ptrdir 1
check "case_unwritable_targets_fail_soft: nothing moved into a plugin-root directory" "" "$(listing "$CASE_HOME/.claude/adlc/plugin-root")"
check "case_unwritable_targets_fail_soft: the config step still ran" "1" "$(command grep -c -x -F '  enabled: false' "$CASE_HOME/.claude/adlc/config.yml" 2>/dev/null)"

# ===========================================================================
# 11. case_shim_doctor_from_cache_copy (AC-5)
# ===========================================================================
check "case_shim_doctor_from_cache_copy: scripts/adlc is executable in the tree" "yes" "$([ -x "$TOOLKIT/scripts/adlc" ] && echo yes || echo no)"
check "case_shim_doctor_from_cache_copy: and in the cache copy" "yes" "$([ -x "$SHIM" ] && echo yes || echo no)"
new_home doctor
( cd "$WORK" && HOME=$CASE_HOME PATH="/usr/bin:/bin:$PY_DIR" PYTHONDONTWRITEBYTECODE=1 "$SUT" "$SHIM" doctor ) \
  </dev/null >"$SANDBOX/out/doctor.out" 2>"$SANDBOX/out/doctor.err"
DOCTOR_RC=$?
check "case_shim_doctor_from_cache_copy: no ~/bin/adlc and no venv" "" "$(listing "$CASE_HOME")"
case $DOCTOR_RC in
  0 | 1) pass "case_shim_doctor_from_cache_copy: doctor ran to a verdict (rc=$DOCTOR_RC)" ;;
  *) fail "case_shim_doctor_from_cache_copy: doctor rc=$DOCTOR_RC: $(scrub "$(head -3 "$SANDBOX/out/doctor.err")")" ;;
esac
check "case_shim_doctor_from_cache_copy: a verdict line" "1" "$(command grep -c '^verdict: ' "$SANDBOX/out/doctor.out")"
check "case_shim_doctor_from_cache_copy: the skills-symlink check ran" "1" "$(command grep -c '\] skills-symlink ' "$SANDBOX/out/doctor.out")"
check "case_shim_doctor_from_cache_copy: no traceback" "0" "$(command grep -c 'Traceback' "$SANDBOX/out/doctor.err")"
VIA_DIR=$( cd "$CACHE/scripts" && HOME=$CASE_HOME PATH="/usr/bin:/bin:$PY_DIR" "$SUT" ./adlc --version 2>&1 )
check "case_shim_doctor_from_cache_copy: a relative invocation finds its root" "$(cat "$TOOLKIT/VERSION")" "$VIA_DIR"

# ===========================================================================
# 12. case_shim_no_python3
# ===========================================================================
NOPY="$SANDBOX/nopy-bin"
mkdir -p "$NOPY" && ln -s "$(command -v dirname)" "$NOPY/dirname"
( cd "$WORK" && HOME=$CASE_HOME PATH="$NOPY" "$SUT_BIN" "$SHIM" doctor ) \
  </dev/null >"$SANDBOX/out/nopy.out" 2>"$SANDBOX/out/nopy.err"
check "case_shim_no_python3: exits 127" "127" "$?"
check "case_shim_no_python3: one stderr line" "1" "$(err_lines nopy)"
check "case_shim_no_python3: it names python3" "1" "$(command grep -c '^adlc: python3 not found' "$SANDBOX/out/nopy.err")"
check "case_shim_no_python3: nothing on stdout" "0" "$(wc -c < "$SANDBOX/out/nopy.out" | tr -d ' ')"

# ===========================================================================
# 13. case_hook_registration (BR-20)
# ===========================================================================
check "case_hook_registration: hooks.json runs the hook with sh from the plugin root" "1" \
  "$(command grep -c -F '"command": "sh \"${CLAUDE_PLUGIN_ROOT}/scripts/session-start.sh\""' "$TOOLKIT/hooks/hooks.json")"
check "case_hook_registration: it is a SessionStart hook" "1" "$(command grep -c -F '"SessionStart"' "$TOOLKIT/hooks/hooks.json")"
check "case_hook_registration: no top-level bin/" "no" "$([ -e "$TOOLKIT/bin" ] && echo yes || echo no)"

# ===========================================================================
# 14. case_adlc_home (REQ-654 BR-1, BR-2, BR-3)
# ===========================================================================
# The config follows ADLC_HOME; the pointer never does, because the root line's
# arm 3 reads it at ~/.claude/adlc/plugin-root by literal. Benign half: unset,
# both land in ~/.claude/adlc (case_valid_root_writes_pointer above).
new_home ahome
AH_DIR="$SANDBOX/adlc home"
ADLC_HOME="$AH_DIR/"; export ADLC_HOME
run_hook ahome "$CACHE"
unset ADLC_HOME
hook_contract ahome 0
check "case_adlc_home: the config is scaffolded under ADLC_HOME" "1" \
  "$(command grep -c -x -F '  enabled: false' "$AH_DIR/adlc/config.yml" 2>/dev/null)"
check "case_adlc_home: the pointer stays at ~/.claude/adlc" "$CACHE_REAL" "$(cat "$CASE_HOME/.claude/adlc/plugin-root" 2>/dev/null)"
check "case_adlc_home: no config under ~/.claude when ADLC_HOME names elsewhere" "./plugin-root " "$(listing "$CASE_HOME/.claude/adlc")"
check "case_adlc_home: nothing else under ADLC_HOME" "./adlc ./adlc/config.yml " "$(listing "$AH_DIR")"
for ahbad in '' 'rel/home'; do
  new_home "ahbad$(printf '%s' "$ahbad" | tr -c 'a-z' '_')"
  ADLC_HOME=$ahbad; export ADLC_HOME
  run_hook ahbad "$CACHE"
  unset ADLC_HOME
  hook_contract ahbad 1
  check "case_adlc_home: ADLC_HOME='$ahbad' — the note names ADLC_HOME" "1" "$(command grep -c 'ADLC_HOME' "$SANDBOX/out/ahbad.err")"
  check "case_adlc_home: ADLC_HOME='$ahbad' — no config written, the pointer still is" "./plugin-root " "$(listing "$CASE_HOME/.claude/adlc")"
done

# ===========================================================================
# Case-count floor: a harness that ran nothing must not read as a pass.
echo "session-start.test.sh: $CASES cases executed"
if [ "$CASES" -lt 100 ]; then
  echo "session-start.test.sh: FAIL — expected at least 100 cases, ran $CASES ($SUT)"
  exit 1
fi
if [ "$FAILS" -eq 0 ]; then
  echo "session-start.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "session-start.test.sh: $FAILS FAILURE(S) ($SUT)"
exit 1
