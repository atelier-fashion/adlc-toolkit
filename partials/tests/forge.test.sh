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

# ---------------------------------------------------------------------------
# 4b. BUG-201: branch-protection refusals must be merge-blocked-by-policy, not
# `network`. The classifier's fall-through default is `network`, so a refusal
# signature the patterns do not know about does not fail loudly — it silently
# acquires the class that reads as transient and invites a retry, when the fix
# is to update the branch / wait for checks / get a review. Each string below is
# real backend stderr; they are pinned so a future pattern edit cannot quietly
# re-widen the default. (No `for x in $VAR` word-splitting here — BUG-118.)
# ---------------------------------------------------------------------------
pol() { check "classify policy: $1" "merge-blocked-by-policy" "$(_adlc_forge_classify "$2")"; }

# GitHub: the GraphQL mergePullRequest refusals.
pol "required status checks" \
  'GraphQL: 4 of 4 required status checks are expected. (mergePullRequest)'
pol "Required status check (singular)" \
  'GraphQL: Required status check "build" is expected. (mergePullRequest)'
pol "base branch modified" \
  'GraphQL: Base branch was modified. Review and try the merge again. (mergePullRequest)'
pol "changes via pull request" \
  'GraphQL: Changes must be made through a pull request. (mergePullRequest)'
pol "approving review required" \
  'GraphQL: At least 1 approving review is required by reviewers with write access. (mergePullRequest)'
pol "code-owner review" \
  'GraphQL: Required review from Code Owners is missing. (mergePullRequest)'
pol "merge queue" \
  'GraphQL: Changes must be made through the merge queue. (mergePullRequest)'
pol "not authorized to push" \
  "GraphQL: You're not authorized to push to this branch. (mergePullRequest)"
pol "protected branch (push)" \
  'remote: error: GH006: Protected branch update failed for refs/heads/main.'
# Already covered pre-BUG-201 by *"not mergeable"* — pinned as a regression anchor.
pol "not mergeable (pre-existing)" \
  'GraphQL: Pull request is not mergeable (mergePullRequest)'

# ADO: the same classifier serves `az`, and its refusals say "policies" (plural),
# which *"policy"* does NOT match. Pre-BUG-201 these were classed correctly only
# when the message happened to carry a TF code.
pol "ADO policies not met" \
  'ERROR: The pull request has policies that are not met'
pol "ADO single policy not met" \
  'ERROR: One or more merge policies is not met'
pol "ADO approval required" \
  'ERROR: The pull request must be approved before it can be completed.'

# Negative anchors: the added patterns must not steal from the other classes.
check "classify real network error" "network" \
  "$(_adlc_forge_classify 'error connecting to api.github.com: dial tcp: i/o timeout')"
check "classify gh not-logged-in" "auth-missing" \
  "$(_adlc_forge_classify 'gh: set the GH_TOKEN. Please run gh auth login')"
check "classify ADO pr missing" "pr-not-found" \
  "$(_adlc_forge_classify 'ERROR: TF401174: The pull request does not exist')"
check "classify local git failure" "local-git" \
  "$(_adlc_forge_classify "failed to run git: fatal: 'main' is already used by worktree")"
check "classify ADO comment unsupported" "feature-unsupported" \
  "$(_adlc_forge_classify 'ADO pr_comment is not supported in v1')"

# ---------------------------------------------------------------------------
# 4c. BR-4 doc-contract guard: every class the classifier can EMIT must be named
# in the header's error_class=<...> enumeration. BUG-201 was filed against that
# contract; the header had itself fallen behind `local-git` (added by BUG-150)
# with nothing to catch it. This is the check that would have caught it.
# ---------------------------------------------------------------------------
EMITTED=$(awk '/^_adlc_forge_classify\(\)/{f=1} f&&/^}/{f=0} f' "$PARTIALS/forge.sh" \
  | sed -n 's/.*echo "\([a-z-]*\)".*/\1/p' | sort -u)
DOCUMENTED=$(awk '/error_class=</{f=1} f{print} f&&/>/{exit}' "$PARTIALS/forge.sh" \
  | tr '<>|' '\n\n\n' | sed -n 's/^#* *\([a-z][a-z-]*\)$/\1/p' | sort -u)
# Set difference via `comm` on the two sorted lists, NOT a `case` inside `$( )`:
# bash 3.2 mis-parses the unbalanced `)` of a case arm within a command
# substitution and dies with "syntax error near unexpected token `;;'".
_emf=$(mktemp 2>/dev/null || mktemp -t forge_em)
_dcf=$(mktemp 2>/dev/null || mktemp -t forge_dc)
printf '%s\n' "$EMITTED" > "$_emf"
printf '%s\n' "$DOCUMENTED" > "$_dcf"
MISSING=$(comm -23 "$_emf" "$_dcf" | tr '\n' ' ' | sed 's/  *$//')
rm -f "$_emf" "$_dcf"
check "BR-4 header names every emitted class" "" "$MISSING"
# Non-vacuity: the extraction must actually have found the class set.
contains "emitted-class extraction non-vacuous" "merge-blocked-by-policy" "$EMITTED"
contains "documented-class extraction non-vacuous" "merge-blocked-by-policy" "$DOCUMENTED"

# ---------------------------------------------------------------------------
# 4d. The mock (BR-10) must honor every class the classifier emits. Before
# BUG-201 `local-git` was not in the scenario list, so it fell to the
# unknown-scenario arm and came back as `network` — the same mislabel this bug
# is about, reproduced inside the offline harness.
# ---------------------------------------------------------------------------
export ADLC_FORGE_MOCK=1 ADLC_FORGE_MOCK_PROVIDER=github ADLC_FORGE_MOCK_SCENARIO=local-git
contains "mock honors local-git scenario" "error_class=local-git" "$(adlc_forge_pr_merge 101 2>&1)"
export ADLC_FORGE_MOCK_SCENARIO=merge-blocked-by-policy
contains "mock pr_merge policy refusal" "error_class=merge-blocked-by-policy" \
  "$(adlc_forge_pr_merge 101 --squash --delete-branch 2>&1)"
unset ADLC_FORGE_MOCK ADLC_FORGE_MOCK_PROVIDER ADLC_FORGE_MOCK_SCENARIO

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
# 7b. BUG-150: a merge that completed remotely is not reported as a failure
#     just because gh's LOCAL post-merge cleanup tripped.
# ===========================================================================
# Shim reproducing the observed failure exactly: `gh pr merge` writes the local
# git error and exits 1, while `gh pr view` reports the PR as MERGED.
WSHIM="$SBX/wbin"; mkdir -p "$WSHIM"
cat > "$WSHIM/gh" <<'WGHSHIM'
#!/bin/sh
case "$1 $2" in
  "pr merge")
    echo "failed to run git: fatal: 'main' is already used by worktree at '/x'" >&2
    exit 1 ;;
  "pr view") echo '{"state":"MERGED"}' ;;
esac
exit 0
WGHSHIM
chmod +x "$WSHIM/gh"
OLDPATH3=$PATH; PATH="$WSHIM:$PATH"; export PATH
export ADLC_FORGE_PROVIDER_OVERRIDE=github
wout=$(adlc_forge_pr_merge 9 --squash --delete-branch 2>&1); wrc=$?
check "merge rc 0 when the PR is actually merged" "0" "$wrc"
contains "merge reports MERGED" "state=MERGED" "$wout"
contains "merge warns cleanup failed" "warn=" "$wout"
contains "merge warns the branch survives" "NOT deleted" "$wout"
case "$wout" in
  *"error_class="*) fail "merge must not claim failure (got: $wout)" ;;
  *) pass "merge emits no error_class when the PR merged" ;;
esac
# The diagnostics survive, demoted to a warning rather than dropped.
contains "merge keeps the raw diagnostic" "already used by worktree" "$wout"

# BUG-195: `--delete-branch` must be COMPLETED, not downgraded to advice.
# The same shim, plus `pr view --json headRefName,isCrossRepository` and a
# recording `git` so we can assert the remote delete actually fired.
DSHIM="$SBX/dbin"; mkdir -p "$DSHIM"
GITREC="$SBX/git-delete-rec"; export GITREC
cat > "$DSHIM/gh" <<'DGHSHIM'
#!/bin/sh
case "$1 $2" in
  "pr merge")
    echo "failed to run git: fatal: 'main' is already used by worktree at '/x'" >&2
    exit 1 ;;
  "pr view")
    case "$*" in
      *headRefName*) echo '{"headRefName":"fix/bug-195-slug","isCrossRepository":false}' ;;
      *) echo '{"state":"MERGED"}' ;;
    esac ;;
esac
exit 0
DGHSHIM
chmod +x "$DSHIM/gh"
cat > "$DSHIM/git" <<'DGITSHIM'
#!/bin/sh
echo "$*" >> "$GITREC"
exit 0
DGITSHIM
chmod +x "$DSHIM/git"
: > "$GITREC"
OLDPATH4=$PATH; PATH="$DSHIM:$PATH"; export PATH
export ADLC_FORGE_PROVIDER_OVERRIDE=github
dout=$(adlc_forge_pr_merge 9 --squash --delete-branch 2>&1); drc=$?
check "delete-branch: rc still 0" "0" "$drc"
contains "delete-branch: reports MERGED" "state=MERGED" "$dout"
contains "delete-branch: reports branch_deleted=1" "branch_deleted=1" "$dout"
contains "delete-branch: remote delete actually ran" "push origin --delete fix/bug-195-slug" "$(cat "$GITREC")"
case "$dout" in
  *"remove it with"*) fail "delete-branch: must not tell the caller to do it manually (got: $dout)" ;;
  *) pass "delete-branch: no manual-remediation instruction when the adapter handled it" ;;
esac
# The underlying diagnostic still survives, demoted.
contains "delete-branch: keeps the raw diagnostic" "already used by worktree" "$dout"

# Idempotence: a remote ref that is already gone is the desired state, not an error.
cat > "$DSHIM/git" <<'DGITSHIM2'
#!/bin/sh
echo "$*" >> "$GITREC"
echo "error: unable to delete 'x': remote ref does not exist" >&2
exit 1
DGITSHIM2
chmod +x "$DSHIM/git"
: > "$GITREC"
iout=$(adlc_forge_pr_merge 9 --squash --delete-branch 2>&1); irc=$?
check "delete-branch: already-gone ref rc 0" "0" "$irc"
contains "delete-branch: already-gone counts as deleted" "branch_deleted=1" "$iout"

# A genuine delete failure must report branch_deleted=0 AND name the exact command.
cat > "$DSHIM/git" <<'DGITSHIM3'
#!/bin/sh
echo "$*" >> "$GITREC"
echo "fatal: could not read from remote repository" >&2
exit 1
DGITSHIM3
chmod +x "$DSHIM/git"
: > "$GITREC"
fout=$(adlc_forge_pr_merge 9 --squash --delete-branch 2>&1); frc=$?
check "delete-branch: unrecoverable delete still rc 0 (merge landed)" "0" "$frc"
contains "delete-branch: reports branch_deleted=0" "branch_deleted=0" "$fout"
contains "delete-branch: names the concrete branch, not a placeholder" "git push origin --delete fix/bug-195-slug" "$fout"
contains "delete-branch: keeps the delete diagnostic" "delete_raw=" "$fout"
case "$fout" in
  *"<branch>"*) fail "delete-branch: must substitute the branch, not emit a placeholder (got: $fout)" ;;
  *) pass "delete-branch: no unsubstituted <branch> placeholder" ;;
esac

# A fork PR head is never auto-deleted.
cat > "$DSHIM/gh" <<'FGHSHIM'
#!/bin/sh
case "$1 $2" in
  "pr merge")
    echo "failed to run git: fatal: 'main' is already used by worktree at '/x'" >&2
    exit 1 ;;
  "pr view")
    case "$*" in
      *headRefName*) echo '{"headRefName":"contrib/patch","isCrossRepository":true}' ;;
      *) echo '{"state":"MERGED"}' ;;
    esac ;;
esac
exit 0
FGHSHIM
chmod +x "$DSHIM/gh"
cat > "$DSHIM/git" <<'FGITSHIM'
#!/bin/sh
echo "$*" >> "$GITREC"
exit 0
FGITSHIM
chmod +x "$DSHIM/git"
: > "$GITREC"
kout=$(adlc_forge_pr_merge 9 --squash --delete-branch 2>&1); krc=$?
check "delete-branch: fork PR rc 0" "0" "$krc"
contains "delete-branch: fork head reported as skipped" "branch_deleted=skipped-fork" "$kout"
case "$(cat "$GITREC")" in
  *"--delete"*) fail "delete-branch: must NEVER delete a fork's head branch (git ran: $(cat "$GITREC"))" ;;
  *) pass "delete-branch: no delete attempted against a fork head" ;;
esac

# No --delete-branch requested -> no deletion, and no branch_deleted field at all.
cat > "$DSHIM/gh" <<'NDGHSHIM'
#!/bin/sh
case "$1 $2" in
  "pr merge")
    echo "failed to run git: fatal: 'main' is already used by worktree at '/x'" >&2
    exit 1 ;;
  "pr view") echo '{"state":"MERGED"}' ;;
esac
exit 0
NDGHSHIM
chmod +x "$DSHIM/gh"
: > "$GITREC"
uout=$(adlc_forge_pr_merge 9 --squash 2>&1); urc=$?
check "no delete-branch: rc 0" "0" "$urc"
case "$uout" in
  *"branch_deleted="*) fail "no delete-branch: must not emit branch_deleted (got: $uout)" ;;
  *) pass "no delete-branch: emits no branch_deleted field" ;;
esac
case "$(cat "$GITREC")" in
  *"--delete"*) fail "no delete-branch: must not delete anything (git ran: $(cat "$GITREC"))" ;;
  *) pass "no delete-branch: no deletion attempted" ;;
esac
PATH=$OLDPATH4; export PATH
unset ADLC_FORGE_PROVIDER_OVERRIDE
export ADLC_FORGE_PROVIDER_OVERRIDE=github
PATH="$WSHIM:$PATH"; export PATH

# A merge that genuinely did NOT land still fails, with the error block intact.
NSHIM="$SBX/nbin"; mkdir -p "$NSHIM"
cat > "$NSHIM/gh" <<'NGHSHIM'
#!/bin/sh
case "$1 $2" in
  "pr merge")
    echo "Pull request is not mergeable: blocked by branch protection" >&2
    exit 1 ;;
  "pr view") echo '{"state":"OPEN"}' ;;
esac
exit 0
NGHSHIM
chmod +x "$NSHIM/gh"
PATH="$NSHIM:$SBX/wbin:$PATH"; export PATH
nout=$(adlc_forge_pr_merge 9 --squash 2>&1); nrc=$?
check "unmerged PR still returns non-zero" "1" "$nrc"
contains "unmerged PR keeps its error class" "error_class=merge-blocked-by-policy" "$nout"
case "$nout" in
  *"state=MERGED"*) fail "unmerged PR must not report MERGED (got: $nout)" ;;
  *) pass "unmerged PR does not report MERGED" ;;
esac
PATH=$OLDPATH3; export PATH
unset ADLC_FORGE_PROVIDER_OVERRIDE

# A local git failure is classified as local-git, not network (BUG-150).
check "classify local worktree collision" "local-git" \
  "$(_adlc_forge_classify "failed to run git: fatal: 'main' is already used by worktree at '/x'")"
check "classify still defaults to network" "network" \
  "$(_adlc_forge_classify 'some transient socket hangup')"

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
