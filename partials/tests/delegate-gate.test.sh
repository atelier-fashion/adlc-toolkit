#!/bin/sh
# partials/tests/delegate-gate.test.sh — the gate's OWN responsibilities
# (REQ-603 BR-8). Cascade semantics — which authorizing arm wins — are asserted
# once, in tools/delegate/tests/, because the gate no longer decides them.
#
# Keeping the cascade cases here would preserve the exact condition REQ-603
# removes: a green shell assertion standing in for coverage of the real
# resolver. That is how BUG-209 survived — this harness asserted
# "ADLC_DISABLE_DELEGATE=1 beats everything" and passed while both CLIs ignored
# the variable entirely.
#
# What belongs here, and only this:
#   (a) the gate returns what the probe said
#   (b) it fails closed on a broken probe
#   (c) no-binary returns 2 without probing
#   (d) the veto short-circuits with zero probes
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
mkdir -p "$SANDBOX/empty"

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

echo "=== (a) pass-through: the gate returns what the probe said ==="

check "probe '1 ok' -> delegated" \
  "0 ok yes" "$(run_gate "" "" "" "1 ok" 0)"

check "probe '0 disabled-via-env' -> passed through verbatim" \
  "1 disabled-via-env yes" "$(run_gate "" "" "" "0 disabled-via-env" 0)"

check "probe '0 disabled-via-config' -> passed through verbatim" \
  "1 disabled-via-config yes" "$(run_gate "" "" "" "0 disabled-via-config" 0)"

check "probe '0 not-opted-in' -> passed through verbatim" \
  "1 not-opted-in yes" "$(run_gate "" "" "" "0 not-opted-in" 0)"

# REQ-603 AC-19/AC-21: every reason the probe can emit survives the gate
# unchanged. The gate must not re-derive, re-label, or collapse any of them —
# that re-derivation is what ADR-4 found to be wrong in the pre-REQ heuristic.
echo "=== (a2) reason fidelity: no probe reason is altered in transit ==="
for _r in ok disabled-via-env disabled-via-config not-opted-in; do
  if [ "$_r" = "ok" ]; then _v=1; _want="0 ok yes"; else _v=0; _want="1 $_r yes"; fi
  check "reason '$_r' round-trips unaltered" "$_want" "$(run_gate "" "" "" "$_v $_r" 0)"
done

echo "=== (b) fail-closed on a broken probe ==="

# Printed a valid verdict and THEN failed. Command substitution discards the
# exit code, so without the immediate `_probe_rc=$?` this reads as consent —
# the shape BUG-205 was.
check "probe prints '1 ok' then exits non-zero -> NOT delegated" \
  "1 not-opted-in yes" "$(run_gate "" "" "" "1 ok" 3)"

check "probe exits non-zero -> not delegated" \
  "1 not-opted-in yes" "$(run_gate "" "" "" "" 1)"

check "probe prints nothing -> not delegated" \
  "1 not-opted-in yes" "$(run_gate "" "" "" __none__ 0)"

check "probe prints garbage -> not delegated" \
  "1 not-opted-in yes" "$(run_gate "" "" "" "yes definitely" 0)"

check "probe names a reason outside the frozen enum -> not delegated" \
  "1 not-opted-in yes" "$(run_gate "" "" "" "1 totally-fine" 0)"

# The (verdict, reason) PAIR cases. Reverting the pair validation to the
# reason-only form previously passed this whole harness — the fix was asserted,
# not tested. "0 ok" is the one the commit message cites: it exported reason=ok
# alongside rc=1, so a WITHHELD run was logged as ok in telemetry and forwarded
# verbatim to agents/delegate-pre-pass.md.
check "probe '0 ok' (inconsistent pair) -> not delegated, reason NOT ok" \
  "1 not-opted-in yes" "$(run_gate "" "" "" "0 ok" 0)"

check "probe '1 disabled-via-config' (inconsistent pair) -> not delegated" \
  "1 not-opted-in yes" "$(run_gate "" "" "" "1 disabled-via-config" 0)"

check "probe '1 not-opted-in' (inconsistent pair) -> not delegated" \
  "1 not-opted-in yes" "$(run_gate "" "" "" "1 not-opted-in" 0)"

echo "=== (c) no-binary: return 2 WITHOUT probing (REQ-603 BR-5) ==="

_nobin=$(env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED \
             -u ADLC_CONFIG -u ADLC_DISABLE_DELEGATE \
             PATH="$SANDBOX/empty" HOME="$FAKEHOME" \
         /bin/sh -c '. "$1/delegate-gate.sh"
                adlc_delegate_gate_check
                printf "%s %s" "$?" "$ADLC_DELEGATE_GATE_REASON"' _ "$PARTIALS")
check "no binary -> 2 no-binary" "2 no-binary" "$_nobin"

# Binary missing AND the veto set: the pre-REQ order resolved the binary first,
# so this is 2, not 1. BR-5 pins that ordering; inverting it would silently
# break the return-code guarantee on a path no other rule covers.
_nobin_veto=$(env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED -u ADLC_CONFIG \
                  ADLC_DISABLE_DELEGATE=1 PATH="$SANDBOX/empty" HOME="$FAKEHOME" \
              /bin/sh -c '. "$1/delegate-gate.sh"
                     adlc_delegate_gate_check
                     printf "%s %s" "$?" "$ADLC_DELEGATE_GATE_REASON"' _ "$PARTIALS")
check "no binary + veto -> still 2 no-binary (binary resolves first)" \
  "2 no-binary" "$_nobin_veto"

echo "=== (d) the veto short-circuits with ZERO probes (REQ-603 BR-2, AC-4) ==="

# The emergency stop must stay fork-free. It is the control most likely to be
# reached when something has already gone wrong.
: > "$SANDBOX/calls"
_veto=$(env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED -u ADLC_CONFIG \
            ADLC_DISABLE_DELEGATE=1 PATH="$BIN:$PATH" HOME="$FAKEHOME" \
            STUB_CALLS="$SANDBOX/calls" STUB_OUT="1 ok" STUB_RC=0 \
        sh -c '. "$1/delegate-gate.sh"
               adlc_delegate_gate_check
               printf "%s %s" "$?" "$ADLC_DELEGATE_GATE_REASON"' _ "$PARTIALS")
if [ -s "$SANDBOX/calls" ]; then _veto="$_veto yes"; else _veto="$_veto no"; fi
check "veto -> 1 disabled-via-env, zero probes" "1 disabled-via-env no" "$_veto"

# AC-4: the veto outranks every authorizing signal at once.
: > "$SANDBOX/calls"
_veto_all=$(env ADLC_DISABLE_DELEGATE=1 ADLC_DELEGATE_ENABLED=1 MOONSHOT_API_KEY=sk-legacy \
                ADLC_CONFIG="$CFG_TRUE" PATH="$BIN:$PATH" HOME="$FAKEHOME" \
                STUB_CALLS="$SANDBOX/calls" STUB_OUT="1 ok" STUB_RC=0 \
            sh -c '. "$1/delegate-gate.sh"
                   adlc_delegate_gate_check
                   printf "%s %s" "$?" "$ADLC_DELEGATE_GATE_REASON"' _ "$PARTIALS")
if [ -s "$SANDBOX/calls" ]; then _veto_all="$_veto_all yes"; else _veto_all="$_veto_all no"; fi
check "veto beats env opt-in + config true + legacy key, zero probes" \
  "1 disabled-via-env no" "$_veto_all"

echo "=== (e) at most ONE probe per gate call (REQ-603 BR-7, AC-11) ==="

: > "$SANDBOX/calls"
env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED -u ADLC_CONFIG \
    -u ADLC_DISABLE_DELEGATE PATH="$BIN:$PATH" HOME="$FAKEHOME" \
    STUB_CALLS="$SANDBOX/calls" STUB_OUT="1 ok" STUB_RC=0 \
  sh -c '. "$1/delegate-gate.sh"; adlc_delegate_gate_check' _ "$PARTIALS" >/dev/null 2>&1
check "delegated path forks exactly once" "1" "$(wc -l < "$SANDBOX/calls" | tr -d " ")"

echo "=== (f) BR-1: the gate contains no AUTHORIZING arm (AC-1) ==="

# Decision sites only — a mention in a comment is documentation, not a branch.
# grep -E without \b (BSD grep on macOS does not honor it — LESSON-013).
_auth=$(grep -nE '^[[:space:]]*(if|elif|case|\[)' "$PARTIALS/delegate-gate.sh" \
        | grep -E 'ADLC_DELEGATE_ENABLED|MOONSHOT_API_KEY|KIMI_API_KEY' | wc -l | tr -d " ")
check "no conditional branches on an authorizing variable" "0" "$_auth"

_cfgread=$(grep -nE '^[[:space:]]*[^#]*ADLC_CONFIG|config\.yml' "$PARTIALS/delegate-gate.sh" \
           | grep -vE '^[[:space:]]*[0-9]+:[[:space:]]*#' | wc -l | tr -d " ")
check "gate does not read the config file path" "0" "$_cfgread"

# AC-2: the veto IS present, and positioned after binary resolution.
_veto_line=$(grep -n 'ADLC_DISABLE_DELEGATE' "$PARTIALS/delegate-gate.sh" | grep -E ':[[:space:]]*if' | head -1 | cut -d: -f1)
_bin_line=$(grep -n 'ADLC_READ_BIN="\$(_adlc_resolve_read_bin)"' "$PARTIALS/delegate-gate.sh" | head -1 | cut -d: -f1)
if [ -n "$_veto_line" ] && [ -n "$_bin_line" ] && [ "$_veto_line" -gt "$_bin_line" ]; then
  pass "veto present and positioned after binary resolution (AC-2)"
else
  fail "veto present and positioned after binary resolution (AC-2) (veto=$_veto_line bin=$_bin_line)"
fi

echo
if [ "$FAILS" -eq 0 ]; then
  echo "delegate-gate.test.sh: all cases passed"
  exit 0
fi
echo "delegate-gate.test.sh: $FAILS case(s) failed"
exit 1
