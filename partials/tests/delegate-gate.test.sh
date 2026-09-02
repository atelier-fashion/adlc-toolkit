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
# Run under ALL THREE shells (REQ-603 BR-6, REQ-609 BR-16 — the gate must behave
# identically under the operator's zsh, under bash, and under /bin/sh):
#   bash    partials/tests/delegate-gate.test.sh
#   zsh     partials/tests/delegate-gate.test.sh
#   /bin/sh partials/tests/delegate-gate.test.sh
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

echo "=== (b2) a failed probe is VISIBLE, not silent (pass-3 M9) ==="
# Every probe failure collapses to not-opted-in, byte-identical to "never opted
# in" — a stale ~/bin/adlc-read silently stopped every skill delegating. One
# stderr line is the difference. Captured with stdout discarded.
_notice=$(env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED -u ADLC_CONFIG \
              -u ADLC_DISABLE_DELEGATE PATH="$BIN:$PATH" HOME="$FAKEHOME" \
              STUB_CALLS="$SANDBOX/calls" STUB_OUT="" STUB_RC=3 \
          sh -c '. "$1/delegate-gate.sh"; adlc_delegate_gate_check' _ "$PARTIALS" 2>&1 >/dev/null)
case "$_notice" in
  *"probe exited 3"*) pass "non-zero probe emits a stderr notice naming the exit code" ;;
  *) fail "non-zero probe emits a stderr notice naming the exit code (got: '$_notice')" ;;
esac
_quiet=$(env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED -u ADLC_CONFIG \
             -u ADLC_DISABLE_DELEGATE PATH="$BIN:$PATH" HOME="$FAKEHOME" \
             STUB_CALLS="$SANDBOX/calls" STUB_OUT="1 ok" STUB_RC=0 \
         sh -c '. "$1/delegate-gate.sh"; adlc_delegate_gate_check' _ "$PARTIALS" 2>&1 >/dev/null)
check "a healthy probe emits NO notice (benign path)" "" "$_quiet"

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

echo "=== (h) AC-1 must also catch an arm hoisted through a temp variable (pass-3 m2) ==="
# `_optin="${ADLC_DELEGATE_ENABLED:-}"; if [ "$_optin" = "1" ]` is the natural
# shape of a re-added fast path, and a conditional-only grep is blind to it.
_hoist=$(grep -nE 'ADLC_DELEGATE_ENABLED|MOONSHOT_API_KEY|KIMI_API_KEY' "$PARTIALS/delegate-gate.sh" \
         | grep -vE '^[0-9]+:[[:space:]]*#' | grep -E '=|\$\{' | wc -l | tr -d " ")
check "no non-comment line READS an authorizing variable at all" "0" "$_hoist"

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

# ==========================================================================
# REQ-609 (TASK-097): the resolver asks the FILESYSTEM, never the shell.
# ==========================================================================
# BUG-209's residue: REQ-603 stopped the gate echoing a bare name, but the
# answer still came out of the shell's lookup machinery, and the hash table
# hands that machinery an absolute path to anything at all. Sections (i)-(n)
# assert the walk's own rules, and each one names the marker or the resolved
# path rather than an exit code (LESSON-478).
#
# Which shell drives the inner runs: run.sh exports it, so `sh run.sh`'s
# three-shell loop exercises the walk under bash, zsh and /bin/sh in turn
# rather than always under sh. A direct invocation is detected instead.
if [ -n "${ADLC_TEST_SHELL-}" ]; then SELF_SH="$ADLC_TEST_SHELL"
elif [ -n "${ZSH_VERSION-}" ]; then SELF_SH=zsh
elif [ -n "${BASH_VERSION-}" ]; then SELF_SH=bash
else SELF_SH=/bin/sh; fi

# Every inner run below is launched through `env PATH=<sandbox>`, which sets the
# PATH env(1) itself searches — so the shell has to be named by absolute path or
# env cannot find it. This is the harness, not the gate: `command -v` is exactly
# the right tool for "where is bash", and it is the gate that must not ask.
abs_shell() { # abs_shell <name-or-path> — absolute path, or empty if absent
  case "$1" in
    /*) if [ -x "$1" ]; then printf '%s' "$1"; fi ;;
    *) command -v "$1" 2>/dev/null ;;
  esac
}
SELF_SH=$(abs_shell "$SELF_SH")
[ -n "$SELF_SH" ] || SELF_SH=/bin/sh

# Fixtures, on top of the sandbox above:
#   planted/adlc-read      a binary the SHELL can be made to name; appends to
#                          $MARKER when it runs, so "was it invoked" is evidence
#   ptime/{timeout,gtimeout}  a timeout(1) planted on $PATH; appends to $TMARKER
#   dirbin/adlc-read       a DIRECTORY: executable, not a regular file
#   noxbin/adlc-read       a regular file that is not executable
#   rel/bin/adlc-read      reachable only through a RELATIVE $PATH entry
#   cwdbin/adlc-read       reachable only through an EMPTY $PATH entry
#   home2/bin, relhome/bin the $HOME arm, absolute and relative
#   home3/bin/adlc-read    a DIRECTORY on the $HOME arm — its own -f case
PLANTED="$SANDBOX/planted"; mkdir -p "$PLANTED"
MARKER="$SANDBOX/marker"
TMARKER="$SANDBOX/timeout-marker"
PTIME="$SANDBOX/ptime"; mkdir -p "$PTIME"
ZMARK="$SANDBOX/zfunc-marker"

cat > "$PLANTED/adlc-read" <<PLANT
#!/bin/sh
printf 'ran\n' >> "$MARKER"
echo "1 ok"
exit 0
PLANT
chmod +x "$PLANTED/adlc-read"

for _n in timeout gtimeout; do
  cat > "$PTIME/$_n" <<PTIMEOUT
#!/bin/sh
printf 'ran\n' >> "$TMARKER"
shift
exec "\$@"
PTIMEOUT
  chmod +x "$PTIME/$_n"
done

mkdir -p "$SANDBOX/dirbin/adlc-read"
mkdir -p "$SANDBOX/home3/bin/adlc-read"
mkdir -p "$SANDBOX/noxbin"
printf '#!/bin/sh\nexit 0\n' > "$SANDBOX/noxbin/adlc-read"
chmod 644 "$SANDBOX/noxbin/adlc-read"
for _d in rel/bin cwdbin home2/bin relhome/bin; do
  mkdir -p "$SANDBOX/$_d"
  cp "$BIN/adlc-read" "$SANDBOX/$_d/adlc-read"
  chmod +x "$SANDBOX/$_d/adlc-read"
done

# resolve_bin <PATH> <HOME> [cwd] — what the gate resolves ADLC_READ_BIN to.
# Sourcing alone is enough; resolution happens at source time.
resolve_bin() {
  ( if [ -n "${3-}" ]; then cd "$3" || exit 1; fi
    env -u ADLC_DISABLE_DELEGATE PATH="$1" HOME="$2" \
        "$SELF_SH" -c '. "$1/delegate-gate.sh"
                       printf "%s" "$ADLC_READ_BIN"' _ "$PARTIALS" )
}

# gate_out <PATH> <HOME> [cwd] — "<rc> <reason>" from a full gate call, with the
# stub scripted to GRANT, so anything but "0 ok" is a resolution outcome.
gate_out() {
  : > "$SANDBOX/calls"
  ( if [ -n "${3-}" ]; then cd "$3" || exit 1; fi
    env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED -u ADLC_CONFIG \
        -u ADLC_DISABLE_DELEGATE PATH="$1" HOME="$2" \
        STUB_CALLS="$SANDBOX/calls" STUB_OUT="1 ok" STUB_RC=0 \
        "$SELF_SH" -c '. "$1/delegate-gate.sh"
                       adlc_delegate_gate_check
                       printf "%s %s" "$?" "$ADLC_DELEGATE_GATE_REASON"' _ "$PARTIALS" )
}

echo "=== (i) the walk resolves a real file on an absolute PATH entry (BR-11) ==="

check "resolves to the file's ABSOLUTE path, never to a name" \
  "$BIN/adlc-read" "$(resolve_bin "$BIN:$SANDBOX/empty" "$FAKEHOME")"

check "the FIRST absolute entry holding the file wins" \
  "$BIN/adlc-read" "$(resolve_bin "$BIN:$SANDBOX/home2/bin" "$FAKEHOME")"

# -x alone is satisfied by a directory; -f is what rejects it.
check "a DIRECTORY named adlc-read is not a match — the walk keeps going" \
  "$BIN/adlc-read" "$(resolve_bin "$SANDBOX/dirbin:$BIN" "$FAKEHOME")"

check "a directory named adlc-read and nothing else -> 2 no-binary" \
  "2 no-binary" "$(gate_out "$SANDBOX/dirbin" "$FAKEHOME")"

check "a non-executable adlc-read is not a match — the walk keeps going" \
  "$BIN/adlc-read" "$(resolve_bin "$SANDBOX/noxbin:$BIN" "$FAKEHOME")"

check "a non-executable adlc-read and nothing else -> 2 no-binary" \
  "2 no-binary" "$(gate_out "$SANDBOX/noxbin" "$FAKEHOME")"

# BR-11's first clause, structurally: one lookup builtin anywhere in the gate is
# the whole defect back. Fixed string, no \b (LESSON-013).
_lookup=$(grep -cF 'command -v' "$PARTIALS/delegate-gate.sh" | tr -d ' ')
check "the gate consults no shell lookup builtin at all" "0" "$_lookup"

echo "=== (j) a function, an alias and a hash entry cannot satisfy resolution (BR-11, AC-6) ==="

# The body lives in a file so the three shells run byte-identical text, and its
# inputs arrive as exported variables because zsh's -c handles positional
# parameters differently from sh's.
cat > "$SANDBOX/hijack-body.sh" <<'HIJACK'
_mechs=""
# 1. A shell function. It is asked of a SUBSHELL first: /bin/sh here is bash in
#    POSIX mode, which rejects a hyphen in a function name, and a syntax error
#    inside eval takes a non-interactive shell down with it — the probe keeps
#    that fatality inside a child.
if ( eval 'adlc-read() { :; }' ) >/dev/null 2>&1; then
  eval 'adlc-read() { "$ADLC_PLANTED" "$@"; }'
  _mechs="$_mechs fn"
fi
# 2. An alias. bash needs expand_aliases in a non-interactive shell; zsh's
#    ALIASES option is on by default and is set here so the intent is on the
#    page; /bin/sh needs neither. Each guard is a not-found command in the other
#    shells, which is why both are swallowed.
shopt -s expand_aliases 2>/dev/null || true
setopt aliases 2>/dev/null || true
if alias adlc-read="$ADLC_PLANTED" 2>/dev/null; then _mechs="$_mechs alias"; fi
# 3. A hash-table entry — the one REQ-603's fix did NOT close, because the table
#    hands the shell an absolute path and a slash-check is satisfied by it.
#    `hash -p file name` in bash, `hash name=file` in zsh (zsh's hash has no -p).
if hash -p "$ADLC_PLANTED" adlc-read 2>/dev/null; then _mechs="$_mechs hash"
elif hash "adlc-read=$ADLC_PLANTED" 2>/dev/null; then _mechs="$_mechs hash"; fi
printf '%s' "${_mechs# }" > "$ADLC_HIJACK_LOG"
# The control (LESSON-602): the shell's own lookup must FIND the hijack, or the
# case below would pass by proving nothing.
_live=$(command -v adlc-read 2>/dev/null)
case "$_live" in "") _live=none ;; *) _live=found ;; esac
. "$ADLC_PARTIALS/delegate-gate.sh"
adlc_delegate_gate_check
printf '%s %s bin=[%s] live=[%s]' "$?" "$ADLC_DELEGATE_GATE_REASON" "$ADLC_READ_BIN" "$_live"
HIJACK

for _sh in bash zsh /bin/sh; do
  _shabs=$(abs_shell "$_sh")
  if [ -z "$_shabs" ]; then
    echo "SKIP: $_sh not installed — hijack case not run under it"
    continue
  fi
  rm -f "$MARKER"
  : > "$SANDBOX/hijacks"
  _hj=$(env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED -u ADLC_CONFIG \
            -u ADLC_DISABLE_DELEGATE PATH="$SANDBOX/empty" HOME="$FAKEHOME" \
            ADLC_PLANTED="$PLANTED/adlc-read" ADLC_PARTIALS="$PARTIALS" \
            ADLC_HIJACK_LOG="$SANDBOX/hijacks" \
            ADLC_HIJACK_BODY="$SANDBOX/hijack-body.sh" \
        "$_shabs" -c '. "$ADLC_HIJACK_BODY"')
  if [ -e "$MARKER" ]; then _hj="$_hj marker=[yes]"; else _hj="$_hj marker=[no]"; fi
  echo "  ($_shabs installed: $(cat "$SANDBOX/hijacks"))"
  check "$_sh: function + alias + hash entry -> 2 no-binary, planted binary never ran" \
    "2 no-binary bin=[] live=[found] marker=[no]" "$_hj"
done

# The control for the marker itself: the planted binary IS runnable and DOES
# write, so "marker=[no]" above is evidence and not an artefact.
rm -f "$MARKER"
"$PLANTED/adlc-read" >/dev/null 2>&1
if [ -e "$MARKER" ]; then _pctl=ran; else _pctl=silent; fi
check "the planted binary writes its marker when actually invoked" "ran" "$_pctl"
rm -f "$MARKER"

echo "=== (k) relative and empty PATH entries are skipped (BR-11) ==="

check "a relative PATH entry holding adlc-read resolves to nothing" \
  "" "$(resolve_bin "rel/bin:$SANDBOX/empty" "$FAKEHOME" "$SANDBOX")"

check "the same file on an ABSOLUTE entry does resolve (working subject)" \
  "$SANDBOX/rel/bin/adlc-read" "$(resolve_bin "$SANDBOX/rel/bin" "$FAKEHOME")"

check "a relative entry does not stop the walk — a later absolute one wins" \
  "$BIN/adlc-read" "$(resolve_bin "rel/bin:$BIN" "$FAKEHOME" "$SANDBOX")"

check "an EMPTY PATH entry (the shell's 'current directory') is skipped" \
  "" "$(resolve_bin ":$SANDBOX/empty" "$FAKEHOME" "$SANDBOX/cwdbin")"

check "a wholly empty PATH resolves to nothing (and terminates)" \
  "" "$(resolve_bin "" "$FAKEHOME" "$SANDBOX/cwdbin")"

check "relative-only PATH -> the gate returns 2 no-binary" \
  "2 no-binary" "$(gate_out "rel/bin:$SANDBOX/empty" "$FAKEHOME" "$SANDBOX")"

echo "=== (l) a timeout(1) planted on PATH is never invoked (BR-11, AC-7) ==="

# The fixed list, recomputed here independently of the gate: the first candidate
# that exists is what the resolver must name, and where none exists the answer
# must be EMPTY — never the planted one, which is first on $PATH.
_want_timeout=""
for _c in /usr/bin/timeout /opt/homebrew/bin/timeout /usr/local/bin/timeout /opt/homebrew/bin/gtimeout /usr/local/bin/gtimeout; do
  if [ -f "$_c" ] && [ -x "$_c" ]; then _want_timeout="$_c"; break; fi
done
_got_timeout=$(env PATH="$PTIME:$BIN" HOME="$FAKEHOME" \
    "$SELF_SH" -c '. "$1/delegate-gate.sh"
                   _adlc_resolve_timeout
                   printf "%s" "$_timeout"' _ "$PARTIALS")
check "the wrapper comes from the fixed list (or is empty), never from PATH" \
  "$_want_timeout" "$_got_timeout"

rm -f "$TMARKER"
_lt=$(gate_out "$PTIME:$BIN" "$FAKEHOME")
if [ -e "$TMARKER" ]; then _lt="$_lt timeout-ran=[yes]"; else _lt="$_lt timeout-ran=[no]"; fi
check "the gate delegates with a planted timeout first on PATH, and never runs it" \
  "0 ok timeout-ran=[no]" "$_lt"
check "... and the real adlc-read is what ran, exactly once" \
  "1" "$(wc -l < "$SANDBOX/calls" | tr -d ' ')"

# The control: the planted wrapper is runnable and does write its marker.
rm -f "$TMARKER"
"$PTIME/timeout" 1 /bin/sh -c 'exit 0' >/dev/null 2>&1
if [ -e "$TMARKER" ]; then _tctl=ran; else _tctl=silent; fi
check "the planted timeout writes its marker when actually invoked" "ran" "$_tctl"
rm -f "$TMARKER"

# Structural: every candidate on the fixed list is absolute, and the resolver
# reads no PATH. Fixed strings, no \b (LESSON-013).
_tline=$(grep -F 'for _t in ' "$PARTIALS/delegate-gate.sh" | head -1)
_tbad=$(printf '%s\n' "$_tline" | sed 's/^.*for _t in //; s/;.*$//' \
        | tr ' ' '\n' | grep -v '^$' | grep -cv '^/' | tr -d ' ')
check "every timeout candidate on the fixed list is an absolute path" "0" "$_tbad"
_tpath=$(sed -n '/^_adlc_resolve_timeout() {/,/^}/p' "$PARTIALS/delegate-gate.sh" \
         | grep -c 'PATH' | tr -d ' ')
check "the timeout resolver never reads PATH" "0" "$_tpath"

echo "=== (m) a HOME that is not absolute is ignored (BR-11) ==="

check "an absolute HOME still resolves \$HOME/bin/adlc-read (working subject)" \
  "$SANDBOX/home2/bin/adlc-read" "$(resolve_bin "$SANDBOX/empty" "$SANDBOX/home2")"

check "a relative HOME is ignored" \
  "" "$(resolve_bin "$SANDBOX/empty" "relhome" "$SANDBOX")"

# The HOME arm carries its own -f, and it needs its own case: dropping it there
# is invisible to (i), which only exercises the walk.
check "a DIRECTORY at \$HOME/bin/adlc-read is not a match either" \
  "" "$(resolve_bin "$SANDBOX/empty" "$SANDBOX/home3")"

check "an empty HOME is ignored" \
  "" "$(resolve_bin "$SANDBOX/empty" "" "$SANDBOX")"

check "a relative HOME -> the gate returns 2 no-binary" \
  "2 no-binary" "$(gate_out "$SANDBOX/empty" "relhome" "$SANDBOX")"

echo "=== (n) a zsh function named with the ABSOLUTE path does not intercept (BR-11) ==="

# Written with an expanding heredoc so the sandbox path lands in the file
# LITERALLY: `function /abs/path/adlc-read { ... }`, which is what zsh accepts
# and what a plain invocation of that path would run.
cat > "$SANDBOX/zfunc-body.zsh" <<ZFUNC
function $BIN/adlc-read {
  printf 'ran\n' >> "$ZMARK"
  echo "1 ok"
}
# The control (LESSON-602): prove the hijack is LIVE before asserting it lost.
$BIN/adlc-read --print-gate >/dev/null 2>&1
. "$PARTIALS/delegate-gate.sh"
adlc_delegate_gate_check
printf '%s %s bin=[%s]' "\$?" "\$ADLC_DELEGATE_GATE_REASON" "\$ADLC_READ_BIN"
ZFUNC

ZSH_ABS=$(abs_shell zsh)
if [ -n "$ZSH_ABS" ]; then
  : > "$ZMARK"
  : > "$SANDBOX/calls"
  _zn=$(env -u MOONSHOT_API_KEY -u KIMI_API_KEY -u ADLC_DELEGATE_ENABLED -u ADLC_CONFIG \
            -u ADLC_DISABLE_DELEGATE PATH="$BIN:$SANDBOX/empty" HOME="$FAKEHOME" \
            STUB_CALLS="$SANDBOX/calls" STUB_OUT="1 ok" STUB_RC=0 \
            ADLC_ZFUNC_BODY="$SANDBOX/zfunc-body.zsh" \
        "$ZSH_ABS" -c '. "$ADLC_ZFUNC_BODY"')
  check "zsh: the gate delegates through the FILE, not the same-named function" \
    "0 ok bin=[$BIN/adlc-read]" "$_zn"
  check "the absolute-path function ran ONCE — for the control, never for the gate" \
    "1" "$(wc -l < "$ZMARK" | tr -d ' ')"
  check "the real file on disk is what the gate executed" \
    "1" "$(wc -l < "$SANDBOX/calls" | tr -d ' ')"
else
  echo "SKIP: zsh not installed — the absolute-path function case needs it"
fi

echo
if [ "$FAILS" -eq 0 ]; then
  echo "delegate-gate.test.sh: all cases passed"
  exit 0
fi
echo "delegate-gate.test.sh: $FAILS case(s) failed"
exit 1
