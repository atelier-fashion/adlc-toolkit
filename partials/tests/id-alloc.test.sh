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

echo
if [ "$FAILS" -eq 0 ]; then
  echo "ALL PASS"
  exit 0
else
  echo "$FAILS FAILURE(S)"
  exit 1
fi
