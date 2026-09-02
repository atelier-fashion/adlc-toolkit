#!/bin/sh
# Shared provider-agnostic delegation gate predicate (REQ-515 BR-4/BR-11).
# This is the canonical (and only) gate predicate (REQ-522 retired the legacy
# back-compat alias partial).
#
# Sourceable POSIX shell function. Each call site reads $? IMMEDIATELY into a
# variable (gate=$?) before any other command, because $? is clobbered by every
# subsequent command. See partials/delegate-gate.md for the full protocol.
#
# Return-code contract (UNCHANGED 0/1/2 shape so existing callers' case
# statements keep working):
#   0 — delegated:    adlc-read resolvable AND not disabled AND opt-in satisfied
#   1 — disabled:     ADLC_DISABLE_DELEGATE=1,
#                     OR opt-in NOT satisfied (BR-11 fresh-install posture)
#   2 — unavailable:  adlc-read is not resolvable (no executable regular file
#                     named adlc-read under any ABSOLUTE $PATH entry, and none
#                     at $HOME/bin/adlc-read)
#
# Reason-string contract:
#   The function exports ADLC_DELEGATE_GATE_REASON on every code path. Canonical
#   values (paired with the return code):
#     return 0 → "ok"
#     return 1 → "disabled-via-env"    (an explicit disable flag) OR
#                "disabled-via-config" (delegate.enabled: false — BUG-205) OR
#                "not-opted-in"         (BR-11: no opt-in signal)
#     return 2 → "no-binary"
#   `export` is intentional — a child delegate invocation may read it.
#
# Opt-in (BR-11) is resolved in the SAME precedence order as the provider fields
# (BR-2), highest first. Before BUG-205 `enabled` did not follow that order — it
# was a flat OR in which the legacy-key arm outranked the config file:
#   1. ADLC_DELEGATE_ENABLED=1 in the environment            → opted in
#   2. delegate.enabled in the config file, when the key is PRESENT → decisive
#      in BOTH directions. `true` opts in; `false` opts OUT and outranks the
#      continuity arm below. Resolved in Python, never parsed in shell
#      (REQ-515 ADR-3).
#   3. a legacy key in env (KIMI_API_KEY / MOONSHOT_API_KEY) — key continuity is
#      provider-preset data, not branding (REQ-522 BR-1/BR-3). Reached ONLY when
#      no config file exists, which is the pre-config install BR-11 wrote it for.
#   4. otherwise                                             → not opted in
#
# An ABSENT `enabled` key is not the same as `enabled: false`: absence is a
# default and yields to continuity, a written `false` is an instruction and does
# not. Collapsing the two is what BUG-205 was.
#
# Cost (REQ-603): one fork on every path that could AUTHORIZE. The veto and
# no-binary paths stay fork-free, so the emergency stop is as cheap as it ever
# was. Measured: the probe is ~21ms against a ~104s median delegated step.
#
# No `set -eu` here — return codes ARE the contract.

# Defensive default: a caller that reads the reason without invoking the
# function gets "unset", making telemetry visibly wrong instead of silently
# empty.
export ADLC_DELEGATE_GATE_REASON="unset"

# --- binary resolution ------------------------------------------------------
# The resolver asks the FILESYSTEM, never the shell (REQ-609 BR-11, ADR-3).
# A lookup builtin (`command`'s `-v` form, `type`, `which`) answers out of the
# shell's own machinery — functions, aliases and the hash table all feed it, and
# none of them is a statement about the filesystem — so a planted function, or
# a `hash -p` entry naming any binary at all, was enough to be handed the corpus
# (BUG-209). A filesystem question has to be asked of the filesystem, so this
# walks $PATH itself:
#   * entries are split on `:` with parameter expansion only — no IFS change,
#     no unquoted word-splitting (zsh does not split — LESSON-329), no globs
#     (LESSON-335), no arrays. Identical under sh, bash and zsh.
#   * an entry that does not begin with `/` is skipped, empty entries included.
#     A relative entry names whatever directory the caller happens to be sitting
#     in, which is not a property of the machine's install.
#   * the first "$dir/adlc-read" that is a regular file (-f) AND executable (-x)
#     wins. -x alone is satisfied by a DIRECTORY named adlc-read.
# GUI-launched Claude Code sessions may run with a PATH that lacks ~/bin (only
# .zshrc adds it), so $HOME/bin/adlc-read is tried after the walk — and only
# when $HOME is itself absolute, by the same rule.
# Resolution order:
#   1. the first absolute $PATH entry holding an executable regular adlc-read,
#      echoed as THAT ABSOLUTE PATH — never as a bare name, which the shell
#      would re-resolve through the very machinery this walk exists to avoid
#   2. an executable regular file at $HOME/bin/adlc-read, when $HOME starts "/"
#   3. neither → empty string
_adlc_resolve_read_bin() {
  _rest="${PATH:-}:"
  while [ -n "$_rest" ]; do
    _dir="${_rest%%:*}"
    _rest="${_rest#*:}"
    case "$_dir" in
      /*) ;;
      *) continue ;;
    esac
    if [ -f "$_dir/adlc-read" ] && [ -x "$_dir/adlc-read" ]; then
      printf '%s\n' "$_dir/adlc-read"
      unset _rest _dir
      return 0
    fi
  done
  unset _rest _dir
  case "${HOME:-}" in
    /*)
      if [ -f "$HOME/bin/adlc-read" ] && [ -x "$HOME/bin/adlc-read" ]; then
        printf '%s\n' "$HOME/bin/adlc-read"
        return 0
      fi
      ;;
  esac
  printf '\n'
  return 1
}

# Resolve at source time so a fenced block that only sources this partial
# (e.g. a delegated-invocation fence that never calls the gate function) still
# gets $ADLC_READ_BIN. The value is an absolute path or empty, and nothing else;
# empty is a refusal for a call site to act on (REQ-609 BR-12), not an invitation
# to resolve the name a second time by a weaker rule.
ADLC_READ_BIN="$(_adlc_resolve_read_bin)"
export ADLC_READ_BIN

# --- the bounded-probe wrapper ----------------------------------------------
# timeout(1) is chosen from a FIXED list of absolute paths and never from $PATH
# (REQ-609 BR-11): a `timeout` planted on $PATH would wrap every probe the gate
# runs, and a wrapper sees — and can replace — the very binary it is wrapping.
# A `for` over a literal list is safe under zsh (nothing to split, nothing to
# glob). Sets $_timeout to a candidate or to empty; empty means "no timeout(1)
# on this machine" (stock macOS), and the probe then runs unbounded rather than
# failing, because an unavailable hardening must not become an outage.
# The list is kept on ONE line so the harness can assert every candidate on it
# is absolute.
_adlc_resolve_timeout() {
  _timeout=""
  for _t in /usr/bin/timeout /opt/homebrew/bin/timeout /usr/local/bin/timeout /opt/homebrew/bin/gtimeout /usr/local/bin/gtimeout; do
    if [ -f "$_t" ] && [ -x "$_t" ]; then _timeout="$_t"; break; fi
  done
  unset _t
}

# --- the dispatcher --------------------------------------------------------
adlc_delegate_gate_check() {
  # Re-resolve at call time — PATH may have changed since the partial was
  # sourced, and a caller may invoke the gate long after sourcing.
  ADLC_READ_BIN="$(_adlc_resolve_read_bin)"
  export ADLC_READ_BIN
  # (1) no-binary stays in shell: it is the one question the probe cannot answer,
  #     and it can only WITHHOLD delegation, never grant it (REQ-603 BR-5).
  #     Resolved BEFORE the veto, preserving the pre-REQ order — binary-missing
  #     plus veto-set yields 2, not 1.
  if [ -z "$ADLC_READ_BIN" ]; then
    export ADLC_DELEGATE_GATE_REASON="no-binary"
    return 2
  fi
  # (2) the veto: the one deliberate duplication (REQ-603 BR-2). A veto arm can
  #     only ever return "disabled", so the shell and Python copies can agree or
  #     abstain but never contradict — PROVIDED Python recognises at least every
  #     input this test does. Both test the literal "1"; widening one alone is
  #     the defect, and tests/test_cross_layer_veto.py is what enforces it.
  #     Kept here so the emergency stop stays fork-free: it is the control most
  #     likely to be reached when something has already gone wrong.
  if [ "${ADLC_DISABLE_DELEGATE:-0}" = "1" ]; then
    export ADLC_DELEGATE_GATE_REASON="disabled-via-env"
    return 1
  fi
  # (3) everything that could AUTHORIZE is Python's (REQ-603 BR-1). One probe,
  #     never two: two invocations could straddle an env change and report an
  #     incoherent pair (BR-7).
  #
  #     `_probe_rc=$?` MUST be the very next statement — command substitution
  #     discards the exit code, so a probe that printed a verdict and THEN failed
  #     would otherwise be read as consent (the shape BUG-205 was).
  # Bounded where a timeout(1) exists: the fork is now unconditional on every
  # non-vetoed call, so a wedged adlc-read would otherwise hang the calling skill
  # with no fallback. Expiry is a non-zero exit and therefore fails closed. Where
  # timeout(1) is absent (stock macOS), this degrades to the unbounded call
  # rather than failing — an unavailable hardening must not become an outage.
  # 10s: an emergency bound, not a tunable — the probe is ~21ms in practice.
  # Duplicated across both branches deliberately: building a "timeout 10"
  # prefix variable would require unquoted word-splitting to inject it as two
  # argv words, which is IFS-dependent and fragile (LESSON-329).
  #
  # Both invocations go through `command`, which bypasses function and alias
  # lookup: zsh will happily define a function whose name is an absolute path,
  # and without `command` that function — not the file the resolver proved is
  # there — is what would run (REQ-609 ADR-3). Both words are absolute paths, so
  # the hash table is not consulted either.
  _adlc_resolve_timeout
  if [ -n "$_timeout" ]; then
    _probe="$(command "$_timeout" 10 "$ADLC_READ_BIN" --print-gate 2>/dev/null)"
  else
    _probe="$(command "$ADLC_READ_BIN" --print-gate 2>/dev/null)"
  fi
  _probe_rc=$?
  unset _timeout
  if [ "$_probe_rc" -ne 0 ]; then
    # Fail closed, but SAY SO. Every probe failure — an adlc-read predating
    # --print-gate, a wedged probe, a timeout expiry (124) — previously collapsed
    # into `not-opted-in`, byte-identical to "this machine never opted in". A
    # consumer with a stale ~/bin/adlc-read silently stopped delegating
    # everywhere. One stderr line is the difference.
    echo "delegate-gate: probe exited $_probe_rc — failing closed as not-opted-in (an adlc-read predating --print-gate, or a wedged probe; run adlc-read --version)" >&2
    export ADLC_DELEGATE_GATE_REASON="not-opted-in"
    unset _probe _probe_rc
    return 1
  fi
  # Parse "<enabled> <reason>". The probe's stdout is untrusted input to shell
  # (LESSON-008): take exactly two fields and validate the reason against the
  # frozen enum before exporting it. An unrecognised value is a fail-closed
  # condition, not a pass-through.
  _verdict=${_probe%% *}
  _reason=${_probe#* }
  # Validate the PAIR, not the reason alone. Validating separately let "0 ok"
  # (and "\n1 ok", whose leading newline shifts the fields) export reason=ok
  # alongside return 1 — an inconsistent record forwarded verbatim into telemetry
  # and to agents/delegate-pre-pass.md, i.e. a withheld run logged as ok. Only
  # the four legal pairs are accepted; anything else fails closed.
  # Safe only because no frozen reason contains a space: the concatenation
  # "$_verdict $_reason" is unambiguous. Adding a reason with a space would
  # silently break this match — keep the enum space-free.
  case "$_verdict $_reason" in
    "1 ok")
      export ADLC_DELEGATE_GATE_REASON="ok"
      unset _probe _probe_rc _verdict _reason
      return 0 ;;
    "0 disabled-via-env"|"0 disabled-via-config"|"0 not-opted-in")
      export ADLC_DELEGATE_GATE_REASON="$_reason"
      unset _probe _probe_rc _verdict _reason
      return 1 ;;
    *)
      export ADLC_DELEGATE_GATE_REASON="not-opted-in"
      unset _probe _probe_rc _verdict _reason
      return 1 ;;
  esac
}
