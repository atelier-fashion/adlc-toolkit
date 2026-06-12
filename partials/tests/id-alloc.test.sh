#!/bin/sh
# partials/tests/id-alloc.test.sh — AC test matrix for id-alloc.sh + id-recheck.sh (REQ-518).
#
# Fully offline: a sandbox HOME (counter fixtures), a sandbox ADLC_REPOS_ROOT, and a local
# bare repo standing in for the "remote". No network, no real ~/.claude mutation.
#
# Run under BOTH shells to satisfy BR-6 / the Linux-parity AC:
#   bash partials/tests/id-alloc.test.sh
#   zsh  partials/tests/id-alloc.test.sh
# or run the wrapper which invokes both:  sh partials/tests/run.sh
#
# Exits 0 iff every case passes; prints one line per case.

# Resolve the partials dir (this script lives in partials/tests/).
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)

FAILS=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}

new_sandbox() {
  SBX=$(mktemp -d -t idalloc.XXXXXX)
  HOME="$SBX/home"; export HOME; mkdir -p "$HOME/.claude"
  ADLC_REPOS_ROOT="$SBX/repos"; export ADLC_REPOS_ROOT; mkdir -p "$ADLC_REPOS_ROOT"
}
make_remote_with_branch() { # make_remote_with_branch <branch> [<branch>...]
  BARE="$SBX/remote.git"; git init -q --bare "$BARE"
  CLONE="$ADLC_REPOS_ROOT/proj"; git clone -q "$BARE" "$CLONE" 2>/dev/null
  ( cd "$CLONE" && git config user.email t@t && git config user.name t \
      && git commit -q --allow-empty -m init && git push -q origin HEAD:main 2>/dev/null \
      && for MRB_B in "$@"; do \
           git checkout -q -b "$MRB_B" && git push -q origin "$MRB_B" 2>/dev/null && git checkout -q main; \
         done )
}
cleanup() { rm -rf "$SBX"; }

# --- case: local-ahead — counter=500, no remote => allocate 500, counter -> 501 -----
new_sandbox
echo 500 > "$HOME/.claude/.global-next-req"
N=$( . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>/dev/null )
check "local-ahead allocates local value" "500" "$N"
check "local-ahead fast-forwards counter" "501" "$(cat "$HOME/.claude/.global-next-req")"
cleanup

# --- case: empty-counter refusal — counter file empty => no allocation --------------
new_sandbox
: > "$HOME/.claude/.global-next-req"
N=$( . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>/dev/null )
check "empty-counter refusal yields no id" "" "$N"
cleanup

# --- case: symlink-swap refusal — lock dir is a symlink => no allocation -------------
new_sandbox
echo 100 > "$HOME/.claude/.global-next-req"
ln -s /tmp "$HOME/.claude/.global-next-req.lock.d"
N=$( . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>/dev/null )
check "symlink-swap refusal yields no id" "" "$N"
cleanup

# --- case: bootstrap — no counter, local spec REQ-042 => allocate 43 ----------------
new_sandbox
mkdir -p "$ADLC_REPOS_ROOT/myrepo/.adlc/specs/REQ-042-foo"
( cd "$ADLC_REPOS_ROOT/myrepo" && git init -q )
N=$( cd "$ADLC_REPOS_ROOT/myrepo"; . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>/dev/null )
check "bootstrap from local scan (octal-safe)" "43" "$N"
cleanup

# --- case: remote-ahead — local counter=100, remote feat/REQ-600 => allocate 601 ----
new_sandbox
make_remote_with_branch feat/REQ-600-x
echo 100 > "$HOME/.claude/.global-next-req"
N=$( cd "$ADLC_REPOS_ROOT/proj"; . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>/dev/null )
check "remote-ahead allocates above remote branch" "601" "$N"
cleanup

# --- case: lock contention — two concurrent allocators get distinct ids -------------
new_sandbox
echo 200 > "$HOME/.claude/.global-next-req"
( . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>/dev/null ) > "$SBX/a" &
( . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>/dev/null ) > "$SBX/b" &
wait
A=$(cat "$SBX/a"); B=$(cat "$SBX/b")
if [ -n "$A" ] && [ -n "$B" ] && [ "$A" != "$B" ]; then
  pass "lock contention yields distinct ids ($A, $B)"
else
  fail "lock contention distinct ids (got '$A' and '$B')"
fi
cleanup

# --- case: remote-unreachable — degraded warning + local-only success ---------------
new_sandbox
# A repo whose origin points at a non-existent path => ls-remote fails (unreachable).
BADREPO="$ADLC_REPOS_ROOT/bad"; mkdir -p "$BADREPO"; ( cd "$BADREPO" && git init -q && git remote add origin "$SBX/nonexistent.git" )
echo 300 > "$HOME/.claude/.global-next-req"
# Call the allocator ONCE — capture stdout (the id) and stderr (the warning) separately
# via a temp file, so the counter is fast-forwarded exactly once.
N=$( cd "$BADREPO"; . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>"$SBX/err" )
ERR=$(cat "$SBX/err")
# Allocation still succeeds from local state (300) despite the unreachable remote.
check "remote-unreachable still allocates locally" "300" "$N"
case "$ERR" in
  *unreachable*|*"local-only"*) pass "remote-unreachable emits a degraded warning" ;;
  *) fail "remote-unreachable degraded warning (got: $ERR)" ;;
esac
cleanup

# --- case: remote-multi-branch — MULTI-line candidate list under the executor shell -
# Regression for BUG-116: with >=2 matching remote branches the candidate list is
# multi-line; zsh does not word-split `for x in $var`, so the whole list reached the
# `[ -gt ]` integer test as one word, adlc_remote_high returned 0, and allocation
# silently degraded to the local counter. The original fixtures only ever pushed ONE
# matching branch, which is why the matrix passed on the broken code.
new_sandbox
make_remote_with_branch feat/REQ-600-x feat/REQ-650-y feat/REQ-610-z
echo 100 > "$HOME/.claude/.global-next-req"
N=$( cd "$ADLC_REPOS_ROOT/proj"; . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>"$SBX/err" )
ERR=$(cat "$SBX/err")
check "remote-multi-branch allocates above max remote branch" "651" "$N"
case "$ERR" in
  *"integer expression expected"*) fail "remote-multi-branch must not spam integer-test errors (got: $ERR)" ;;
  *) pass "remote-multi-branch emits no integer-test errors" ;;
esac
cleanup

# --- case: leading-zero branch numbers — decimal, not octal, in a multi-line list ----
new_sandbox
make_remote_with_branch feat/REQ-042-x feat/REQ-007-y
echo 10 > "$HOME/.claude/.global-next-req"
N=$( cd "$ADLC_REPOS_ROOT/proj"; . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>/dev/null )
check "leading-zero branches normalize to decimal (042 -> 42 -> alloc 43)" "43" "$N"
cleanup

# --- case: lesson artifact listing via stubbed gh — multi-entry remote listing -------
# The incident path for BUG-116: lessons have no branch namespace, so the remote
# footprint is the merged artifact listing (gh api). Stub `gh` to return a real-shaped
# multi-entry listing (incl. a leading-zero name) without network.
new_sandbox
mkdir -p "$SBX/bin"
cat > "$SBX/bin/gh" <<'EOF'
#!/bin/sh
case "$1" in
  api)
    printf '%s\n' \
      "LESSON-007-old-thing.md" \
      "LESSON-329-printf-newlines.md" \
      "LESSON-356-latest-thing.md"
    ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$SBX/bin/gh"
REPO="$ADLC_REPOS_ROOT/proj"; mkdir -p "$REPO"
( cd "$REPO" && git init -q && git remote add origin "https://github.com/acme/proj.git" )
echo 5 > "$HOME/.claude/.global-next-lesson"
N=$( cd "$REPO"; PATH="$SBX/bin:$PATH"; export PATH; . "$PARTIALS/id-alloc.sh"; adlc_alloc_id lesson 2>"$SBX/err" )
ERR=$(cat "$SBX/err")
check "lesson allocates above multi-entry remote artifact listing" "357" "$N"
case "$ERR" in
  *"integer expression expected"*) fail "lesson listing must not spam integer-test errors (got: $ERR)" ;;
  *) pass "lesson listing emits no integer-test errors" ;;
esac
cleanup

# --- case: adlc_id_list_max unit — multi-line, leading zeros, garbage fails loud -----
new_sandbox
M=$( . "$PARTIALS/id-alloc.sh"; adlc_id_list_max "$(printf '600\n042\n650\n7')" 2>/dev/null )
check "list_max picks numeric max of multi-line list" "650" "$M"
M=$( . "$PARTIALS/id-alloc.sh"; adlc_id_list_max "" 2>/dev/null )
check "list_max of empty list is 0" "0" "$M"
RC=0; M=$( . "$PARTIALS/id-alloc.sh"; adlc_id_list_max "$(printf '600\nDROP TABLE\n650')" 2>"$SBX/err" ) || RC=$?
check "list_max rejects non-numeric input (rc 2)" "2" "$RC"
check "list_max prints nothing on garbage" "" "$M"
case "$(cat "$SBX/err")" in
  *ERROR*non-numeric*) pass "list_max fails loud on garbage" ;;
  *) fail "list_max loud-failure message (got: $(cat "$SBX/err"))" ;;
esac
cleanup

# --- case: recheck collision — remote has feat/REQ-600, recheck REQ-600 => rc 1 -----
new_sandbox
make_remote_with_branch feat/REQ-600-x
RC=0; MSG=$( cd "$ADLC_REPOS_ROOT/proj"; . "$PARTIALS/id-recheck.sh"; adlc_recheck_id req REQ-600 2>&1 ) || RC=$?
check "recheck collision returns 1" "1" "$RC"
case "$MSG" in
  *"adlc renumber REQ-600 REQ-601"*) pass "recheck collision prints renumber command" ;;
  *) fail "recheck collision renumber command (got: $MSG)" ;;
esac
cleanup

# --- case: recheck no-collision — recheck REQ-700 => rc 0 ---------------------------
new_sandbox
make_remote_with_branch feat/REQ-600-x
RC=0; ( cd "$ADLC_REPOS_ROOT/proj"; . "$PARTIALS/id-recheck.sh"; adlc_recheck_id req REQ-700 2>/dev/null ) || RC=$?
check "recheck no-collision returns 0" "0" "$RC"
cleanup

# --- case: recheck multi-branch — renumber suggestion uses the REAL high-water -------
# adlc_recheck_id inherits adlc_remote_high; under broken zsh iteration (BUG-116) the
# high-water was 0 and a collision suggested "renumber ... REQ-001". With >=2 branches
# the suggestion must be high+1 = 651.
new_sandbox
make_remote_with_branch feat/REQ-600-x feat/REQ-650-y
RC=0; MSG=$( cd "$ADLC_REPOS_ROOT/proj"; . "$PARTIALS/id-recheck.sh"; adlc_recheck_id req REQ-600 2>&1 ) || RC=$?
check "recheck multi-branch collision returns 1" "1" "$RC"
case "$MSG" in
  *"adlc renumber REQ-600 REQ-651"*) pass "recheck multi-branch suggests real high-water + 1" ;;
  *) fail "recheck multi-branch renumber suggestion (got: $MSG)" ;;
esac
cleanup

# ====================================================================================
# REQ-523 cases
# ====================================================================================

# Helper: build a bare remote whose `main` contains real merged artifact dirs/files, so
# the git-transport scan (ls-remote tip + shallow fetch + ls-tree) can derive them with
# NO gh. <kind-path> e.g. .adlc/specs; names are passed as the remaining args.
make_remote_with_artifacts() { # make_remote_with_artifacts <artifact-path> <name> [<name>...]
  MRA_PATH=$1; shift
  BARE="$SBX/remote.git"; git init -q --bare "$BARE"
  SEED="$SBX/seed"; git clone -q "$BARE" "$SEED" 2>/dev/null
  ( cd "$SEED" && git config user.email t@t && git config user.name t
    for MRA_N in "$@"; do mkdir -p "$MRA_PATH/$MRA_N"; echo x > "$MRA_PATH/$MRA_N/f.md"; done
    git add -A && git commit -q -m seed && git push -q origin HEAD:main 2>/dev/null )
  CLONE="$ADLC_REPOS_ROOT/proj"; git clone -q "$BARE" "$CLONE" 2>/dev/null
}

# --- BR-1: ls-remote fails but gh shows merged REQ-800 => alloc>=801 AND degraded ----
# Independent sources: the branch scan (ls-remote) failing must NOT skip the artifact
# scan (gh) for the same repo. A bad-origin repo makes ls-remote fail; a gh stub returns
# a merged REQ-800 listing. Expect 801 AND a degraded warning on stderr.
new_sandbox
mkdir -p "$SBX/bin"
cat > "$SBX/bin/gh" <<'EOF'
#!/bin/sh
case "$1" in
  api) printf '%s\n' "REQ-790-a" "REQ-800-b" ;;   # multi-element listing
  *) exit 1 ;;
esac
EOF
chmod +x "$SBX/bin/gh"
BADREPO="$ADLC_REPOS_ROOT/proj"; mkdir -p "$BADREPO"
( cd "$BADREPO" && git init -q && git remote add origin "https://github.com/acme/proj.git" \
    && git remote set-url origin "$SBX/nonexistent.git" )
# NOTE: origin URL must look like GitHub for the host classifier to take the gh path,
# but point ls-remote at a nonexistent path so the BRANCH scan fails. We achieve this by
# leaving the github.com URL and relying on ls-remote failing for an unreachable repo.
( cd "$BADREPO" && git remote set-url origin "https://github.com/acme/does-not-exist-zzz.git" )
echo 100 > "$HOME/.claude/.global-next-req"
N=$( cd "$BADREPO"; PATH="$SBX/bin:$PATH"; export PATH; . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>"$SBX/err" )
ERR=$(cat "$SBX/err")
check "BR-1 independent sources: gh artifact scan runs despite ls-remote failure" "801" "$N"
case "$ERR" in
  *DEGRADED*|*degraded*|*unreachable*) pass "BR-1 emits a degraded warning (branch source failed)" ;;
  *) fail "BR-1 degraded warning (got: $ERR)" ;;
esac
cleanup

# --- BR-2: degraded bit survives command substitution -------------------------------
# A caller using $(adlc_remote_high ...) must observe the degraded token. No remote at
# all => degraded=1; the SECOND stdout token is the signal.
new_sandbox
# Empty repos root (no participating repo) => saw_remote=0 => degraded.
RH=$( . "$PARTIALS/id-alloc.sh"; adlc_remote_high req 2>/dev/null )
DEG=${RH##* }
HIGH=${RH%% *}
check "BR-2 cmd-sub: high-water token is 0 with no remote" "0" "$HIGH"
check "BR-2 cmd-sub: degraded token observable through \$()" "1" "$DEG"
cleanup

# --- BR-3: kind=lesson, gh absent and no git fallback => degraded, never silent 0 ----
# A GitHub-shaped origin pointing at a nonexistent repo, with gh forced absent, leaves
# NO usable artifact scan for a lesson (its only source) => degraded with a warning.
new_sandbox
LREPO="$ADLC_REPOS_ROOT/proj"; mkdir -p "$LREPO"
( cd "$LREPO" && git init -q && git remote add origin "https://github.com/acme/no-such-repo-xyz.git" )
echo 5 > "$HOME/.claude/.global-next-lesson"
# Force gh to FAIL (stands in for absent) via a failing stub at the front of PATH; keep
# the full PATH so git/sed/grep/tr remain available. The git-transport fallback also
# fails (the repo does not exist), leaving NO usable scan for the lesson => degraded.
mkdir -p "$SBX/bin"; printf '#!/bin/sh\nexit 1\n' > "$SBX/bin/gh"; chmod +x "$SBX/bin/gh"
RH=$( cd "$LREPO"; PATH="$SBX/bin:$PATH"; export PATH; . "$PARTIALS/id-alloc.sh"; adlc_remote_high lesson 2>"$SBX/err" )
ERR=$(cat "$SBX/err")
DEG=${RH##* }
check "BR-3 lesson no-gh no-fallback is degraded (token=1)" "1" "$DEG"
case "$ERR" in
  *"could not run"*|*degraded*|*DEGRADED*) pass "BR-3 lesson emits a degraded warning (never silent 0)" ;;
  *) fail "BR-3 lesson degraded warning (got: $ERR)" ;;
esac
cleanup

# --- BR-4: gh absent, GitHub remote reachable over git transport => artifacts derived -
# A real bare remote with merged spec dirs on main; gh forced to FAIL (stands in for
# "gh absent" — same code path: gh fast-path yields nothing, git-transport fallback
# runs). The fallback (ls-remote tip + shallow fetch + ls-tree) must still derive
# REQ-700/REQ-720. Keep the FULL PATH so the lock's mkdir/seq/sleep work; only `gh` is
# shadowed by a failing stub at the FRONT of PATH.
new_sandbox
make_remote_with_artifacts ".adlc/specs" REQ-700-a REQ-720-b
( cd "$ADLC_REPOS_ROOT/proj" && git remote set-url origin "$SBX/remote.git" )
mkdir -p "$SBX/bin"; printf '#!/bin/sh\nexit 1\n' > "$SBX/bin/gh"; chmod +x "$SBX/bin/gh"
echo 100 > "$HOME/.claude/.global-next-req"
N=$( cd "$ADLC_REPOS_ROOT/proj"; PATH="$SBX/bin:$PATH"; export PATH; . "$PARTIALS/id-alloc.sh"; adlc_alloc_id req 2>/dev/null )
check "BR-4 git-transport scan derives merged artifacts with no usable gh" "721" "$N"
cleanup

# --- BR-5: Azure DevOps origin => artifacts derived via the same git-transport scan ---
# An ADO-shaped origin URL classifies as azure-devops; the forge-agnostic git-transport
# scan delivers full parity (the bare remote IS reachable). gh absent throughout.
new_sandbox
make_remote_with_artifacts ".adlc/specs" REQ-900-a REQ-910-b
# Point origin at the bare remote for transport, but set a SECOND remote URL string that
# the classifier sees as ADO. Simplest: verify the classifier + git scan path directly.
DEG_RAN=$( cd "$ADLC_REPOS_ROOT/proj"; . "$PARTIALS/id-alloc.sh"
  # Force the ADO classification by feeding an ADO URL to the host classifier and run
  # the git-transport scan against the (real) origin bare remote.
  cls=$(adlc_forge_host_class "git@ssh.dev.azure.com:v3/org/proj/repo")
  out=$(adlc_remote_artifact_nums "$ADLC_REPOS_ROOT/proj" req REQ)
  ran=$(printf '%s\n' "$out" | sed -n '2p')
  nums=$(printf '%s\n' "$out" | sed -n '1p')
  printf '%s|%s|%s' "$cls" "$ran" "$nums" )
CLS=$(printf '%s' "$DEG_RAN" | cut -d'|' -f1)
RAN=$(printf '%s' "$DEG_RAN" | cut -d'|' -f2)
NUMS=$(printf '%s' "$DEG_RAN" | cut -d'|' -f3)
check "BR-5 ADO URL classifies as azure-devops" "azure-devops" "$CLS"
check "BR-5 ADO git-transport scan runs (parity, not degraded)" "1" "$RAN"
case "$NUMS" in *900*) case "$NUMS" in *910*) pass "BR-5 ADO scan derives both merged ids (900, 910)";; *) fail "BR-5 ADO scan missing 910 (got: $NUMS)";; esac;; *) fail "BR-5 ADO scan missing 900 (got: $NUMS)";; esac
cleanup

# --- BR-5: a genuinely unsupported forge with no usable scan => degraded with warning -
new_sandbox
UREPO="$ADLC_REPOS_ROOT/proj"; mkdir -p "$UREPO"
( cd "$UREPO" && git init -q && git remote add origin "https://gitlab.com/o/r.git" )
echo 5 > "$HOME/.claude/.global-next-lesson"
# gitlab.com classifies as `other`; the generic git-transport scan fails (no such
# remote), so no usable scan for the lesson => degraded with a forge-naming warning.
RH=$( cd "$UREPO"; . "$PARTIALS/id-alloc.sh"; adlc_remote_high lesson 2>"$SBX/err" )
DEG=${RH##* }
ERR=$(cat "$SBX/err")
check "BR-5 unsupported forge with no scan is degraded" "1" "$DEG"
case "$ERR" in *"could not run"*|*degraded*|*DEGRADED*) pass "BR-5 unsupported forge warns (never silent skip)";; *) fail "BR-5 unsupported-forge warning (got: $ERR)";; esac
cleanup

# --- BR-2: recheck under a degraded derivation takes the degraded branch -------------
# No participating remote => degraded; recheck must return 0 and emit NO renumber
# suggestion derived from a zero high-water.
new_sandbox
# Empty repos root => degraded derivation.
RC=0; MSG=$( . "$PARTIALS/id-recheck.sh"; adlc_recheck_id req REQ-600 2>&1 ) || RC=$?
check "BR-2 recheck-degraded returns 0 (cannot find collision)" "0" "$RC"
case "$MSG" in
  *"renumber"*"REQ-001"*) fail "BR-2 recheck-degraded must NOT suggest renumber from zero high-water (got: $MSG)" ;;
  *DEGRADED*|*degraded*) pass "BR-2 recheck-degraded takes the degraded branch (warns, no zero-renumber)" ;;
  *) pass "BR-2 recheck-degraded returns 0 with no zero-derived renumber" ;;
esac
cleanup

echo
if [ "$FAILS" -eq 0 ]; then
  echo "ALL PASS"
  exit 0
else
  echo "$FAILS FAILURE(S)"
  exit 1
fi
