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

# REQ-654: forge.sh loads partials/adlc-home.sh beside itself under bash and zsh,
# but dash cannot name the file being sourced and falls to ToolkitRoot. A fence's
# root line would have set it; this harness sets it for the load only, to the
# checkout under test, and unsets it again so every case below runs as before.
ADLC_TOOLKIT_ROOT=$(CDPATH= cd -- "$PARTIALS/.." && pwd); export ADLC_TOOLKIT_ROOT
. "$PARTIALS/forge.sh"
unset ADLC_TOOLKIT_ROOT

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
# REQ-609 BR-8: forge_config.py reads the machine config through the shared loader,
# resolved relative to its own file (../delegate); vendor it beside the copy.
mkdir -p "$ado_repo/tools/delegate"; cp "$ROOT/tools/delegate/_machine_config.py" "$ado_repo/tools/delegate/" 2>/dev/null
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
mkdir -p "$cfg_repo/tools/delegate"; cp "$ROOT/tools/delegate/_machine_config.py" "$cfg_repo/tools/delegate/"   # REQ-609 BR-8 (see above)
printf 'forge:\n  provider: azure-devops\n  auth: ADO_PAT\n' > "$cfg_repo/.adlc/config.yml"
check "project config overrides remote" "azure-devops" \
  "$(ADLC_FORGE_REPO="$cfg_repo" adlc_forge_provider "$cfg_repo" 2>/dev/null)"

# --- REQ-654 BR-1: machine_config_under_adlc_home ---------------------------
# The machine config is <ADLC_HOME>/adlc/config.yml: its forge.provider overrides
# a github remote when ADLC_HOME names it, and a config under $HOME/.claude is not
# read then. An unusable ADLC_HOME fails loud, naming it (BR-2).
mc_repo=$(mk_repo "https://github.com/o/r.git")
mkdir -p "$mc_repo/tools/adlc" "$mc_repo/tools/delegate"
cp "$ROOT/tools/adlc/forge_config.py" "$mc_repo/tools/adlc/"
cp "$ROOT/tools/delegate/_machine_config.py" "$mc_repo/tools/delegate/"
MC_HOME="$SBX/mc home"
mkdir -p "$MC_HOME/adlc"
printf 'forge:\n  provider: azure-devops\n  auth: ADO_PAT\n' > "$MC_HOME/adlc/config.yml"
check "machine_config_under_adlc_home: ADLC_HOME's config is read" "azure-devops" \
  "$(ADLC_HOME=$MC_HOME; export ADLC_HOME; unset ADLC_CONFIG; adlc_forge_provider "$mc_repo" 2>/dev/null)"
check "machine_config_under_adlc_home: benign — ADLC_HOME unset ignores it" "github" \
  "$(unset ADLC_HOME ADLC_CONFIG; HOME="$SBX/no-config-home"; export HOME; adlc_forge_provider "$mc_repo" 2>/dev/null)"
err=$(ADLC_HOME=relative; export ADLC_HOME; unset ADLC_CONFIG; adlc_forge_provider "$mc_repo" 2>&1 >/dev/null)
contains "machine_config_under_adlc_home: a relative ADLC_HOME fails loud" "ADLC_HOME" "$err"
check "machine_config_under_adlc_home: ADLC_CONFIG still outranks an invalid home" "azure-devops" \
  "$(ADLC_HOME=relative; ADLC_CONFIG="$MC_HOME/adlc/config.yml"; export ADLC_HOME ADLC_CONFIG; adlc_forge_provider "$mc_repo" 2>/dev/null)"

# ===========================================================================
# 6b. THE ONE INTERPRETER RULE (REQ-609 BR-8, ADR-2)
# ===========================================================================
# This partial is the path /proceed actually takes for every PR operation, and
# it used to run a bare `python3` while the `adlc` shim preferred the delegate
# venv — two interpreters answering one question. The rule has two halves and
# both are asserted here: a regular EXECUTABLE bin/python3, and a `yaml`
# package directory in that venv. A venv created before REQ-609 satisfies the
# first and not the second, and preferring it points every config read at the
# one interpreter on the machine that cannot parse the file.
FAKEHOME="$SBX/fakehome"
FAKEVENV="$FAKEHOME/.claude/delegate-venv"
mkdir -p "$FAKEVENV/bin" "$FAKEVENV/lib/python3.9/site-packages/yaml"
printf '#!/bin/sh\nexit 0\n' > "$FAKEVENV/bin/python3"
chmod +x "$FAKEVENV/bin/python3"
REALHOME=$HOME
HOME=$FAKEHOME; export HOME
check "interpreter rule: venv WITH PyYAML is preferred" \
  "$FAKEVENV/bin/python3" "$(_adlc_forge_python)"
rm -rf "$FAKEVENV/lib/python3.9/site-packages/yaml"
check "interpreter rule: venv WITHOUT PyYAML falls back to PATH python3" \
  "python3" "$(_adlc_forge_python)"
mkdir -p "$FAKEVENV/lib/python3.9/site-packages/yaml"
chmod -x "$FAKEVENV/bin/python3"
check "interpreter rule: non-executable venv python3 falls back" \
  "python3" "$(_adlc_forge_python)"

# --- REQ-609 verify D1: three sites, ONE answer ----------------------------
# The other two sites answer this question with a shell glob + `[ -d ]` (the
# shim) and `os.path.isdir` (checks.py). BOTH follow symlinks, and BOTH anchor
# the pattern at `lib/python*/`. `find … -type d` without `-L` does not follow,
# and `-path '*/site-packages/yaml'` is not anchored — so this site disagreed
# with the other two in both directions, which is exactly what BR-8 forbids.
chmod +x "$FAKEVENV/bin/python3"
rm -rf "$FAKEVENV/lib"
mkdir -p "$FAKEVENV/lib/python3.9/site-packages" "$SBX/realyaml"
ln -s "$SBX/realyaml" "$FAKEVENV/lib/python3.9/site-packages/yaml"
check "interpreter rule: a SYMLINKED yaml dir counts, as it does at the shim" \
  "$FAKEVENV/bin/python3" "$(_adlc_forge_python)"

# A pypy venv is not a `lib/python*/site-packages` layout: the shim's glob and
# checks.py's both skip it, so this site must too — whatever one thinks of the
# rule, the three sites may not answer differently.
rm -rf "$FAKEVENV/lib"
mkdir -p "$FAKEVENV/lib/pypy3.10/site-packages/yaml"
check "interpreter rule: a pypy site-packages is not a python* one" \
  "python3" "$(_adlc_forge_python)"

# $HOME is DATA, not a pattern. A home directory named `h[1] x` carries a space
# and glob metacharacters; the venv path may therefore never be interpolated
# INTO the `-path` pattern (the same class as `glob.escape` in checks.py), and
# the quoting must survive zsh, where an unmatched glob aborts the command
# (LESSON-335). Both halves of the rule are asserted under that home so neither
# a false yes nor a false no hides there.
GLOBHOME="$SBX/h[1] x"
GLOBVENV="$GLOBHOME/.claude/delegate-venv"
mkdir -p "$GLOBVENV/bin" "$GLOBVENV/lib/python3.9/site-packages" "$SBX/realyaml2"
printf '#!/bin/sh\nexit 0\n' > "$GLOBVENV/bin/python3"
chmod +x "$GLOBVENV/bin/python3"
ln -s "$SBX/realyaml2" "$GLOBVENV/lib/python3.9/site-packages/yaml"
HOME=$GLOBHOME; export HOME
check "interpreter rule: HOME with a space and glob chars is matched literally" \
  "$GLOBVENV/bin/python3" "$(_adlc_forge_python)"
rm -rf "$GLOBVENV/lib"
mkdir -p "$GLOBVENV/lib/pypy3.10/site-packages/yaml"
check "interpreter rule: glob-char HOME does not turn pypy into a match" \
  "python3" "$(_adlc_forge_python)"
HOME=$FAKEHOME; export HOME

rm -rf "$FAKEVENV"
check "interpreter rule: no venv at all falls back" "python3" "$(_adlc_forge_python)"

# --- REQ-654 ADR-3: the venv lives under ADLC_HOME --------------------------
# The rule's directory is <ADLC_HOME>/delegate-venv. With ADLC_HOME set, a venv
# under $HOME/.claude is NOT the one (benign half: unset, it still is), and an
# unusable ADLC_HOME means no venv: python3 from $PATH, as at the other two sites.
AHOME="$SBX/adlc home"
mkdir -p "$AHOME/delegate-venv/bin" "$AHOME/delegate-venv/lib/python3.9/site-packages/yaml" \
         "$FAKEVENV/bin" "$FAKEVENV/lib/python3.9/site-packages/yaml"
printf '#!/bin/sh\nexit 0\n' > "$AHOME/delegate-venv/bin/python3"
printf '#!/bin/sh\nexit 0\n' > "$FAKEVENV/bin/python3"
chmod +x "$AHOME/delegate-venv/bin/python3" "$FAKEVENV/bin/python3"
check "interpreter rule (REQ-654): ADLC_HOME's venv is the one" \
  "$AHOME/delegate-venv/bin/python3" "$(ADLC_HOME=$AHOME; export ADLC_HOME; _adlc_forge_python)"
check "interpreter rule (REQ-654): benign — ADLC_HOME unset is \$HOME/.claude's venv" \
  "$FAKEVENV/bin/python3" "$(unset ADLC_HOME; _adlc_forge_python)"
check "interpreter rule (REQ-654): a relative ADLC_HOME means python3" \
  "python3" "$(ADLC_HOME=rel; export ADLC_HOME; _adlc_forge_python)"
rm -rf "$FAKEVENV" "$AHOME"
HOME=$REALHOME; export HOME

# ===========================================================================
# 6b2. The interpreter is INVOKED through `command` (REQ-609 verify D5)
# ===========================================================================
# `_adlc_forge_py` runs `$adlc_fp_py`, which on the fallback arm is the bare
# word `python3`. This partial is SOURCED, so a shell function named `python3`
# in the sourcing shell — a debug wrapper, a version shim, a planted one — takes
# precedence over the $PATH lookup, and it, not the interpreter, receives the
# forge_config path and produces the "provider". `command` bypasses function
# lookup; the delegate gate's own probe already used it (REQ-609 ADR-3), and
# this site is the one /proceed actually takes for every PR operation.
#
# Run with a $HOME carrying no venv, so the rule really is on its bare-word
# fallback arm — against a real venv path there would be no bare name to hijack
# and the case would prove nothing.
NOVENV="$SBX/novenv"; mkdir -p "$NOVENV"
REALHOME2=$HOME; HOME=$NOVENV; export HOME
check "hijack case runs on the bare-name arm (non-vacuity)" \
  "python3" "$(_adlc_forge_python)"
HIJACK_REPO=$(mktemp -d "$SBX/hijack.XXXXXX")
mkdir -p "$HIJACK_REPO/tools/adlc"
printf 'print("REAL-PYTHON")\n' > "$HIJACK_REPO/tools/adlc/forge_config.py"
python3() { echo HIJACKED; }
# Positive control (LESSON-602): the SAME function, invoked the way this partial
# used to invoke it, really does intercept. Without this, "the answer was not
# HIJACKED" would also be produced by a function that was never installed.
hj_control=$("$(_adlc_forge_python)" "$HIJACK_REPO/tools/adlc/forge_config.py" 2>/dev/null)
hj=$(_adlc_forge_py "$HIJACK_REPO" resolve-provider "$HIJACK_REPO" 2>/dev/null)
unset -f python3
check "a python3 function DOES intercept a bare invocation (control)" \
  "HIJACKED" "$hj_control"
check "_adlc_forge_py invokes through command, not the python3 function" \
  "REAL-PYTHON" "$hj"
HOME=$REALHOME2; export HOME

# ===========================================================================
# 6c. The resolver's stderr is never swallowed (REQ-609 BR-4/BR-9, verify B2)
# ===========================================================================
# With no PyYAML reachable, forge_config takes the ADR-2 `dependency-missing`
# carve-out: it proceeds UNCONFIGURED, so the `forge.provider: azure-devops`
# written below is NOT honoured and the provider is auto-detected from the
# github origin instead. That override is only tolerable if the operator is
# told, and the one line that tells them was going to /dev/null.
poison_repo=$(mk_repo "https://github.com/o/r.git")
mkdir -p "$poison_repo/.adlc" "$poison_repo/tools/adlc" "$poison_repo/tools/delegate"
cp "$ROOT/tools/adlc/forge_config.py" "$poison_repo/tools/adlc/"
cp "$ROOT/tools/delegate/_machine_config.py" "$poison_repo/tools/delegate/"
printf 'forge:\n  provider: azure-devops\n' > "$poison_repo/.adlc/config.yml"
POISON="$SBX/poison"; mkdir -p "$POISON/yaml"
printf "raise ImportError('no module named yaml (test poison)')\n" \
  > "$POISON/yaml/__init__.py"
OLDPP=${PYTHONPATH:-}
PYTHONPATH="$POISON"; export PYTHONPATH
pout=$(adlc_forge_provider "$poison_repo" 2>"$SBX/poison.err"); prc=$?
perr=$(cat "$SBX/poison.err")
if [ -n "$OLDPP" ]; then PYTHONPATH=$OLDPP; export PYTHONPATH; else unset PYTHONPATH; fi
check "no-PyYAML: the resolver still answers" "0" "$prc"
check "no-PyYAML: falls back to origin auto-detect" "github" "$pout"
contains "no-PyYAML: the dependency line reaches stderr" "PyYAML" "$perr"
# Benign twin: the same repo with PyYAML reachable honours the written provider,
# and says nothing on stderr.
cout=$(adlc_forge_provider "$poison_repo" 2>"$SBX/clean.err"); crc=$?
cerr=$(cat "$SBX/clean.err")
check "with PyYAML: the written provider wins" "azure-devops" "$cout"
check "with PyYAML: rc 0" "0" "$crc"
check "with PyYAML: stderr is empty" "" "$cerr"
unset ADLC_FORGE_PROVIDER

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
contains "gh merge byte-compat"  "pr merge 9 --squash" "$REC"
# BUG-252: the adapter keeps --delete-branch for itself; gh never sees it.
case "$REC" in
  *"--delete-branch"*) fail "gh merge must not receive --delete-branch (got: $REC)" ;;
  *) pass "gh merge argv carries no --delete-branch" ;;
esac
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
# 7c. BUG-252: the merge must not remove the worktree that holds the PR branch.
# ===========================================================================
# Real git, so the outcome is observed, not inferred: a bare origin, a primary
# checkout on main, and a linked REQ worktree on the feature branch carrying an
# untracked pipeline-state.json — the /sprint layout. The gh shim does what gh
# 2.103.3's `-d` does: remove the worktree holding the branch, delete the local
# branch, delete the remote one. Without `-d` it only merges.
B252="$SBX/b252"; mkdir -p "$B252/bin"
B252BR="feat/REQ-252-x"; B252REC="$B252/gh-rec"; B252STATE=MERGED
export B252BR B252REC B252STATE
b252git() { git -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@"; }
git init -q --bare "$B252/origin.git"
git init -q "$B252/primary"
b252git -C "$B252/primary" checkout -q -b main
b252git -C "$B252/primary" commit -q --allow-empty -m init
git -C "$B252/primary" remote add origin "$B252/origin.git"
git -C "$B252/primary" push -q origin main 2>/dev/null
B252WT="$B252/primary/.worktrees/REQ-252"
git -C "$B252/primary" worktree add -q -b "$B252BR" "$B252WT" 2>/dev/null
b252git -C "$B252WT" commit -q --allow-empty -m feat
git -C "$B252WT" push -q origin "$B252BR" 2>/dev/null
mkdir -p "$B252WT/.adlc/specs/REQ-252-x"
echo '{"currentPhase":8,"completed":false}' > "$B252WT/.adlc/specs/REQ-252-x/pipeline-state.json"
cat > "$B252/bin/gh" <<'B252GH'
#!/bin/sh
case "$1 $2" in
  "pr merge")
    echo "$*" >> "$B252REC"
    for a in "$@"; do
      case "$a" in
        --delete-branch|-d)
          wt=$(git worktree list --porcelain | awk -v b="branch refs/heads/$B252BR" \
            '/^worktree /{w=substr($0,10)} $0==b{print w}')
          [ -n "$wt" ] && git worktree remove --force "$wt" && echo "Removed worktree $wt" >&2
          git branch -D "$B252BR" >/dev/null 2>&1
          git push -q origin --delete "$B252BR" 2>/dev/null ;;
      esac
    done
    exit 0 ;;
  "pr view")
    echo "{\"state\":\"$B252STATE\",\"headRefName\":\"$B252BR\",\"isCrossRepository\":false}" ;;
esac
exit 0
B252GH
chmod +x "$B252/bin/gh"
OLDPATH5=$PATH; PATH="$B252/bin:$PATH"; export PATH
export ADLC_FORGE_PROVIDER_OVERRIDE=github
: > "$B252REC"
# From the parent repo path, exactly as /proceed Phase 8 runs it.
mout=$(cd "$B252/primary" && adlc_forge_pr_merge 9 --squash --delete-branch 2>&1); mrc=$?
check "BUG-252: merge rc 0" "0" "$mrc"
contains "BUG-252: reports MERGED" "state=MERGED" "$mout"
contains "BUG-252: reports branch_deleted=1" "branch_deleted=1" "$mout"
if [ -d "$B252WT" ]; then pass "BUG-252: the REQ worktree survives the merge"
else fail "BUG-252: the merge removed the REQ worktree (out: $mout)"; fi
contains "BUG-252: its untracked pipeline-state.json survives" '"currentPhase":8' \
  "$(cat "$B252WT/.adlc/specs/REQ-252-x/pipeline-state.json" 2>/dev/null)"
case "$(cat "$B252REC")" in
  *"--delete-branch"*|*" -d"*) fail "BUG-252: gh received a delete flag (argv: $(cat "$B252REC"))" ;;
  *) pass "BUG-252: gh received no delete flag" ;;
esac
if git -C "$B252/origin.git" show-ref -q --verify "refs/heads/$B252BR"; then
  fail "BUG-252: the remote branch survived the merge"
else pass "BUG-252: the remote branch is deleted"; fi
if git -C "$B252/primary" show-ref -q --verify "refs/heads/$B252BR"; then
  pass "BUG-252: the local branch is left for the caller's ordered teardown"
else fail "BUG-252: the merge deleted the local branch"; fi

# gh's short spelling `-d` is stripped the same way.
git -C "$B252WT" push -q origin "$B252BR" 2>/dev/null
: > "$B252REC"
sout=$(cd "$B252/primary" && adlc_forge_pr_merge 9 --squash -d 2>&1); src=$?
check "BUG-252: -d merge rc 0" "0" "$src"
if [ -d "$B252WT" ]; then pass "BUG-252: -d leaves the REQ worktree in place"
else fail "BUG-252: -d removed the REQ worktree (out: $sout)"; fi
contains "BUG-252: -d still deletes the remote branch" "branch_deleted=1" "$sout"

# A zero exit that did not merge (auto-merge, a merge queue) must keep the head:
# deleting an open PR's branch closes the PR.
git -C "$B252WT" push -q origin "$B252BR" 2>/dev/null
B252STATE=OPEN; export B252STATE
oout=$(cd "$B252/primary" && adlc_forge_pr_merge 9 --squash --delete-branch 2>&1); orc=$?
check "BUG-252: unmerged-after-exit-0 rc 0" "0" "$orc"
contains "BUG-252: reports the real state" "state=OPEN" "$oout"
contains "BUG-252: reports branch_deleted=0" "branch_deleted=0" "$oout"
if git -C "$B252/origin.git" show-ref -q --verify "refs/heads/$B252BR"; then
  pass "BUG-252: an open PR's head branch is kept"
else fail "BUG-252: deleted the head branch of a PR that is still open"; fi
PATH=$OLDPATH5; export PATH
unset ADLC_FORGE_PROVIDER_OVERRIDE B252BR B252REC B252STATE

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

# ===========================================================================
# REQ-659 BR-26: pinned merge, protection, commit PRs, ADO allowlist, new fields
# ===========================================================================
ADLC_TOOLKIT_ROOT=$ROOT; export ADLC_TOOLKIT_ROOT
ADLC_FORGE_MOCK=1; export ADLC_FORGE_MOCK
unset ADLC_FORGE_PROVIDER_OVERRIDE ADLC_FORGE_MOCK_STORE
for prov in github azure-devops; do
  ADLC_FORGE_MOCK_PROVIDER=$prov; ADLC_FORGE_MOCK_SCENARIO=ok; export ADLC_FORGE_MOCK_PROVIDER ADLC_FORGE_MOCK_SCENARIO
  out=$(adlc_forge_pr_view 101 --fields number,url,headRefOid,isCrossRepository,files,mergeCommit 2>&1)
  contains "$prov view number" "number=101" "$out"
  contains "$prov view oid" "headRefOid=0000000000" "$out"
  contains "$prov view cross" "isCrossRepository=false" "$out"
  contains "$prov view files" 'files=["README.md"]' "$out"
  contains "$prov view mergeCommit" "mergeCommit=1111111111" "$out"
  out=$(adlc_forge_pr_list --head feat/REQ-520-forge-adapter --state all --json number,url,headRefOid,baseRefName,isCrossRepository 2>&1)
  contains "$prov list by head" '"number": 101' "$out"
  check "$prov protection default" "protected" "$(adlc_forge_branch_protection main)"
  check "$prov commit_prs empty" "" "$(adlc_forge_commit_prs abc123)"
done
ADLC_FORGE_MOCK_PROVIDER=github; export ADLC_FORGE_MOCK_PROVIDER
for v in no-pr bypass force-push deletion; do
  ADLC_FORGE_MOCK_SCENARIO=protection-$v; export ADLC_FORGE_MOCK_SCENARIO
  check "protection without $v" "unprotected" "$(adlc_forge_branch_protection main)"
done
ADLC_FORGE_MOCK_SCENARIO=protection-lookup-fail; export ADLC_FORGE_MOCK_SCENARIO
check "protection lookup failure" "unknown" "$(adlc_forge_branch_protection main)"
ADLC_FORGE_MOCK_SCENARIO=ok; export ADLC_FORGE_MOCK_SCENARIO
out=$(adlc_forge_pr_merge 101 --squash --match-head-commit abc 2>&1); rc=$?
check "github pinned merge rc" "0" "$rc"
contains "github pinned merge" "state=MERGED" "$out"
ADLC_FORGE_MOCK_PROVIDER=azure-devops; export ADLC_FORGE_MOCK_PROVIDER
out=$(adlc_forge_pr_merge 101 --squash --match-head-commit abc 2>&1); rc=$?
contains "ado pinned merge is refused" "error_class=feature-unsupported" "$out"
check "ado pinned merge rc" "1" "$rc"
for op in pr_edit pr_ready pr_create; do
  for f in --status --auto-complete --squash --delete-source-branch --bypass-policy; do
    out=$(adlc_forge_"$op" 101 "$f" true 2>&1); rc=$?
    contains "ado $op refuses $f" "error_class=feature-unsupported" "$out"
    check "ado $op $f rc" "1" "$rc"
  done
  out=$(adlc_forge_"$op" 101 --title T --description D --draft --source-branch a --target-branch b 2>&1); rc=$?
  check "ado $op passes the five flags" "0" "$rc"
done
unset ADLC_FORGE_MOCK ADLC_FORGE_MOCK_PROVIDER ADLC_FORGE_MOCK_SCENARIO

# The real ADO merge arm refuses the pin before az runs; the real edit arm strips
# nothing silently and translates the gh-shaped flags.
AZDIR="$SBX/azpin"; mkdir -p "$AZDIR"; AZREC2="$SBX/azpin.rec"
cat > "$AZDIR/az" <<AZSH
#!/bin/sh
printf '%s\n' "\$*" >> "$AZREC2"
echo '{}'
AZSH
chmod +x "$AZDIR/az"
OLDPATH3=$PATH; PATH="$AZDIR:$PATH"; export PATH
ADLC_FORGE_PROVIDER_OVERRIDE=azure-devops; export ADLC_FORGE_PROVIDER_OVERRIDE
out=$(adlc_forge_pr_merge 101 --squash --match-head-commit abc 2>&1); rc=$?
contains "real ado pinned merge refused" "error_class=feature-unsupported" "$out"
check "real ado pin never reached az" "no" "$( [ -f "$AZREC2" ] && echo yes || echo no )"
out=$(adlc_forge_pr_edit 101 --status completed 2>&1); rc=$?
contains "real ado edit refuses --status" "error_class=feature-unsupported" "$out"
check "real ado --status never reached az" "no" "$( [ -f "$AZREC2" ] && echo yes || echo no )"
adlc_forge_pr_edit 101 --title 'T x' --body 'B y' >/dev/null 2>&1
contains "real ado edit translates --body" "repos pr update --id 101 --title T x --description B y" "$(cat "$AZREC2")"
adlc_forge_pr_ready 101 >/dev/null 2>&1
contains "real ado ready" "repos pr update --id 101 --draft false" "$(cat "$AZREC2")"
adlc_forge_pr_create -R o/r --draft --base main --head feat/x --title T --body B >/dev/null 2>&1
contains "real ado create translates" "repos pr create --draft --target-branch main --source-branch feat/x --title T --description B" "$(cat "$AZREC2")"
PATH=$OLDPATH3; export PATH
unset ADLC_FORGE_PROVIDER_OVERRIDE

# Real-backend protection: a recording gh on PATH, the merge pin forwarded verbatim.
GHDIR="$SBX/ghprot"; mkdir -p "$GHDIR"; GHREC="$SBX/ghprot.rec"
cat > "$GHDIR/gh" <<GHSH
#!/bin/sh
printf '%s\n' "\$*" >> "$GHREC"
case "\$*" in
  *rules/branches/*) echo '[{"type":"pull_request","ruleset_id":7},{"type":"non_fast_forward","ruleset_id":7},{"type":"deletion","ruleset_id":7}]' ;;
  *rulesets/7*) echo '{"current_user_can_bypass":"never"}' ;;
  *branches/*/protection*) echo 'Branch not protected (HTTP 404)' >&2; exit 1 ;;
  "api user"*) echo operator ;;
  "api repos/{owner}/{repo}"*) echo '{"permissions":{"admin":false}}' ;;
  *) echo ok ;;
esac
GHSH
chmod +x "$GHDIR/gh"
OLDPATH4=$PATH; PATH="$GHDIR:$PATH"; export PATH
ADLC_FORGE_PROVIDER_OVERRIDE=github; export ADLC_FORGE_PROVIDER_OVERRIDE
check "real github protection" "protected" "$(adlc_forge_branch_protection main)"
adlc_forge_pr_merge 7 --squash --match-head-commit abc >/dev/null 2>&1
contains "real github pin is forwarded" "pr merge 7 --squash --match-head-commit abc" "$(cat "$GHREC")"
PATH=$OLDPATH4; export PATH
unset ADLC_FORGE_PROVIDER_OVERRIDE ADLC_TOOLKIT_ROOT

rm -rf "$SBX"

echo ""
if [ "$FAILS" -eq 0 ]; then
  echo "forge.test.sh: ALL CASES PASS"
  exit 0
fi
echo "forge.test.sh: $FAILS FAILURE(S)"
exit 1
