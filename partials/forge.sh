# partials/forge.sh — forge-neutral PR-operation adapter (REQ-520).
#
# The SINGLE place gh/az PR commands live (BR-1). Source this partial, then call
# the adapter functions WITHIN THE SAME fenced block (conventions.md cross-fence
# rule):
#   . .adlc/partials/forge.sh 2>/dev/null || . ~/.claude/skills/partials/forge.sh
#   out=$(adlc_forge_pr_view "$pr" --fields state,url); rc=$?
#
# Provider resolution (BR-2): per-project .adlc/config.yml forge.provider >
# machine ~/.claude/adlc/config.yml forge.provider > auto (origin URL). `auto` on
# an unrecognized host fails loud (never a silent GitHub default). Resolution and
# the key-shaped-auth refusal live in tools/adlc/forge_config.py (no shell YAML
# parsing — REQ-515 ADR-3); the no-config fast path stays pure-shell.
#
# Result/error surface (BR-4), normalized — identical field names from BOTH
# backends. On success: newline-delimited `key=value` lines. On failure:
#   error_class=<auth-missing|pr-not-found|merge-blocked-by-policy|feature-unsupported|network>
#   raw=<verbatim backend stderr>          # never swallowed (LESSON-008)
# and a non-zero return. Distinct failures never collapse into one label.
#
# State normalization (BR-4): pr_view.state in {OPEN, MERGED, CLOSED}. GitHub
# passes through; ADO active->OPEN, completed->MERGED, abandoned->CLOSED.
#
# Backends: github (gh), azure-devops (az repos). The GitHub path is BYTE-COMPATIBLE
# with the pre-migration direct `gh pr` calls (BR-3). ADLC_FORGE_MOCK=1 routes every
# op to an offline fixture dispatcher (BR-10) — no gh/az/network.
#
# Credentials (BR-6): forge.auth is a source NAME (gh/az/an env-var name). PATs are
# read from the named env var at call time, NEVER echoed/logged/sent to telemetry.
#
# Portability (BR-9): prefixed globals (no `local`), no `set -eu` (return codes are
# the contract), no `\b` in grep -E, no bare $<digit>, no [0] indexing, no `status=`,
# no cross-block function state; $? captured immediately after each sub-call. Runs
# under sh/bash/zsh and Ubuntu bash.
#
# ADO REST-via-PAT fallback (documented, NOT shipped in v1 — ADR-2): when `az` is
# absent, each ADO op maps to a single ADO REST call authenticated by the PAT env
# var. The mapping per op:
#   pr_create -> POST  {org}/{proj}/_apis/git/repositories/{repo}/pullrequests?api-version=7.1
#   pr_view   -> GET   .../pullrequests/{id}?api-version=7.1
#   pr_list   -> GET   .../pullrequests?searchCriteria.status=active&api-version=7.1
#   pr_ready  -> PATCH .../pullrequests/{id}  body {"isDraft":false}
#   pr_edit   -> PATCH .../pullrequests/{id}  body {"title":...,"description":...}
#   pr_merge  -> PATCH .../pullrequests/{id}  body {"status":"completed",
#                "completionOptions":{"deleteSourceBranch":true,"mergeStrategy":"squash"}}
#   pr_comment-> POST  .../pullrequests/{id}/threads (thread API) — feature-unsupported in v1
# Auth header: `Authorization: Basic base64(:$PAT)`. A future REQ implements this
# behind the same adapter functions without changing any call site.

# --- internal: resolve provider into ADLC_FORGE_PROVIDER --------------------
# Echoes the provider; exports ADLC_FORGE_PROVIDER. rc!=0 on unrecognized auto.
# Honors the mock override (ADLC_FORGE_MOCK_PROVIDER) so the offline matrix can
# exercise both providers without a real remote.
adlc_forge_provider() {
  adlc_fg_repo=${1:-.}
  if [ "${ADLC_FORGE_MOCK:-0}" = "1" ]; then
    export ADLC_FORGE_PROVIDER="${ADLC_FORGE_MOCK_PROVIDER:-github}"
    printf '%s\n' "$ADLC_FORGE_PROVIDER"
    return 0
  fi
  # Explicit override (callers/tests) short-circuits config + remote probes.
  if [ -n "${ADLC_FORGE_PROVIDER_OVERRIDE:-}" ]; then
    export ADLC_FORGE_PROVIDER="$ADLC_FORGE_PROVIDER_OVERRIDE"
    printf '%s\n' "$ADLC_FORGE_PROVIDER"
    return 0
  fi
  # Config file present anywhere in the precedence chain -> Python resolver
  # (handles project>machine>auto + fail-loud). Otherwise pure-shell auto.
  adlc_fg_cfg_proj="$adlc_fg_repo/.adlc/config.yml"
  adlc_fg_cfg_mach="${ADLC_CONFIG:-${HOME:-}/.claude/adlc/config.yml}"
  if [ -f "$adlc_fg_cfg_proj" ] || [ -f "$adlc_fg_cfg_mach" ]; then
    adlc_fg_pv=$(_adlc_forge_py "$adlc_fg_repo" resolve-provider "$adlc_fg_repo" 2>/dev/null)
    adlc_fg_rc=$?
    if [ "$adlc_fg_rc" -eq 0 ] && [ -n "$adlc_fg_pv" ]; then
      export ADLC_FORGE_PROVIDER="$adlc_fg_pv"
      printf '%s\n' "$ADLC_FORGE_PROVIDER"
      return 0
    fi
    if [ "$adlc_fg_rc" -ne 0 ]; then
      # Resolver failed loud (unrecognized host / bad explicit provider). Surface it.
      _adlc_forge_py "$adlc_fg_repo" resolve-provider "$adlc_fg_repo" >/dev/null
      return 2
    fi
  fi
  # No config: pure-shell auto from origin URL.
  adlc_fg_url=$(git -C "$adlc_fg_repo" remote get-url origin 2>/dev/null)
  case "$adlc_fg_url" in
    *github.com[:/]*)  export ADLC_FORGE_PROVIDER="github" ;;
    *dev.azure.com[:/]*|*.visualstudio.com[:/]*|*.visualstudio.com:*)
                       export ADLC_FORGE_PROVIDER="azure-devops" ;;
    "") echo "forge: cannot auto-detect provider: no 'origin' remote. Set forge.provider in .adlc/config.yml (github|azure-devops)." >&2
        return 2 ;;
    *)  echo "forge: cannot auto-detect provider from origin URL '$adlc_fg_url'. Supported: github, azure-devops. Set forge.provider explicitly." >&2
        return 2 ;;
  esac
  printf '%s\n' "$ADLC_FORGE_PROVIDER"
  return 0
}

# Locate and invoke forge_config.py with the two-level fallback (project vendored
# copy first, then toolkit). Args after the repo are passed to the script.
_adlc_forge_py() {
  adlc_fp_repo=$1
  shift
  adlc_fp_local="$adlc_fp_repo/tools/adlc/forge_config.py"
  adlc_fp_vend="$adlc_fp_repo/.adlc/tools/adlc/forge_config.py"
  adlc_fp_glob="${HOME:-}/.claude/skills/tools/adlc/forge_config.py"
  if [ -f "$adlc_fp_local" ]; then
    python3 "$adlc_fp_local" "$@"
  elif [ -f "$adlc_fp_vend" ]; then
    python3 "$adlc_fp_vend" "$@"
  else
    python3 "$adlc_fp_glob" "$@"
  fi
}

# --- internal: normalized error emission ------------------------------------
# _adlc_forge_err <class> <raw-stderr-file-or-string>
# Echoes the normalized class + verbatim raw stderr beneath it (BR-4).
_adlc_forge_err() {
  adlc_fe_class=$1
  adlc_fe_raw=$2
  printf 'error_class=%s\n' "$adlc_fe_class"
  if [ -f "$adlc_fe_raw" ]; then
    while IFS= read -r adlc_fe_line; do
      printf 'raw=%s\n' "$adlc_fe_line"
    done < "$adlc_fe_raw"
  elif [ -n "$adlc_fe_raw" ]; then
    printf 'raw=%s\n' "$adlc_fe_raw"
  fi
}

# Classify backend stderr into a normalized error class. Order matters: the most
# specific signatures first. Anything unmatched is `network` (the conservative
# default for "the call failed but we can't attribute it") — callers still get the
# raw stderr beneath it, so nothing is lost (BR-4).
_adlc_forge_classify() {
  adlc_fc_raw=$1
  case "$adlc_fc_raw" in
    *"not logged"*|*"auth status"*|*"authentication"*|*"Unauthorized"*|*"TF400813"*|*"PAT"*"not set"*|*"auth-missing"*|*"az login"*|*"gh auth login"*|*"Please run"*"login"*|*"credentials"*)
      echo "auth-missing" ;;
    *"not found"*|*"Not Found"*|*"could not resolve"*|*"no pull request"*|*"TF401174"*)
      echo "pr-not-found" ;;
    *"policy"*|*"Policy"*|*"required review"*|*"branch protection"*|*"TF402455"*|*"not mergeable"*|*"blocked"*)
      echo "merge-blocked-by-policy" ;;
    *"unsupported"*|*"not supported"*|*"feature-unsupported"*)
      echo "feature-unsupported" ;;
    *)
      echo "network" ;;
  esac
}

# --- mock backend (BR-10) ---------------------------------------------------
# Deterministic offline fixtures keyed by (op, ADLC_FORGE_MOCK_PROVIDER,
# ADLC_FORGE_MOCK_SCENARIO). SCENARIO defaults to `ok`; set it to an error-class
# name to drive the failure path. Honors provider semantics faithfully:
# ADO pr_comment is feature-unsupported; state normalization differs by provider.
_adlc_forge_mock() {
  adlc_mk_op=$1
  adlc_mk_prov="${ADLC_FORGE_MOCK_PROVIDER:-github}"
  adlc_mk_scn="${ADLC_FORGE_MOCK_SCENARIO:-ok}"
  # ADO pr_comment is always feature-unsupported in v1, regardless of scenario.
  if [ "$adlc_mk_op" = "pr_comment" ] && [ "$adlc_mk_prov" = "azure-devops" ]; then
    _adlc_forge_err "feature-unsupported" "ADO pr_comment is not supported in v1 (no az repos comment subcommand; REST thread API deferred)"
    return 1
  fi
  case "$adlc_mk_scn" in
    ok) : ;;
    auth-missing|pr-not-found|merge-blocked-by-policy|feature-unsupported|network)
      _adlc_forge_err "$adlc_mk_scn" "mock backend ($adlc_mk_prov): simulated $adlc_mk_scn for $adlc_mk_op"
      return 1 ;;
    *)
      _adlc_forge_err "network" "mock backend: unknown scenario '$adlc_mk_scn'"
      return 1 ;;
  esac
  # Happy-path normalized output per op. State normalization is provider-aware:
  # the mock returns already-normalized OPEN/MERGED/CLOSED (the adapter's job).
  case "$adlc_mk_op" in
    pr_create) printf 'url=%s\nnumber=%s\nstate=OPEN\n' "https://mock.forge/$adlc_mk_prov/pr/101" "101" ;;
    pr_ready)  printf 'state=OPEN\n' ;;
    pr_edit)   printf 'url=%s\n' "https://mock.forge/$adlc_mk_prov/pr/101" ;;
    pr_view)   printf 'number=%s\nurl=%s\nstate=%s\nmergedAt=%s\nbody=%s\n' "101" "https://mock.forge/$adlc_mk_prov/pr/101" "OPEN" "" "mock body" ;;
    pr_list)   printf 'number=101|url=https://mock.forge/%s/pr/101|head=feat/REQ-520-forge-adapter\n' "$adlc_mk_prov" ;;
    pr_merge)  printf 'state=MERGED\n' ;;
    pr_comment) printf 'ok=1\n' ;;
    *) _adlc_forge_err "network" "mock backend: unknown op '$adlc_mk_op'"; return 1 ;;
  esac
  return 0
}

# --- backend runner: run a command, capture stderr, classify on failure ------
# _adlc_forge_run -- <cmd...>
# A leading `--` sentinel separates the runner's own (currently none) options from
# the command argv; it is shifted off before exec. Runs the command; on success
# streams stdout; on failure classifies stderr and emits the normalized error
# block. Returns the command's rc (non-zero on failure).
_adlc_forge_run() {
  [ "$1" = "--" ] && shift
  adlc_rn_errf=$(mktemp 2>/dev/null || mktemp -t forge)
  # shellcheck disable=SC2068 — intentional: run the passed argv as the command.
  adlc_rn_out=$("$@" 2>"$adlc_rn_errf")
  adlc_rn_rc=$?
  if [ "$adlc_rn_rc" -eq 0 ]; then
    [ -n "$adlc_rn_out" ] && printf '%s\n' "$adlc_rn_out"
    rm -f "$adlc_rn_errf"
    return 0
  fi
  adlc_rn_rawall=$(cat "$adlc_rn_errf" 2>/dev/null)
  adlc_rn_class=$(_adlc_forge_classify "$adlc_rn_rawall")
  _adlc_forge_err "$adlc_rn_class" "$adlc_rn_errf"
  rm -f "$adlc_rn_errf"
  return "$adlc_rn_rc"
}

# ============================================================================
# Public ops. Each resolves the provider (cheap, cached in ADLC_FORGE_PROVIDER),
# then dispatches. The GitHub branch reproduces the exact pre-migration `gh`
# command/flags (BR-3). All ops honor ADLC_FORGE_MOCK.
# ============================================================================

# adlc_forge_pr_create --base B --head H --title T --body BODY [--draft]
adlc_forge_pr_create() {
  [ "${ADLC_FORGE_MOCK:-0}" = "1" ] && { _adlc_forge_mock pr_create; return $?; }
  adlc_forge_provider "${ADLC_FORGE_REPO:-.}" >/dev/null || return 2
  case "$ADLC_FORGE_PROVIDER" in
    github)
      # Byte-compatible with: gh pr create --base .. --head .. --title .. --body .. [--draft]
      # gh pr create prints the new PR URL on stdout. Normalize it to url=/state=.
      adlc_fc_out=$(_adlc_forge_run -- gh pr create "$@"); adlc_fc_rc=$?
      [ "$adlc_fc_rc" -ne 0 ] && { printf '%s\n' "$adlc_fc_out"; return "$adlc_fc_rc"; }
      # The runner already streamed the raw URL; re-emit as a normalized field too.
      printf 'url=%s\nstate=OPEN\n' "$adlc_fc_out"; return 0 ;;
    azure-devops)
      _adlc_forge_run -- az repos pr create "$@"; return $? ;;
    *) _adlc_forge_err "feature-unsupported" "no backend for provider '$ADLC_FORGE_PROVIDER'"; return 1 ;;
  esac
}

# adlc_forge_pr_ready <number|url>
adlc_forge_pr_ready() {
  [ "${ADLC_FORGE_MOCK:-0}" = "1" ] && { _adlc_forge_mock pr_ready; return $?; }
  adlc_forge_provider "${ADLC_FORGE_REPO:-.}" >/dev/null || return 2
  case "$ADLC_FORGE_PROVIDER" in
    github)       _adlc_forge_run -- gh pr ready "$@"; adlc_fr_rc=$?; [ "$adlc_fr_rc" -eq 0 ] && printf 'state=OPEN\n'; return "$adlc_fr_rc" ;;
    azure-devops) _adlc_forge_run -- az repos pr update --id "$@" --draft false; adlc_fr_rc=$?; [ "$adlc_fr_rc" -eq 0 ] && printf 'state=OPEN\n'; return "$adlc_fr_rc" ;;
    *) _adlc_forge_err "feature-unsupported" "no backend for provider '$ADLC_FORGE_PROVIDER'"; return 1 ;;
  esac
}

# adlc_forge_pr_edit <number|url> [--title T] [--body BODY] [--body-file F]
adlc_forge_pr_edit() {
  [ "${ADLC_FORGE_MOCK:-0}" = "1" ] && { _adlc_forge_mock pr_edit; return $?; }
  adlc_forge_provider "${ADLC_FORGE_REPO:-.}" >/dev/null || return 2
  case "$ADLC_FORGE_PROVIDER" in
    github)       _adlc_forge_run -- gh pr edit "$@"; return $? ;;
    azure-devops)
      # gh's --title/--body map to az repos pr update --title/--description; caller
      # passes gh-shaped flags, the ADO call-site adapter translates. For v1 the
      # migrated call sites pass gh-shaped flags only through the github branch;
      # ADO edit goes through az with the id positional.
      _adlc_forge_run -- az repos pr update --id "$@"; return $? ;;
    *) _adlc_forge_err "feature-unsupported" "no backend for provider '$ADLC_FORGE_PROVIDER'"; return 1 ;;
  esac
}

# adlc_forge_pr_view <number|url> --fields f1,f2,...   (normalized mode)
#                    | <number|url> --json … [-q …] [-R …]   (raw passthrough)
#
# Two modes, by flag shape:
#   * --fields f1,f2,…  -> normalized: emits requested fields as key=value with
#     state coerced to {OPEN,MERGED,CLOSED} (the cross-backend contract).
#   * gh-native --json/-q/--jq/-R (no --fields) -> raw passthrough: the GitHub
#     backend forwards the WHOLE argv verbatim to `gh pr view`, so callers that
#     need the raw body string (e.g. footprint reads) stay byte-identical (BR-3).
#     ADO has no raw-gh shape; it always normalizes via `az repos pr show`.
adlc_forge_pr_view() {
  [ "${ADLC_FORGE_MOCK:-0}" = "1" ] && { _adlc_forge_mock pr_view; return $?; }
  adlc_fv_ref=""
  adlc_fv_fields=""
  adlc_fv_raw_mode=0
  for adlc_fv_a in "$@"; do
    case "$adlc_fv_a" in
      --json|-q|--jq|-R|--repo) adlc_fv_raw_mode=1 ;;
    esac
  done
  # Locate --fields (normalized mode) and the ref positional without consuming
  # the gh-native flags (which raw mode forwards verbatim).
  adlc_fv_prev=""
  for adlc_fv_a in "$@"; do
    if [ "$adlc_fv_prev" = "--fields" ]; then adlc_fv_fields=$adlc_fv_a; fi
    case "$adlc_fv_a" in
      --*|-*) : ;;
      *) [ -z "$adlc_fv_ref" ] && [ "$adlc_fv_prev" != "--fields" ] && adlc_fv_ref=$adlc_fv_a ;;
    esac
    adlc_fv_prev=$adlc_fv_a
  done
  [ -n "$adlc_fv_fields" ] && adlc_fv_raw_mode=0
  [ -n "$adlc_fv_fields" ] || adlc_fv_fields="state,url,number"
  adlc_forge_provider "${ADLC_FORGE_REPO:-.}" >/dev/null || return 2
  case "$ADLC_FORGE_PROVIDER" in
    github)
      if [ "$adlc_fv_raw_mode" = "1" ]; then
        # Byte-compatible raw passthrough: exactly `gh pr view <args…>`.
        _adlc_forge_run -- gh pr view "$@"; return $?
      fi
      adlc_fv_raw=$(_adlc_forge_run -- gh pr view "$adlc_fv_ref" --json "$adlc_fv_fields"); adlc_fv_rc=$?
      [ "$adlc_fv_rc" -ne 0 ] && { printf '%s\n' "$adlc_fv_raw"; return "$adlc_fv_rc"; }
      # GitHub states already match {OPEN,MERGED,CLOSED}; emit normalized k=v.
      printf '%s\n' "$adlc_fv_raw" | _adlc_forge_json_to_kv ;;
    azure-devops)
      adlc_fv_raw=$(_adlc_forge_run -- az repos pr show --id "$adlc_fv_ref"); adlc_fv_rc=$?
      [ "$adlc_fv_rc" -ne 0 ] && { printf '%s\n' "$adlc_fv_raw"; return "$adlc_fv_rc"; }
      # ADO status active|completed|abandoned -> OPEN|MERGED|CLOSED (BR-4).
      printf '%s\n' "$adlc_fv_raw" | _adlc_forge_ado_view_to_kv ;;
    *) _adlc_forge_err "feature-unsupported" "no backend for provider '$ADLC_FORGE_PROVIDER'"; return 1 ;;
  esac
}

# adlc_forge_pr_list --state open --branch-pattern PAT
adlc_forge_pr_list() {
  [ "${ADLC_FORGE_MOCK:-0}" = "1" ] && { _adlc_forge_mock pr_list; return $?; }
  adlc_forge_provider "${ADLC_FORGE_REPO:-.}" >/dev/null || return 2
  case "$ADLC_FORGE_PROVIDER" in
    github)       _adlc_forge_run -- gh pr list "$@"; return $? ;;
    azure-devops) _adlc_forge_run -- az repos pr list "$@"; return $? ;;
    *) _adlc_forge_err "feature-unsupported" "no backend for provider '$ADLC_FORGE_PROVIDER'"; return 1 ;;
  esac
}

# adlc_forge_pr_merge <number|url> [--squash] [--delete-branch]
adlc_forge_pr_merge() {
  [ "${ADLC_FORGE_MOCK:-0}" = "1" ] && { _adlc_forge_mock pr_merge; return $?; }
  adlc_forge_provider "${ADLC_FORGE_REPO:-.}" >/dev/null || return 2
  case "$ADLC_FORGE_PROVIDER" in
    github)
      _adlc_forge_run -- gh pr merge "$@"; adlc_fm_rc=$?
      [ "$adlc_fm_rc" -eq 0 ] && printf 'state=MERGED\n'; return "$adlc_fm_rc" ;;
    azure-devops)
      # REQ-523 BR-9: callers pass gh-shaped flags (`<ref> --squash --delete-branch`).
      # `az repos pr update` does NOT understand `--squash` (bare) or `--delete-branch`;
      # forwarding "$@" verbatim made the ADO merge error out. Split the PR ref (first
      # non-flag positional) from the gh-shaped flags and TRANSLATE:
      #   --squash         -> --squash true
      #   --delete-branch  -> --delete-source-branch true
      # Other gh-only flags (e.g. --merge/--rebase/--admin) are dropped for v1; never
      # forwarded verbatim. --status completed is always set (auto-complete the PR).
      # Build the az flag list portably (no arrays — sh/bash/zsh parity): rebuild the
      # positional set so the ref and translated flags survive word boundaries safely.
      adlc_fm_ref=""
      adlc_fm_squash=""
      adlc_fm_delsrc=""
      for adlc_fm_a in "$@"; do
        case "$adlc_fm_a" in
          --squash)        adlc_fm_squash="--squash true" ;;
          --delete-branch) adlc_fm_delsrc="--delete-source-branch true" ;;
          --merge|--rebase|--admin|--auto) : ;;  # gh-only; drop (never forward to az)
          --*) : ;;                               # any other gh-only flag; drop
          *) [ -z "$adlc_fm_ref" ] && adlc_fm_ref="$adlc_fm_a" ;;  # first positional = ref
        esac
      done
      if [ -z "$adlc_fm_ref" ]; then
        _adlc_forge_err "pr-not-found" "adlc_forge_pr_merge (azure-devops): no PR id/url positional in args: $*"
        return 1
      fi
      # Rebuild argv as: --id <ref> --status completed [--squash true] [--delete-source-branch true]
      # via `set --` so each translated token is a distinct word (no eval, no array).
      set -- --id "$adlc_fm_ref" --status completed
      [ -n "$adlc_fm_squash" ] && set -- "$@" --squash true
      [ -n "$adlc_fm_delsrc" ] && set -- "$@" --delete-source-branch true
      # Policy blocks surface as merge-blocked-by-policy via the classifier (never
      # bypassed — ethos #6).
      _adlc_forge_run -- az repos pr update "$@"; adlc_fm_rc=$?
      [ "$adlc_fm_rc" -eq 0 ] && printf 'state=MERGED\n'; return "$adlc_fm_rc" ;;
    *) _adlc_forge_err "feature-unsupported" "no backend for provider '$ADLC_FORGE_PROVIDER'"; return 1 ;;
  esac
}

# adlc_forge_pr_comment <number|url> --body BODY
adlc_forge_pr_comment() {
  [ "${ADLC_FORGE_MOCK:-0}" = "1" ] && { _adlc_forge_mock pr_comment; return $?; }
  adlc_forge_provider "${ADLC_FORGE_REPO:-.}" >/dev/null || return 2
  case "$ADLC_FORGE_PROVIDER" in
    github)       _adlc_forge_run -- gh pr comment "$@"; adlc_fcm_rc=$?; [ "$adlc_fcm_rc" -eq 0 ] && printf 'ok=1\n'; return "$adlc_fcm_rc" ;;
    azure-devops) _adlc_forge_err "feature-unsupported" "ADO pr_comment is not supported in v1 (no az repos comment subcommand; REST thread API deferred)"; return 1 ;;
    *) _adlc_forge_err "feature-unsupported" "no backend for provider '$ADLC_FORGE_PROVIDER'"; return 1 ;;
  esac
}

# --- JSON -> key=value helpers (no jq dependency; gh emits compact JSON) -----
# GitHub: pass-through state. Minimal parser for the flat fields gh --json emits.
_adlc_forge_json_to_kv() {
  python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if isinstance(d, dict):
    for k, v in d.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, separators=(",", ":"))
        print(f"{k}={v}")
'
}

# ADO: normalize `status` -> state {OPEN,MERGED,CLOSED}; surface url/number/title.
_adlc_forge_ado_view_to_kv() {
  python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if not isinstance(d, dict):
    sys.exit(0)
status = (d.get("status") or "").lower()
state = {"active": "OPEN", "completed": "MERGED", "abandoned": "CLOSED"}.get(status, status.upper())
print(f"state={state}")
num = d.get("pullRequestId")
if num is not None:
    print(f"number={num}")
url = d.get("url") or d.get("_links", {}).get("web", {}).get("href")
if url:
    print(f"url={url}")
ct = d.get("closedDate")
if status == "completed" and ct:
    print(f"mergedAt={ct}")
desc = d.get("description")
if desc is not None:
    print(f"body={desc}")
'
}
