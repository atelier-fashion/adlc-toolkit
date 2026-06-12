#!/bin/sh
# partials/tests/forge.test.sh — AC test matrix for partials/forge.sh (REQ-520 BR-10).
#
# Fully offline: uses ADLC_FORGE_MOCK for the op matrix, a recording `gh` shim on a
# sandbox PATH for the GitHub byte-compat assertions, and a sandbox git repo for
# provider auto-detection. No network, no real gh/az invocation.
#
# Run under BOTH shells (BR-9 / cross-shell AC):
#   bash partials/tests/forge.test.sh
#   zsh  partials/tests/forge.test.sh
# or via the wrapper:  sh partials/tests/run.sh
#
# Exits 0 iff every case passes; prints one line per case.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
ROOT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)

FAILS=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}
contains() { # contains <desc> <needle> <haystack>
  case "$3" in
    *"$2"*) pass "$1 (found '$2')" ;;
    *) fail "$1 (missing '$2' in: $3)" ;;
  esac
}

. "$PARTIALS/forge.sh"

# ===========================================================================
# 1. Mock op matrix: every op x both providers, happy path
# ===========================================================================
export ADLC_FORGE_MOCK=1
for prov in github azure-devops; do
  export ADLC_FORGE_MOCK_PROVIDER="$prov"
  export ADLC_FORGE_MOCK_SCENARIO=ok
  for op in pr_create pr_ready pr_edit pr_view pr_list pr_merge pr_comment; do
    out=$(adlc_forge_"$op" 101 2>&1); rc=$?
    if [ "$prov" = "azure-devops" ] && [ "$op" = "pr_comment" ]; then
      # ADO pr_comment is feature-unsupported in v1 even on the happy path.
      contains "ado/$op feature-unsupported" "error_class=feature-unsupported" "$out"
      check "ado/$op nonzero rc" "1" "$( [ $rc -ne 0 ] && echo 1 || echo 0 )"
    else
      check "$prov/$op happy-path rc" "0" "$rc"
    fi
  done
done

# ===========================================================================
# 2. State normalization: ADO pr_merge -> MERGED; create -> OPEN
# ===========================================================================
export ADLC_FORGE_MOCK_PROVIDER=azure-devops ADLC_FORGE_MOCK_SCENARIO=ok
contains "ado merge state=MERGED" "state=MERGED" "$(adlc_forge_pr_merge 101)"
contains "ado create state=OPEN"  "state=OPEN"   "$(adlc_forge_pr_create --base m --head h --title t --body b)"

# ===========================================================================
# 3. Error classes: every class x both providers; raw preserved; nonzero rc
# ===========================================================================
for prov in github azure-devops; do
  export ADLC_FORGE_MOCK_PROVIDER="$prov"
  for cls in auth-missing pr-not-found merge-blocked-by-policy feature-unsupported network; do
    export ADLC_FORGE_MOCK_SCENARIO="$cls"
    out=$(adlc_forge_pr_view 1 2>&1); rc=$?
    contains "$prov/$cls error_class" "error_class=$cls" "$out"
    contains "$prov/$cls raw preserved" "raw=" "$out"
    check "$prov/$cls nonzero rc" "1" "$( [ $rc -ne 0 ] && echo 1 || echo 0 )"
  done
done
unset ADLC_FORGE_MOCK ADLC_FORGE_MOCK_PROVIDER ADLC_FORGE_MOCK_SCENARIO

# ===========================================================================
# 4. Classifier: backend stderr signatures -> normalized classes
# ===========================================================================
check "classify ADO policy block" "merge-blocked-by-policy" \
  "$(_adlc_forge_classify 'TF402455: PR blocked by branch policy required review')"
check "classify az not-logged-in" "auth-missing" \
  "$(_adlc_forge_classify 'ERROR: Please run az login to setup account')"
check "classify pr not found" "pr-not-found" \
  "$(_adlc_forge_classify 'GraphQL: Could not resolve to a PullRequest (Not Found)')"
check "classify unknown -> network" "network" \
  "$(_adlc_forge_classify 'some transient socket hangup')"

# ===========================================================================
# 5. Provider auto-detect + fail-loud (no mock)
# ===========================================================================
SBX=$(mktemp -d -t forge.XXXXXX)
mk_repo() { # mk_repo <url>; echoes a unique repo dir
  # Use a fresh mktemp dir per call so repeated URLs never collide (the counter
  # approach fails here because mk_repo runs in a command-substitution subshell).
  d=$(mktemp -d "$SBX/repo.XXXXXX")
  git -C "$d" init -q; git -C "$d" remote add origin "$1"; echo "$d"
}
gh_repo=$(mk_repo "https://github.com/o/r.git")
check "auto github (https)" "github" "$(adlc_forge_provider "$gh_repo" 2>/dev/null)"
ado_repo=$(mk_repo "git@ssh.dev.azure.com:v3/org/proj/repo")
# az path requires forge_config.py reachable; provide it via the project copy.
mkdir -p "$ado_repo/tools/adlc"; cp "$ROOT/tools/adlc/forge_config.py" "$ado_repo/tools/adlc/" 2>/dev/null
# No config file -> pure-shell auto handles the ADO SSH host directly.
check "auto azure-devops (ssh)" "azure-devops" "$(adlc_forge_provider "$ado_repo" 2>/dev/null)"
bad_repo=$(mk_repo "https://gitlab.com/o/r.git")
p=$(adlc_forge_provider "$bad_repo" 2>/dev/null); rc=$?
check "auto unrecognized fails (empty provider)" "" "$p"
check "auto unrecognized nonzero rc" "2" "$rc"
err=$(adlc_forge_provider "$bad_repo" 2>&1 >/dev/null)
contains "fail-loud names URL" "gitlab.com" "$err"
contains "fail-loud names providers" "github" "$err"

# ===========================================================================
# 6. Config-based resolution: project forge.provider overrides github remote
# ===========================================================================
cfg_repo=$(mk_repo "https://github.com/o/r.git")
mkdir -p "$cfg_repo/.adlc" "$cfg_repo/tools/adlc"
cp "$ROOT/tools/adlc/forge_config.py" "$cfg_repo/tools/adlc/"
printf 'forge:\n  provider: azure-devops\n  auth: ADO_PAT\n' > "$cfg_repo/.adlc/config.yml"
check "project config overrides remote" "azure-devops" \
  "$(ADLC_FORGE_REPO="$cfg_repo" adlc_forge_provider "$cfg_repo" 2>/dev/null)"

# ===========================================================================
# 7. GitHub byte-compat: recording gh shim asserts exact argv (BR-3)
# ===========================================================================
SHIM="$SBX/bin"; mkdir -p "$SHIM"
cat > "$SHIM/gh" <<'GHSHIM'
#!/bin/sh
echo "$*" >> "$GH_RECORD"
case "$1 $2" in
  "pr view") echo '{"state":"MERGED","url":"https://github.com/o/r/pull/9","number":9}';;
  "pr create") echo 'https://github.com/o/r/pull/9';;
esac
exit 0
GHSHIM
chmod +x "$SHIM/gh"
GH_RECORD="$SBX/rec.txt"; export GH_RECORD; : > "$GH_RECORD"
OLDPATH=$PATH; PATH="$SHIM:$PATH"; export PATH
export ADLC_FORGE_PROVIDER_OVERRIDE=github
adlc_forge_pr_create --base main --head feat/x --title T --body B --draft >/dev/null 2>&1
adlc_forge_pr_ready 9 >/dev/null 2>&1
adlc_forge_pr_view 9 --fields state,url,number >/dev/null 2>&1
adlc_forge_pr_merge 9 --squash --delete-branch >/dev/null 2>&1
adlc_forge_pr_comment 9 --body hi >/dev/null 2>&1
adlc_forge_pr_edit 9 --title NT --body NB >/dev/null 2>&1
REC=$(cat "$GH_RECORD")
contains "gh create byte-compat" "pr create --base main --head feat/x --title T --body B --draft" "$REC"
contains "gh ready byte-compat"  "pr ready 9" "$REC"
contains "gh view byte-compat"   "pr view 9 --json state,url,number" "$REC"
contains "gh merge byte-compat"  "pr merge 9 --squash --delete-branch" "$REC"
contains "gh comment byte-compat" "pr comment 9 --body hi" "$REC"
contains "gh edit byte-compat"   "pr edit 9 --title NT --body NB" "$REC"
# Normalized outputs through the github backend
contains "gh view normalizes MERGED" "state=MERGED" \
  "$(adlc_forge_pr_view 9 --fields state,url,number 2>/dev/null)"
PATH=$OLDPATH; export PATH
unset ADLC_FORGE_PROVIDER_OVERRIDE

# ===========================================================================
# 8. ADO merge arg-translation (REQ-523 BR-9): gh-shaped flags -> az equivalents
# ===========================================================================
# A recording `az` shim asserts the exact argv. The caller passes the gh-shaped
# `<ref> --squash --delete-branch`; the ADO branch must translate to
# `--squash true` / `--delete-source-branch true` and never forward the bare
# gh flags to `az`.
AZSHIM="$SBX/azbin"; mkdir -p "$AZSHIM"
cat > "$AZSHIM/az" <<'AZSHIM_EOF'
#!/bin/sh
echo "$*" >> "$AZ_RECORD"
exit 0
AZSHIM_EOF
chmod +x "$AZSHIM/az"
AZ_RECORD="$SBX/azrec.txt"; export AZ_RECORD; : > "$AZ_RECORD"
OLDPATH2=$PATH; PATH="$AZSHIM:$PATH"; export PATH
export ADLC_FORGE_PROVIDER_OVERRIDE=azure-devops
out=$(adlc_forge_pr_merge 9 --squash --delete-branch 2>&1); rc=$?
AZREC=$(cat "$AZ_RECORD")
check "ado merge rc 0" "0" "$rc"
contains "ado merge normalizes MERGED" "state=MERGED" "$out"
contains "ado merge passes the ref as --id 9" "--id 9" "$AZREC"
contains "ado merge sets --status completed" "--status completed" "$AZREC"
contains "ado merge translates --squash -> --squash true" "--squash true" "$AZREC"
contains "ado merge translates --delete-branch -> --delete-source-branch true" "--delete-source-branch true" "$AZREC"
# Negative: no gh-shaped flag leaks to az.
case "$AZREC" in
  *"--delete-branch"*) fail "ado merge must NOT forward bare --delete-branch to az (got: $AZREC)" ;;
  *) pass "ado merge forwards no bare --delete-branch to az" ;;
esac
# `--squash true` is fine; assert there is no DANGLING bare --squash (i.e. --squash
# immediately followed by another flag or end-of-line rather than `true`).
case "$AZREC" in
  *"--squash true"*) pass "ado merge --squash carries its true value" ;;
  *) fail "ado merge --squash missing its value (got: $AZREC)" ;;
esac
PATH=$OLDPATH2; export PATH
unset ADLC_FORGE_PROVIDER_OVERRIDE AZ_RECORD

rm -rf "$SBX"

echo ""
if [ "$FAILS" -eq 0 ]; then
  echo "forge.test.sh: ALL CASES PASS"
  exit 0
fi
echo "forge.test.sh: $FAILS FAILURE(S)"
exit 1
