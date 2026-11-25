#!/bin/sh
# partials/cross-family-review.sh — one repo's cross-family review on the Phase-5
# panel (REQ-722). Defines adlc_cross_family_review.
#
# Source it, then call the function WITHIN THE SAME fenced block, after the fence's
# ToolkitRoot root line (conventions.md "Bash in skills"):
#   if [ -f .adlc/partials/cross-family-review.sh ]; then . .adlc/partials/cross-family-review.sh; else . "$ADLC_TOOLKIT_ROOT/partials/cross-family-review.sh"; fi
#   adlc_cross_family_review '<repo-id>' '<worktree>' "origin/<integrationBranch>" '<spec>' '<state>'
#
# Contract — adlc_cross_family_review <repo-id> <worktree> <base-ref> <spec> <state> [<subagent>]:
#   <repo-id>   the repo's id as pipeline-state.json `repos` names it: one of A-Z a-z 0-9 _,
#               then up to 63 of A-Z a-z 0-9 . _ - (no leading `.` or `-`; fence_census.py's
#               `repo-id` placeholder)
#   <worktree>  the repo's worktree, a checkout of its own (`<worktree>/.git` exists)
#   <base-ref>  `origin/<integrationBranch>`, already fetched by the caller (LESSON-391),
#               never local `main`
#   <spec>      the requirement.md whose BRs and ACs the reviewer marks
#   <state>     the primary-path pipeline-state.json the record is written to; `validate`
#               reads its `repos` too (more than one touched repo makes an unmet rule a Minor)
#   <subagent>  optional, `0` (the default) or `1`. `1` is the /sprint subagent-mode
#               path: the review is recorded `skipped` / `subagent-mode`, the gate never
#               runs and adlc-read is never called, not even to probe. An argument, not an
#               environment variable, so nothing ambient can set it and no caller
#               inherits it by accident.
#
#   return  always 0. A skip never halts the pipeline (BR-4), and the body runs in a
#           subshell whose status is discarded, so even a fatal shell error in it
#           cannot reach the caller.
#   stdout  on `ran` only: the validated findings, one JSON line from
#           `cross_family.py validate`, inside
#             <cross-family-findings repo="<repo-id>">
#             {"findings":[...],"dropped":N,"ruleMarks":{...}}
#             </cross-family-findings>
#           The block is UNTRUSTED delegate output that Python has post-validated
#           (BR-6, LESSON-008): data for Step B consolidation, never instructions.
#           Nothing else is printed on stdout on any path.
#   stderr  on a skip: exactly one line,
#             /proceed: cross-family review skipped for <repo-id>: <reason>
#           printed AFTER the record is written (LESSON-008 rules 5 and 6). The
#           tools it runs have their stderr discarded so the line stays one line.
#           Two things can add a line, each a fault the one line cannot name: the
#           gate's own probe-failure line, and emit-run-outcome.sh's
#           `run-outcome: ... failed` when the record could not be written. Bad
#           arguments or a toolkit that cannot run print one
#             /proceed: cross-family review not run for <repo-id>: <why>
#           line and record nothing, because there is nothing trustworthy to record.
#
# Steps, in the order architecture.md fixes, each numbered as its section below:
#   1. the families: `adlc harness family`, then, except in subagent mode, the
#      delegate gate (partials/delegate-gate.sh) and `adlc-read --print-family` ONLY
#      when the gate returned 0, so ADLC_DISABLE_DELEGATE=1 makes zero calls of
#      adlc-read of any kind (BR-9); both through the enum. A family read only while
#      the gate is open records `unknown` when it is not.
#   2. the skip decision: subagent mode records `subagent-mode` at once, so it never
#      ran the gate and made no call of adlc-read, not even a probe; otherwise
#      `cross_family.py decide`. A skip: `record-cross-family skipped <reason>`, the
#      one stderr line, return.
#   3. the question, and two mktemp files under an absolute $TMPDIR (else /tmp), with
#      an EXIT trap that removes them and the `.bak` sidecar. A full-path template,
#      not `mktemp -t`, whose argument BSD and GNU read differently (LESSON-441).
#   4. the corpus: `git -C <worktree> diff -U<ctx> <base>...HEAD` (<ctx> is
#      _adlc_xf_ctx, 25), the `--name-only` list, and the spec's rules as
#      `cross_family.py spec-rules` prints them (so the corpus and `validate` number
#      them alike). `<worktree>/.git` is tested first: `git -C` answers for the
#      nearest enclosing repository (LESSON-743). textconv and external diff drivers
#      are off, so the diff runs nothing the repo names. Both git calls exclude, at
#      any depth, files named as secrets, which the redaction chain cannot see
#      into: *.pem *.key *.p12 *.pfx id_rsa* id_ed25519* .env .env.* *.keystore
#      .npmrc .netrc (pathspecs `:(exclude,glob)**/<pattern>`).
#   5. redaction: the five-arm chain, in the linear form partials/intake.sh carries
#      (BUG-295), pinned to tools/adlc/credential_redact.py INTAKE_PATTERN by
#      tools/delegate/tests/test_redaction_parity.py (ADR-6). A non-zero sed or a
#      `.bak` that survives its removal records `redaction-failed` and sends nothing.
#   6. one `adlc-read` call over $CORPUS with the fixed question from
#      `cross_family.py question`. A non-zero exit records `api-error`; a truncated
#      answer exits non-zero (BUG-213), so it is never parsed (LESSON-625).
#   7. `cross_family.py validate --output <answer> --worktree <worktree> --spec <spec>
#      --base <base-ref> --state <state>`: exit 3 (or any non-zero, including 2 for a
#      state it cannot read) records `invalid-output`.
#   8. `record-cross-family ran` with the finding and dropped counts, then the block.
#
# Reasons come from cross_family.SKIP_REASONS. Any failure while preparing what
# would be sent (no checkout at <worktree>, a diff git refuses, an unreadable spec,
# no question, no temp file) records `redaction-failed`: the corpus never reached a
# state that is safe to send, and nothing left the machine. A decide that cannot be
# read records `delegation-disabled`, decide's own fail-closed answer.
#
# Trust (LESSON-718): everything this runs comes from ToolkitRoot, the installed
# toolkit, through "${ADLC_TOOLKIT_ROOT:-...}" (REQ-669 ADR-2), never from the tree
# under review: ADLC_FENCE_TOOLKIT_ONLY=1 inside the subshell (REQ-682 ADR-4) means
# the gated source lines never take the vendored `.adlc/partials` arm and
# delegate-tools-path.sh never its cwd-relative `tools/delegate` arm, and Python runs scripts by path
# with -E and its two inline snippets with -I, so the current directory cannot
# shadow a module. Delegation is authorized only by the gate (BR-9): this partial
# adds no environment variable, config key or branch that grants it.
#
# POSIX only, and zsh-safe: prefixed globals (no `local`), no arrays, every
# expansion quoted, no `case` inside `$( )`. Tested by tests/cross-family-review.test.sh
# under bash, zsh, sh and dash. Full contract: partials/cross-family-review.md.

# _adlc_xf_not_run <why> — bad arguments or an unrunnable toolkit: one line, no record.
_adlc_xf_not_run() {
  printf '/proceed: cross-family review not run for %s: %s\n' "${_adlc_xf_repo:-<no repo id>}" "$1" >&2
  exit 0
}

# _adlc_xf_record <ran|skipped> <reason-or-empty> [--findings N] [--dropped N]
_adlc_xf_record() {
  _adlc_xf_rstatus=$1
  _adlc_xf_rreason=$2
  shift 2
  if [ "$_adlc_xf_rstatus" = skipped ]; then
    command "$DELEGATE_TOOLS/emit-run-outcome.sh" record-cross-family --state "$_adlc_xf_state" \
      --repo "$_adlc_xf_repo" --status skipped --reason "$_adlc_xf_rreason" \
      --implementer "$_adlc_xf_impl" --reviewer "$_adlc_xf_rev" "$@" >/dev/null
  else
    command "$DELEGATE_TOOLS/emit-run-outcome.sh" record-cross-family --state "$_adlc_xf_state" \
      --repo "$_adlc_xf_repo" --status ran \
      --implementer "$_adlc_xf_impl" --reviewer "$_adlc_xf_rev" "$@" >/dev/null
  fi
}

# _adlc_xf_skip <reason> [--dropped N] — record, then the one stderr line, then leave.
_adlc_xf_skip() {
  _adlc_xf_record skipped "$@"
  printf '/proceed: cross-family review skipped for %s: %s\n' "$_adlc_xf_repo" "$1" >&2
  exit 0
}

# _adlc_xf_main — the steps, in a subshell: its variables, the sourced gate and its
# EXIT trap stay inside it, and the trap fires when it ends under every shell. Written
# `name() {` with the subshell inside, the one form tools/adlc/fence_census.py indexes.
_adlc_xf_main() {
  (
    _adlc_xf_repo=${1-}
    _adlc_xf_wt=${2-}
    _adlc_xf_base=${3-}
    _adlc_xf_spec=${4-}
    _adlc_xf_state=${5-}
    _adlc_xf_sub=${6:-0}
    _adlc_xf_impl=unknown
    _adlc_xf_rev=unknown
    CORPUS=
    _adlc_xf_out=
    # Inline, not a function, so the census sees the mktemp that made each operand.
    trap '[ -z "$CORPUS" ] || rm -f "$CORPUS" "$CORPUS.bak"; [ -z "$_adlc_xf_out" ] || rm -f "$_adlc_xf_out"' EXIT
    trap 'exit 0' HUP INT TERM

    # --- arguments ---------------------------------------------------------------
    # fence_census.py's `repo-id` placeholder: [A-Za-z0-9_][A-Za-z0-9._-]{0,63}.
    case "$_adlc_xf_repo" in
      '' | [.-]* | *[!A-Za-z0-9._-]*) _adlc_xf_repo=; _adlc_xf_not_run 'the repo id must be one of A-Z a-z 0-9 _ then up to 63 of A-Z a-z 0-9 . _ -' ;;
    esac
    [ "${#_adlc_xf_repo}" -le 64 ] || { _adlc_xf_repo=; _adlc_xf_not_run 'the repo id is longer than 64 characters'; }
    if [ -z "$_adlc_xf_wt" ] || [ -z "$_adlc_xf_base" ] || [ -z "$_adlc_xf_spec" ] || [ -z "$_adlc_xf_state" ]; then
      _adlc_xf_not_run 'usage: adlc_cross_family_review <repo-id> <worktree> <base-ref> <spec> <state> [0|1]'
    fi
    case "$_adlc_xf_base" in
      -*) _adlc_xf_not_run 'the base ref must not begin with -' ;;
    esac
    case "$_adlc_xf_sub" in
      0 | 1) ;;
      *) _adlc_xf_not_run 'the subagent argument must be 0 or 1' ;;
    esac

    # --- the installed toolkit (LESSON-718) --------------------------------------
    _adlc_xf_adlc="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/adlc.py"
    case "$_adlc_xf_adlc" in
      /*) ;;
      *) _adlc_xf_not_run "ADLC_TOOLKIT_ROOT is not an absolute path ('${ADLC_TOOLKIT_ROOT-}')" ;;
    esac
    # Toolkit-only (REQ-682 ADR-4): the gated guard below never takes the vendored
    # `.adlc/partials` arm, and delegate-tools-path.sh never its cwd-relative
    # `tools/delegate` arm; both are the tree under review's. Not exported, and this
    # is a subshell, so it ends here. The `else` arm is unguarded on purpose: a
    # toolkit without its partials is not installed (conventions.md "Bash in skills").
    ADLC_FENCE_TOOLKIT_ONLY=1
    DELEGATE_TOOLS=
    if [ "${ADLC_FENCE_TOOLKIT_ONLY:-0}" != 1 ] && [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/delegate-tools-path.sh"; fi
    case "$DELEGATE_TOOLS" in
      /*) ;;
      *) _adlc_xf_not_run "the toolkit's tools/delegate did not resolve ('$DELEGATE_TOOLS')" ;;
    esac
    if [ ! -f "$DELEGATE_TOOLS/cross_family.py" ] || [ ! -x "$DELEGATE_TOOLS/emit-run-outcome.sh" ]; then
      _adlc_xf_not_run "cross_family.py or emit-run-outcome.sh is missing from $DELEGATE_TOOLS"
    fi
    command -v python3 >/dev/null 2>&1 || _adlc_xf_not_run 'python3 is not on PATH'

    # --- 1. families, and the gate (never in subagent mode) ------------------------
    _adlc_xf_impl=$(command python3 -E "$_adlc_xf_adlc" harness family 2>/dev/null) || _adlc_xf_impl=unknown
    ADLC_READ_BIN=
    _adlc_xf_gate=1
    if [ "${ADLC_FENCE_TOOLKIT_ONLY:-0}" != 1 ] && [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/delegate-gate.sh"; fi
    # Subagent mode never runs the gate, which probes adlc-read: that path makes no
    # call of adlc-read of any kind, and step 2 records `subagent-mode` before decide.
    # Sourcing the gate above only defines its function.
    if [ "$_adlc_xf_sub" = 0 ]; then
      adlc_delegate_gate_check
      _adlc_xf_gate=$?
      case "$ADLC_READ_BIN" in
        /*) ;;
        *) [ "$_adlc_xf_gate" != 0 ] || _adlc_xf_gate=2 ;;
      esac
      if [ "$_adlc_xf_gate" = 0 ]; then
        _adlc_xf_rev=$(command "$ADLC_READ_BIN" --print-family 2>/dev/null) || _adlc_xf_rev=unknown
      fi
    fi
    # Both through the enum's owner, so the record never carries a value its loader
    # refuses: anything outside model_family.MODEL_FAMILIES reads `unknown` (ADR-2).
    _adlc_xf_fams=$(command python3 -I -c 'import sys
sys.path.insert(0, sys.argv[1])
import model_family as m
print(" ".join(v if v in m.MODEL_FAMILIES else m.UNKNOWN for v in sys.argv[2:]))' \
      "$DELEGATE_TOOLS" "$_adlc_xf_impl" "$_adlc_xf_rev" 2>/dev/null) || _adlc_xf_fams=
    case "$_adlc_xf_fams" in
      *' '*) _adlc_xf_impl=${_adlc_xf_fams%% *}; _adlc_xf_rev=${_adlc_xf_fams#* } ;;
      *) _adlc_xf_impl=unknown; _adlc_xf_rev=unknown ;;
    esac

    # --- 2. subagent mode, decide; a skip records, prints one line, returns ---------
    [ "$_adlc_xf_sub" = 0 ] || _adlc_xf_skip subagent-mode
    _adlc_xf_verdict=$(command python3 -E "$DELEGATE_TOOLS/cross_family.py" decide \
      --subagent "$_adlc_xf_sub" --gate-rc "$_adlc_xf_gate" \
      --implementer "$_adlc_xf_impl" --reviewer "$_adlc_xf_rev" 2>/dev/null) || _adlc_xf_verdict=
    case "$_adlc_xf_verdict" in
      run) ;;
      'skip '*)
        _adlc_xf_reason=${_adlc_xf_verdict#skip }
        case "$_adlc_xf_reason" in
          '' | *[!a-z-]*) _adlc_xf_reason=delegation-disabled ;;
        esac
        _adlc_xf_skip "$_adlc_xf_reason" ;;
      *) _adlc_xf_skip delegation-disabled ;;
    esac

    # --- 3. the question, temp files ------------------------------------------------
    _adlc_xf_q=$(command python3 -E "$DELEGATE_TOOLS/cross_family.py" question 2>/dev/null) || _adlc_xf_q=
    [ -n "$_adlc_xf_q" ] || _adlc_xf_skip redaction-failed
    case "${TMPDIR-}" in
      /*) _adlc_xf_tmp=$TMPDIR ;;
      *) _adlc_xf_tmp=/tmp ;;
    esac
    CORPUS=$(mktemp "$_adlc_xf_tmp/adlc-xfam.XXXXXX" 2>/dev/null) || CORPUS=
    { [ -n "$CORPUS" ] && [ -f "$CORPUS" ]; } || _adlc_xf_skip redaction-failed
    _adlc_xf_out=$(mktemp "$_adlc_xf_tmp/adlc-xfam.XXXXXX" 2>/dev/null) || _adlc_xf_out=
    { [ -n "$_adlc_xf_out" ] && [ -f "$_adlc_xf_out" ]; } || _adlc_xf_skip redaction-failed

    # --- 4. corpus -----------------------------------------------------------------
    [ -e "$_adlc_xf_wt/.git" ] || _adlc_xf_skip redaction-failed
    _adlc_xf_ctx=25
    # Files named as secrets, excluded at any depth from both lists: the redaction
    # chain matches token shapes, and a key file's body has none it knows. The
    # positional parameters, not a string, so no shell word-splits them (BUG-118).
    # icase: a case-insensitive filesystem (macOS) holds `.ENV` and `server.PEM` as
    # readily as the lower-case names (Phase-5 Step D security fix).
    set -- ':(exclude,glob,icase)**/*.pem' ':(exclude,glob,icase)**/*.key' \
      ':(exclude,glob,icase)**/*.p12' ':(exclude,glob,icase)**/*.pfx' \
      ':(exclude,glob,icase)**/*.jks' ':(exclude,glob,icase)**/*.keystore' \
      ':(exclude,glob,icase)**/id_rsa*' ':(exclude,glob,icase)**/id_ed25519*' \
      ':(exclude,glob,icase)**/id_ecdsa*' ':(exclude,glob,icase)**/id_dsa*' \
      ':(exclude,glob,icase)**/.env' ':(exclude,glob,icase)**/.env.*' \
      ':(exclude,glob,icase)**/.envrc' ':(exclude,glob,icase)**/.npmrc' \
      ':(exclude,glob,icase)**/.netrc' ':(exclude,glob,icase)**/.pypirc' \
      ':(exclude,glob,icase)**/.git-credentials' ':(exclude,glob,icase)**/*.tfvars' \
      ':(exclude,glob,icase)**/credentials*.json'
    printf '=== DIFF %s...HEAD (%s lines of context) ===\n' "$_adlc_xf_base" "$_adlc_xf_ctx" > "$CORPUS" || _adlc_xf_skip redaction-failed
    git -C "$_adlc_xf_wt" diff --no-color --no-ext-diff --no-textconv -U"$_adlc_xf_ctx" "$_adlc_xf_base...HEAD" -- "$@" >> "$CORPUS" 2>/dev/null \
      || _adlc_xf_skip redaction-failed
    printf '\n=== CHANGED FILES ===\n' >> "$CORPUS" || _adlc_xf_skip redaction-failed
    git -C "$_adlc_xf_wt" -c core.quotePath=false diff --no-color --name-only "$_adlc_xf_base...HEAD" -- "$@" >> "$CORPUS" 2>/dev/null \
      || _adlc_xf_skip redaction-failed
    printf '\n=== SPECIFICATION RULES ===\n' >> "$CORPUS" || _adlc_xf_skip redaction-failed
    command python3 -E "$DELEGATE_TOOLS/cross_family.py" spec-rules --spec "$_adlc_xf_spec" >> "$CORPUS" 2>/dev/null \
      || _adlc_xf_skip redaction-failed

    # --- 5. redaction: fail closed -------------------------------------------------
    if ! command sed -i.bak -E 's/(sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}|Bearer [A-Za-z0-9._-]{20,}|[A-Z_]{1,64}_(API_KEY|TOKEN)[[:space:]]*[=:][[:space:]]*[^[:space:]]+)/[REDACTED]/g' "$CORPUS" 2>/dev/null; then
      rm -f "$CORPUS.bak"
      _adlc_xf_skip redaction-failed
    fi
    rm -f "$CORPUS.bak"
    [ ! -e "$CORPUS.bak" ] || _adlc_xf_skip redaction-failed

    # --- 6. the one call -------------------------------------------------------------
    case "$ADLC_READ_BIN" in
      /*) ;;
      *) _adlc_xf_skip no-binary ;;
    esac
    command "$ADLC_READ_BIN" --no-warn --paths "$CORPUS" --question "$_adlc_xf_q" > "$_adlc_xf_out" 2>/dev/null
    _adlc_xf_rc=$?
    [ "$_adlc_xf_rc" -eq 0 ] || _adlc_xf_skip api-error

    # --- 7. validate -----------------------------------------------------------------
    _adlc_xf_json=$(command python3 -E "$DELEGATE_TOOLS/cross_family.py" validate \
      --output "$_adlc_xf_out" --worktree "$_adlc_xf_wt" --spec "$_adlc_xf_spec" \
      --base "$_adlc_xf_base" --state "$_adlc_xf_state" 2>/dev/null)
    _adlc_xf_rc=$?
    _adlc_xf_counts=$(printf '%s\n' "$_adlc_xf_json" | command python3 -I -c 'import json, sys
d = json.load(sys.stdin)
print(len(d["findings"]), int(d["dropped"]))' 2>/dev/null) || _adlc_xf_counts=
    _adlc_xf_found=${_adlc_xf_counts%% *}
    _adlc_xf_dropped=${_adlc_xf_counts#* }
    case "$_adlc_xf_found:$_adlc_xf_dropped" in
      *[!0-9:]* | :* | *:) _adlc_xf_found=; _adlc_xf_dropped= ;;
    esac
    if [ "$_adlc_xf_rc" -ne 0 ] || [ -z "$_adlc_xf_found" ]; then
      if [ -n "$_adlc_xf_dropped" ]; then
        _adlc_xf_skip invalid-output --dropped "$_adlc_xf_dropped"
      else
        _adlc_xf_skip invalid-output
      fi
    fi

    # --- 8. record, then the block ---------------------------------------------------
    _adlc_xf_record ran '' --findings "$_adlc_xf_found" --dropped "$_adlc_xf_dropped"
    printf '<cross-family-findings repo="%s">\n%s\n</cross-family-findings>\n' "$_adlc_xf_repo" "$_adlc_xf_json"
    exit 0
  )
}

adlc_cross_family_review() {
  _adlc_xf_main "$@" || :
  return 0
}
