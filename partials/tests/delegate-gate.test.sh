#!/bin/sh
# partials/tests/delegate-gate.test.sh — arm ordering and reason strings for
# partials/delegate-gate.sh (REQ-515 BR-11, BUG-205).
#
# Fully offline. `adlc-read` is replaced by a scripted stub on PATH: the Python
# resolver's own correctness is covered by tools/delegate/tests/test_resolve_provider.py,
# and what belongs HERE is the shell's arm ordering, its fail-closed posture, and
# whether it forks at all. A stub is the only way to assert the last two.
#
# Run under BOTH shells (BR-6 — the gate must behave identically under the
# operator's zsh and under sh):
#   bash partials/tests/delegate-gate.test.sh
#   zsh  partials/tests/delegate-gate.test.sh
# or via the wrapper:  sh partials/tests/run.sh
#
# Exits 0 iff every case passes; prints one line per case.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)

FAILS=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}

SANDBOX=$(mktemp -d 2>/dev/null || mktemp -d -t adlc-gate)
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

BIN="$SANDBOX/bin"; mkdir -p "$BIN"
FAKEHOME="$SANDBOX/home"; mkdir -p "$FAKEHOME"

# --- the stub ---------------------------------------------------------------
# Prints whatever $STUB_OUT holds and exits $STUB_RC, and appends a line to
# $SANDBOX/calls every time it runs so a test can assert the gate did (or did
# not) fork. --version is answered so nothing else in the gate trips on it.
cat > "$BIN/adlc-read" <<'STUB'
#!/bin/sh
echo "called" >> "$STUB_CALLS"
[ "${STUB_OUT-}" = "__none__" ] || printf '%s\n' "${STUB_OUT-}"
exit "${STUB_RC:-0}"
STUB
chmod +x "$BIN/adlc-read"

CFG_TRUE="$SANDBOX/true.yml";   printf 'delegate:\n  enabled: true\n'  > "$CFG_TRUE"
CFG_FALSE="$SANDBOX/false.yml"; printf 'delegate:\n  enabled: false\n' > "$CFG_FALSE"

# run_gate <cfg-path-or-empty> <key-or-empty> <envopt-or-empty> <stub_out> <stub_rc>
# Echoes "<rc> <reason> <forked:yes|no>".
run_gate() {
  _cfg=$1; _key=$2; _envopt=$3; _out=$4; _rc=$5
  : > "$SANDBOX/calls"
  env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED \
      -u ADLC_CONFIG -u ADLC_DISABLE_DELEGATE \
      PATH="$BIN:$PATH" HOME="$FAKEHOME" \
      STUB_CALLS="$SANDBOX/calls" STUB_OUT="$_out" STUB_RC="$_rc" \
      ${_cfg:+ADLC_CONFIG="$_cfg"} \
      ${_key:+MOONSHOT_API_KEY="$_key"} \
      ${_envopt:+ADLC_DELEGATE_ENABLED="$_envopt"} \
      sh -c '. "$1/delegate-gate.sh"
             adlc_delegate_gate_check
             printf "%s %s" "$?" "$ADLC_DELEGATE_GATE_REASON"' _ "$PARTIALS"
  if [ -s "$SANDBOX/calls" ]; then printf ' yes\n'; else printf ' no\n'; fi
}

echo "=== BUG-205: an explicit \`enabled: false\` outranks legacy key continuity ==="

# The regression itself. Before the fix the legacy-key arm was tested first, so
# this returned "0 ok" and a live call followed.
check "config false + legacy key -> disabled, config named as the cause" \
  "1 disabled-via-config yes" "$(run_gate "$CFG_FALSE" sk-legacy "" 0 0)"

check "config false, no key -> disabled (fresh-install wording, both true)" \
  "1 not-opted-in yes" "$(run_gate "$CFG_FALSE" "" "" 0 0)"

check "config true + legacy key -> enabled" \
  "0 ok yes" "$(run_gate "$CFG_TRUE" sk-legacy "" 1 0)"

echo "=== continuity preserved: absence still yields (BR-11's actual case) ==="

# The other side of the fix. If this flips, the fix over-reached and broke every
# pre-config install — the exact population BR-11's exception exists for.
check "NO config file + legacy key -> enabled, and never forks" \
  "0 ok no" "$(run_gate "" sk-legacy "" 0 0)"

check "NO config file, no key -> not opted in, and never forks" \
  "1 not-opted-in no" "$(run_gate "" "" "" 0 0)"

echo "=== precedence: ADLC_DELEGATE_ENABLED (rank 2) outranks the config (rank 3) ==="

# The documented escape hatch for someone who wants delegation on despite the
# config. It must keep working, and must not pay for a fork to do it.
check "env opt-in beats config false, without forking" \
  "0 ok no" "$(run_gate "$CFG_FALSE" sk-legacy 1 0 0)"

echo "=== fail-closed: an unusable probe is never read as consent ==="

# A gate that cannot establish consent must not assume it. Each of these would
# have been "enabled" under the old ordering, since a legacy key is present.
check "probe exits non-zero -> disabled" \
  "1 disabled-via-config yes" "$(run_gate "$CFG_FALSE" sk-legacy "" 1 3)"

check "probe prints nothing -> disabled" \
  "1 disabled-via-config yes" "$(run_gate "$CFG_FALSE" sk-legacy "" __none__ 0)"

check "probe prints garbage -> disabled" \
  "1 disabled-via-config yes" "$(run_gate "$CFG_FALSE" sk-legacy "" yes-please 0)"

echo "=== unchanged contract: the force-off escape hatch still short-circuits ==="

_disable=$(env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED -u ADLC_CONFIG \
  PATH="$BIN:$PATH" HOME="$FAKEHOME" STUB_CALLS="$SANDBOX/calls" STUB_OUT=1 STUB_RC=0 \
  ADLC_DISABLE_DELEGATE=1 ADLC_CONFIG="$CFG_TRUE" MOONSHOT_API_KEY=sk-legacy \
  sh -c '. "$1/delegate-gate.sh"
         adlc_delegate_gate_check
         printf "%s %s" "$?" "$ADLC_DELEGATE_GATE_REASON"' _ "$PARTIALS")
check "ADLC_DISABLE_DELEGATE=1 beats everything" "1 disabled-via-env" "$_disable"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "delegate-gate.test.sh: all cases passed"
else
  echo "delegate-gate.test.sh: $FAILS case(s) failed"
fi
exit $([ "$FAILS" -eq 0 ] && echo 0 || echo 1)
