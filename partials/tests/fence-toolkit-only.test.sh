#!/bin/sh
# partials/tests/fence-toolkit-only.test.sh — REQ-682 ADR-4 (TASK-245).
#
# Under `fence-run` the runner sets ADLC_FENCE_TOOLKIT_ONLY=1, and no partial may then
# load code from the working copy, which the exec model can write: not the fence's own
# source line (the runner rewrites that), and not a partial that another partial sources.
# This harness proves the closure by DECOYS, not by a list:
#
#   arms_are_enumerated        every partials/*.sh line that sources `.adlc/partials/…`, or
#                              runs a cwd-relative `tools/` or `.adlc/tools/` file, carries
#                              the gate; a new ungated arm is a FAILURE here (BR-3)
#   decoys_never_run_with_flag each gated source line, extracted verbatim, run under the
#                              shell under test from a working copy whose
#                              `.adlc/partials/<name>.sh` is a decoy: with the flag the
#                              ToolkitRoot copy is sourced, never the decoy (BR-3)
#   forge_config_toolkit_only  `_adlc_forge_py` runs ToolkitRoot's forge_config.py with the
#                              flag, never `tools/adlc/` or `.adlc/tools/adlc/`'s (BR-3)
#   delegate_tools_toolkit_only `$DELEGATE_TOOLS` names ToolkitRoot with the flag, never the
#                              project-local `tools/delegate` (BR-3)
#   every_partial_sources_clean sourcing every partial, with every decoy planted and the
#                              flag set, writes no sentinel (BR-3)
#   arms_unchanged_without_flag the same lines and functions with the flag unset take the
#                              working-copy arm exactly as before (BR-10, benign path)
#
# The shell under test is $ADLC_TEST_SHELL (default /bin/sh); run.sh drives bash, zsh,
# /bin/sh and dash. Exits 0 iff every case passes; prints one PASS:/FAIL: line per case.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
ROOT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}

FAILS=0
CASES=0
pass() { echo "PASS: $1"; CASES=$((CASES + 1)); }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-fto.XXXXXX") || { echo "fence-toolkit-only: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "fence-toolkit-only: sandbox path invalid" >&2; exit 1; }
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

HOME="$SANDBOX/home"
export HOME
mkdir -p "$HOME"
unset ADLC_TOOLKIT_ROOT CLAUDE_PLUGIN_ROOT ADLC_HOME ADLC_CONFIG ADLC_FENCE_TOOLKIT_ONLY

WC="$SANDBOX/wc"
FAKE_TK="$SANDBOX/tk"
SENT="$SANDBOX/sentinel"
LOG="$SANDBOX/log"
mkdir -p "$WC/.adlc/partials" "$WC/tools/delegate" "$WC/tools/adlc" "$WC/.adlc/tools/adlc" \
  "$FAKE_TK/partials" "$SANDBOX/bin"

# The decoys: every working-copy arm a partial could reach writes the sentinel.
for f in "$PARTIALS"/*.sh; do
  n=$(basename "$f" .sh)
  printf 'echo "wc:%s" >> "%s"\n' "$n" "$SENT" > "$WC/.adlc/partials/$n.sh"
  printf 'echo "tk:%s" >> "%s"\n' "$n" "$LOG" > "$FAKE_TK/partials/$n.sh"
done
for s in emit-telemetry.sh skill-flag.sh check-delegation.sh emit-run-outcome.sh; do
  printf '#!/bin/sh\necho "wc:tools/delegate/%s" >> "%s"\n' "$s" "$SENT" > "$WC/tools/delegate/$s"
  chmod +x "$WC/tools/delegate/$s"
done
printf 'import sys\nopen("%s", "a").write("wc:tools/adlc/forge_config.py\\n")\n' "$SENT" \
  > "$WC/tools/adlc/forge_config.py"
printf 'import sys\nopen("%s", "a").write("wc:.adlc/tools/adlc/forge_config.py\\n")\n' "$SENT" \
  > "$WC/.adlc/tools/adlc/forge_config.py"
# A recording python3 first on PATH: logs the script it was handed, then runs nothing.
REAL_PY=$(command -v python3)
printf '#!/bin/sh\necho "py:$1" >> "%s"\nexit 0\n' "$LOG" > "$SANDBOX/bin/python3"
chmod +x "$SANDBOX/bin/python3"

# ---------------------------------------------------------------- arms_are_enumerated
# A source line of a working-copy partial, or a cwd-relative tools/ executable test.
ARMS="$SANDBOX/arms"
grep -n -E '\. \.adlc/partials/|\[ -x "tools/|\[ -f "\$adlc_fp_(local|vend)" \]' "$PARTIALS"/*.sh \
  | grep -v -E '^[^:]+:[0-9]+:[[:space:]]*#' > "$ARMS"
n_arms=$(wc -l < "$ARMS" | tr -d ' ')
if [ "$n_arms" -lt 9 ]; then
  fail "arms_are_enumerated: only $n_arms arms found — the extraction rotted"
else
  ungated=$(grep -v 'ADLC_FENCE_TOOLKIT_ONLY' "$ARMS")
  if [ -z "$ungated" ]; then
    pass "arms_are_enumerated: $n_arms working-copy arms, every one gated"
  else
    fail "arms_are_enumerated: ungated arm(s): $ungated"
  fi
fi

# ------------------------------------------------- decoys_never_run_with_flag + benign
# Every gated source line, extracted verbatim (leading blanks dropped), run under the
# shell under test from the working copy, with ToolkitRoot a fake whose copies log.
GATED_LINES="$SANDBOX/lines"
grep -h -E '^[[:space:]]*if \[ "\$\{ADLC_FENCE_TOOLKIT_ONLY:-0\}" != 1 \] && \[ -f \.adlc/partials/' \
  "$PARTIALS"/*.sh | sed 's/^[[:space:]]*//' | sort -u > "$GATED_LINES"
n_lines=$(wc -l < "$GATED_LINES" | tr -d ' ')
if [ "$n_lines" -lt 4 ]; then
  fail "decoys_never_run_with_flag: only $n_lines gated source lines extracted"
fi
i=0
# A line reaches a shell only if it is the gated canonical spelling, whole (LESSON-619): the
# extraction is a prefix match, so anything a partial appended after the guard would run.
GATED_RE='^if \[ "\$\{ADLC_FENCE_TOOLKIT_ONLY:-0\}" != 1 \] && \[ -f \.adlc/partials/([a-z0-9-]+)\.sh \]; then \. \.adlc/partials/[a-z0-9-]+\.sh; else \. "\$\{ADLC_TOOLKIT_ROOT:-\$HOME/\.claude/skills\}/partials/[a-z0-9-]+\.sh"; fi$'
while IFS= read -r line; do
  i=$((i + 1))
  if ! printf '%s\n' "$line" | grep -Eq "$GATED_RE"; then
    fail "decoys_never_run_with_flag: not the gated canonical spelling, never executed: $line"
    continue
  fi
  name=$(printf '%s\n' "$line" | sed -E 's/.*\[ -f \.adlc\/partials\/([A-Za-z0-9_-]+)\.sh \].*/\1/')
  : > "$SENT"; : > "$LOG"
  (cd "$WC" && ADLC_FENCE_TOOLKIT_ONLY=1 ADLC_TOOLKIT_ROOT="$FAKE_TK" "$SUT" -c "$line")
  check "decoys_never_run_with_flag[$name]: toolkit copy sourced" "tk:$name" "$(cat "$LOG")"
  check "decoys_never_run_with_flag[$name]: no decoy" "" "$(cat "$SENT")"
  : > "$SENT"; : > "$LOG"
  (cd "$WC" && ADLC_TOOLKIT_ROOT="$FAKE_TK" "$SUT" -c "$line")
  check "arms_unchanged_without_flag[$name]: working-copy copy first, as before" "wc:$name" \
    "$(cat "$SENT")$(cat "$LOG")"
done < "$GATED_LINES"
# Both directions of that allowlist, in the same run (LESSON-619, LESSON-440).
canon='if [ "${ADLC_FENCE_TOOLKIT_ONLY:-0}" != 1 ] && [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/forge.sh"; fi'
printf '%s\n' "$canon" | grep -Eq "$GATED_RE" && pass "gated_line_allowlist: the canonical gated line conforms" \
  || fail "gated_line_allowlist: the canonical gated line does not conform"
printf '%s; touch %s\n' "$canon" "$SENT" | grep -Eq "$GATED_RE" \
  && fail "gated_line_allowlist: a line with a tail after the guard conforms" \
  || pass "gated_line_allowlist: a line with a tail after the guard is refused"

# ---------------------------------------------------------- forge_config_toolkit_only
: > "$SENT"; : > "$LOG"
(cd "$WC" && PATH="$SANDBOX/bin:$PATH" ADLC_FENCE_TOOLKIT_ONLY=1 ADLC_TOOLKIT_ROOT="$ROOT" "$SUT" -c \
  '. "$1/partials/forge.sh"; _adlc_forge_py . --probe' _ "$ROOT")
check "forge_config_toolkit_only: ToolkitRoot's forge_config.py runs" \
  "py:$ROOT/tools/adlc/forge_config.py" "$(cat "$LOG")"
check "forge_config_toolkit_only: no working-copy forge_config.py" "" "$(cat "$SENT")"
: > "$SENT"; : > "$LOG"
(cd "$WC" && PATH="$SANDBOX/bin:$PATH" ADLC_TOOLKIT_ROOT="$ROOT" "$SUT" -c \
  '. "$1/partials/forge.sh"; _adlc_forge_py . --probe' _ "$ROOT")
check "arms_unchanged_without_flag[forge_config]: the repo's own copy first, as before" \
  "py:./tools/adlc/forge_config.py" "$(cat "$LOG")"
rm -f "$WC/tools/adlc/forge_config.py"
: > "$LOG"
(cd "$WC" && PATH="$SANDBOX/bin:$PATH" ADLC_TOOLKIT_ROOT="$ROOT" "$SUT" -c \
  '. "$1/partials/forge.sh"; _adlc_forge_py . --probe' _ "$ROOT")
check "arms_unchanged_without_flag[forge_config]: then the vendored copy, as before" \
  "py:./.adlc/tools/adlc/forge_config.py" "$(cat "$LOG")"
printf 'import sys\nopen("%s", "a").write("wc:tools/adlc/forge_config.py\\n")\n' "$SENT" \
  > "$WC/tools/adlc/forge_config.py"

# ---------------------------------------------------------- delegate_tools_toolkit_only
got=$(cd "$WC" && ADLC_FENCE_TOOLKIT_ONLY=1 ADLC_TOOLKIT_ROOT="$ROOT" "$SUT" -c \
  '. "$1/partials/delegate-tools-path.sh"; printf %s "$DELEGATE_TOOLS"' _ "$ROOT")
check "delegate_tools_toolkit_only: DELEGATE_TOOLS is ToolkitRoot's" "$ROOT/tools/delegate" "$got"
got=$(cd "$WC" && ADLC_FENCE_TOOLKIT_ONLY=1 ADLC_TOOLKIT_ROOT="$SANDBOX/no-such-root" "$SUT" -c \
  '. "$1/partials/delegate-tools-path.sh"; printf %s "$DELEGATE_TOOLS"' _ "$ROOT")
check "delegate_tools_toolkit_only: never the cwd-relative default either" \
  "$SANDBOX/no-such-root/tools/delegate" "$got"
got=$(cd "$WC" && ADLC_TOOLKIT_ROOT="$ROOT" "$SUT" -c \
  '. "$1/partials/delegate-tools-path.sh"; printf %s "$DELEGATE_TOOLS"' _ "$ROOT")
check "arms_unchanged_without_flag[delegate-tools]: project-local first, as before" \
  "tools/delegate" "$got"
got=$(cd "$WC" && ADLC_FENCE_TOOLKIT_ONLY=1 ADLC_TOOLKIT_ROOT="$ROOT" "$SUT" -c \
  '. "$1/partials/emit-step-telemetry.sh"; printf %s "$DELEGATE_TOOLS"' _ "$ROOT")
check "delegate_tools_toolkit_only[emit-step-telemetry]: nested resolution is ToolkitRoot's" \
  "$ROOT/tools/delegate" "$got"

# ---------------------------------------------------------- every_partial_sources_clean
: > "$SENT"
for f in "$PARTIALS"/*.sh; do
  (cd "$WC" && PATH="$SANDBOX/bin:$PATH" ADLC_FENCE_TOOLKIT_ONLY=1 ADLC_TOOLKIT_ROOT="$ROOT" \
     "$SUT" -c '. "$1"' _ "$f" >/dev/null 2>&1 </dev/null)
done
(cd "$WC" && PATH="$SANDBOX/bin:$PATH" ADLC_FENCE_TOOLKIT_ONLY=1 ADLC_TOOLKIT_ROOT="$ROOT" "$SUT" -c \
  '. "$1/partials/lessons.sh"; command -v _adlc_forge_python >/dev/null && echo ok' _ "$ROOT" \
  > "$SANDBOX/lessons.out" 2>/dev/null)
check "every_partial_sources_clean: lessons.sh loads forge.sh from ToolkitRoot" "ok" \
  "$(cat "$SANDBOX/lessons.out")"
check "every_partial_sources_clean: no decoy ran" "" "$(cat "$SENT")"

: "${REAL_PY:=}"
if [ "$FAILS" -eq 0 ] && [ "$CASES" -gt 0 ]; then
  echo "fence-toolkit-only: $CASES case(s) passed"
  exit 0
fi
[ "$CASES" -gt 0 ] || echo "fence-toolkit-only: zero cases ran — vacuous" >&2
echo "fence-toolkit-only: $FAILS of $CASES case(s) failed" >&2
exit 1
