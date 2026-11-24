#!/bin/sh
# partials/tests/id-recheck-rewrite.test.sh — BUG-294: the id recheck must still know
# this machine's own reservation after the reservation ref's commit SHA has changed.
#
# A history rewrite (2026-11-01, LESSON-905) gave every refs/adlc/ids/* commit a new SHA
# and kept its subject, `adlc-id-reservation kind=<k> num=<n> nonce=<nonce>`. The
# own-reservation ledger identified a reservation by SHA alone, so adlc_recheck_id called
# the machine's own id a COLLISION. The allocator now records the nonce beside the SHA
# and the recheck accepts a ref whose subject carries a nonce the ledger holds for that
# kind and number.
#
# What must NOT pass is pinned here too: a ledger entry for the same kind and number is
# never proof on its own. A colleague's reservation of the same id, a subject for
# another number, a nonce that only resembles a recorded one, a three-field (pre-fix)
# ledger line whose SHA no longer matches, and a symlinked ledger all stay a collision.
#
# Fully offline: a throwaway HOME, ADLC_HOME and ADLC_REPOS_ROOT per machine, and a
# local bare repo standing in for the remote. Run under every shell by run.sh:
#   sh partials/tests/run.sh        (or: <shell> partials/tests/id-recheck-rewrite.test.sh)
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
has() { # has <desc> <needle> <haystack>
  case "$3" in *"$2"*) pass "$1";; *) fail "$1 (no '$2' in: $3)";; esac
}

# Two machines on one remote. A allocates; B is the colleague, with a ledger of its own.
SBX=$(mktemp -d -t idrecheck.XXXXXX)
trap 'rm -rf "$SBX"' EXIT
GIT_TERMINAL_PROMPT=0; export GIT_TERMINAL_PROMPT
# dash names no sourced file, so id-recheck.sh finds id-alloc.sh, and id-alloc.sh finds
# adlc-home.sh, through ToolkitRoot there (REQ-610). run.sh unsets it; this harness sets it.
ADLC_TOOLKIT_ROOT=$(CDPATH= cd -- "$PARTIALS/.." && pwd); export ADLC_TOOLKIT_ROOT
BARE="$SBX/shared.git"; git init -q --bare "$BARE"
HA="$SBX/homeA"; HB="$SBX/homeB"; AA="$SBX/stateA"; AB="$SBX/stateB"
ROOTA="$SBX/reposA"; ROOTB="$SBX/reposB"; RA="$ROOTA/proj"; RB="$ROOTB/proj"
mkdir -p "$HA" "$HB" "$AA" "$AB" "$ROOTA" "$ROOTB"
LEDGER="$AA/.adlc-own-reservations"
( HOME="$HA"; export HOME
  git clone -q "$BARE" "$RA" 2>/dev/null
  cd "$RA" && git config user.email a@a && git config user.name a \
    && git commit -q --allow-empty -m init && git push -q origin HEAD:main 2>/dev/null )
( HOME="$HB"; export HOME
  git clone -q "$BARE" "$RB" 2>/dev/null
  cd "$RB" && git config user.email b@b && git config user.name b )

alloc_a() { # alloc_a <kind> -> prints the allocated number
  ( HOME="$HA"; ADLC_HOME="$AA"; ADLC_REPOS_ROOT="$ROOTA"; export HOME ADLC_HOME ADLC_REPOS_ROOT
    cd "$RA" && . "$PARTIALS/id-alloc.sh" && adlc_alloc_id "$1" 2>/dev/null )
}
recheck_a() { # recheck_a <kind> <ID> -> RC and MSG (stdout and stderr together)
  RC=0
  MSG=$( HOME="$HA"; ADLC_HOME="$AA"; ADLC_REPOS_ROOT="$ROOTA"; export HOME ADLC_HOME ADLC_REPOS_ROOT
         cd "$RA" && . "$PARTIALS/id-recheck.sh" && adlc_recheck_id "$1" "$2" 2>&1 ) || RC=$?
}
recheck_b() { # recheck_b <kind> <ID> -> RC
  RC=0
  ( HOME="$HB"; ADLC_HOME="$AB"; ADLC_REPOS_ROOT="$ROOTB"; export HOME ADLC_HOME ADLC_REPOS_ROOT
    cd "$RB" && . "$PARTIALS/id-recheck.sh" && adlc_recheck_id "$1" "$2" >/dev/null 2>&1 ) || RC=$?
}
ref_sha() { git -C "$BARE" rev-parse "refs/adlc/ids/$1/$2"; }
ref_subject() { git -C "$BARE" log -1 --format=%s "refs/adlc/ids/$1/$2"; }
commit_on_remote() { # commit_on_remote <tree> — message on stdin; another address than A's
  GIT_AUTHOR_NAME=a GIT_AUTHOR_EMAIL=rewritten@example.invalid \
  GIT_COMMITTER_NAME=a GIT_COMMITTER_EMAIL=rewritten@example.invalid \
    git -C "$BARE" commit-tree "$1"
}
# The rewrite: the same tree and the same message under another address, so the commit
# gets another SHA and keeps its subject. This is what the 2026-11-01 rewrite did.
rewrite_ref() { # rewrite_ref <kind> <num>
  RW_OLD=$(ref_sha "$1" "$2")
  RW_NEW=$(git -C "$BARE" log -1 --format=%B "$RW_OLD" | commit_on_remote "$(git -C "$BARE" rev-parse "${RW_OLD}^{tree}")")
  git -C "$BARE" update-ref "refs/adlc/ids/$1/$2" "$RW_NEW"
}
# Another commit altogether at the ref, with the subject given.
put_ref() { # put_ref <kind> <num> <subject>
  PR_NEW=$(printf '%s\n' "$3" | commit_on_remote "$(git -C "$BARE" hash-object -t tree /dev/null)")
  git -C "$BARE" update-ref "refs/adlc/ids/$1/$2" "$PR_NEW"
}

# --- 1. the defect: an own reservation, its commit rewritten ---------------------------
echo 700 > "$AA/.global-next-req"
N=$(alloc_a req)
check "BUG-294 setup: machine A allocates req 700" "700" "$N"
SHA0=$(ref_sha req 700)
SUBJ0=$(ref_subject req 700)
NONCE0=${SUBJ0#adlc-id-reservation kind=req num=700 nonce=}
recheck_a req REQ-700
check "BUG-294: own reservation rechecks clear before the rewrite" "0" "$RC"
REFS_BEFORE=$(git -C "$RA" for-each-ref)
rewrite_ref req 700
SHA1=$(ref_sha req 700)
if [ -n "$SHA1" ] && [ "$SHA1" != "$SHA0" ]; then pass "BUG-294 setup: the rewrite changed the ref's SHA"; else fail "BUG-294 setup: the rewrite changed the ref's SHA (still '$SHA1')"; fi
check "BUG-294 setup: the rewrite kept the subject" "$SUBJ0" "$(ref_subject req 700)"
recheck_a req REQ-700
check "BUG-294: own reservation rechecks clear after its commit was rewritten" "0" "$RC"
has "BUG-294: the recheck says the rewritten reservation is this machine's own" "self, not a collision" "$MSG"
case "$MSG" in *COLLISION*) fail "BUG-294: no COLLISION is printed for the machine's own id (got: $MSG)";; *) pass "BUG-294: no COLLISION is printed for the machine's own id";; esac
# Reading the ref's commit leaves the working copy's refs and FETCH_HEAD as they were.
if [ "$REFS_BEFORE" = "$(git -C "$RA" for-each-ref)" ]; then pass "BUG-294: the recheck creates no ref in the working copy"; else fail "BUG-294: the recheck creates no ref in the working copy (now: $(git -C "$RA" for-each-ref | tr '\n' ' '))"; fi
check "BUG-294: the recheck writes no FETCH_HEAD" "absent" "$([ -e "$RA/.git/FETCH_HEAD" ] && echo present || echo absent)"
# The same with a refspec that maps every remote ref to a tracking ref: a fetch that
# names a source still updates what the configured refspec maps it to, unless told not to.
git -C "$RA" config remote.origin.fetch '+refs/*:refs/remotes/origin/*'
rewrite_ref req 700
recheck_a req REQ-700
check "BUG-294: a reservation rewritten twice rechecks clear, refspec mapping every ref" "0" "$RC"
if [ "$REFS_BEFORE" = "$(git -C "$RA" for-each-ref)" ]; then pass "BUG-294: the recheck creates no tracking ref under that refspec"; else fail "BUG-294: the recheck creates no tracking ref under that refspec (now: $(git -C "$RA" for-each-ref | tr '\n' ' '))"; fi
git -C "$RA" config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'

# --- 2. what the allocator records ------------------------------------------------------
# The SHA line is unchanged, so a reader from before this fix still matches it whole.
if grep -qxF "req 700 $SHA0" "$LEDGER" 2>/dev/null; then pass "BUG-294: the ledger keeps the three-field SHA line"; else fail "BUG-294: the ledger keeps the three-field SHA line (ledger: $(cat "$LEDGER" 2>/dev/null))"; fi
if [ -n "$NONCE0" ] && grep -qxF "req 700 nonce=$NONCE0" "$LEDGER" 2>/dev/null; then pass "BUG-294: the ledger records the reservation's nonce"; else fail "BUG-294: the ledger records the reservation's nonce (ledger: $(cat "$LEDGER" 2>/dev/null))"; fi

# --- 3. must not pass: the same kind and number is never enough ------------------------
recheck_b req REQ-700
check "BUG-294: the colleague's machine (no ledger entry) still collides" "1" "$RC"
# A colleague's reservation of the same id: same kind, same number, their own nonce.
put_ref req 700 "adlc-id-reservation kind=req num=700 nonce=1700000000-4242-00c0ffee00c0ffee"
check "BUG-294 setup: A's ledger still holds its lines for req 700" "2" "$(grep -c '^req 700 ' "$LEDGER" 2>/dev/null)"
recheck_a req REQ-700
check "BUG-294: a colleague's reservation of the same id is a collision" "1" "$RC"
has "BUG-294: the collision names the renumber command" "adlc renumber REQ-700 " "$MSG"
has "BUG-294: the collision says the ledger holds an entry for the id" "own-reservation ledger holds an entry for req 700" "$MSG"
# A's nonce in a subject that is not this reservation's.
put_ref req 700 "adlc-id-reservation kind=req num=701 nonce=$NONCE0"
recheck_a req REQ-700
check "BUG-294: A's nonce under another number in the subject is a collision" "1" "$RC"
put_ref req 700 "adlc-id-reservation kind=bug num=700 nonce=$NONCE0"
recheck_a req REQ-700
check "BUG-294: A's nonce under another kind in the subject is a collision" "1" "$RC"
put_ref req 700 "adlc-id-reservation kind=req num=700 nonce=${NONCE0%?}"
recheck_a req REQ-700
check "BUG-294: a nonce that is a prefix of A's is a collision" "1" "$RC"
put_ref req 700 "adlc-id-reservation kind=req num=700 nonce=${NONCE0}0"
recheck_a req REQ-700
check "BUG-294: a nonce that extends A's is a collision" "1" "$RC"
put_ref req 700 "adlc-id-reservation kind=req num=700 nonce=$NONCE0 and more"
recheck_a req REQ-700
check "BUG-294: text after the nonce is a collision" "1" "$RC"
put_ref req 700 "adlc-id-reservation kind=req num=700 nonce=.*"
recheck_a req REQ-700
check "BUG-294: a pattern in place of the nonce is a collision" "1" "$RC"
put_ref req 700 "a note about the id
adlc-id-reservation kind=req num=700 nonce=$NONCE0"
recheck_a req REQ-700
check "BUG-294: A's nonce on a later line of the message is a collision" "1" "$RC"

# --- 4. a three-field ledger line (written before this fix) -----------------------------
N=$(alloc_a req)
check "BUG-294 setup: machine A allocates req 701" "701" "$N"
# A nonce the ledger holds for ANOTHER number proves nothing about this one.
SUBJ1=$(ref_subject req 701)
NONCE1=${SUBJ1#adlc-id-reservation kind=req num=701 nonce=}
if [ -n "$NONCE1" ] && grep -qxF "req 701 nonce=$NONCE1" "$LEDGER" 2>/dev/null; then pass "BUG-294 setup: the ledger holds req 701's nonce"; else fail "BUG-294 setup: the ledger holds req 701's nonce"; fi
put_ref req 700 "adlc-id-reservation kind=req num=700 nonce=$NONCE1"
recheck_a req REQ-700
check "BUG-294: a nonce recorded for req 701 does not clear req 700" "1" "$RC"
# Nor do lines for a number that req 700 only begins, or only begins with.
SHA700=$(ref_sha req 700)
printf '%s\n' "req 70 $SHA700" "req 70 nonce=$NONCE1" "req 7000 $SHA700" "req 7000 nonce=$NONCE1" "bug 700 $SHA700" "bug 700 nonce=$NONCE1" >> "$LEDGER"
recheck_a req REQ-700
check "BUG-294: lines for req 70, req 7000 and bug 700 do not clear req 700" "1" "$RC"
grep -v '^req 701 nonce=' "$LEDGER" > "$LEDGER.tmp" && mv "$LEDGER.tmp" "$LEDGER"
check "BUG-294 setup: req 701 has only its three-field line" "1" "$(grep -c '^req 701 ' "$LEDGER")"
recheck_a req REQ-701
check "BUG-294: a three-field line still clears its own reservation by SHA" "0" "$RC"
rewrite_ref req 701
recheck_a req REQ-701
check "BUG-294: a three-field line never clears a ref whose SHA changed" "1" "$RC"
has "BUG-294: that collision says the ledger holds an entry for the id" "own-reservation ledger holds an entry for req 701" "$MSG"

# --- 5. a symlinked ledger is refused by the reader and by the writer (LESSON-014) ------
N=$(alloc_a req)
check "BUG-294 setup: machine A allocates req 702" "702" "$N"
mv "$LEDGER" "$AA/ledger-elsewhere" && ln -s "$AA/ledger-elsewhere" "$LEDGER"
recheck_a req REQ-702
check "BUG-294: a symlinked ledger clears nothing by SHA" "1" "$RC"
rewrite_ref req 702
recheck_a req REQ-702
check "BUG-294: a symlinked ledger clears nothing by nonce" "1" "$RC"
N=$(alloc_a req)
check "BUG-294 setup: machine A allocates req 703 with the ledger symlinked" "703" "$N"
check "BUG-294: the allocator writes nothing through a symlinked ledger" "0" "$(grep -c '^req 703 ' "$AA/ledger-elsewhere")"
rm -f "$LEDGER" && mv "$AA/ledger-elsewhere" "$LEDGER"
recheck_a req REQ-702
check "BUG-294: the same ledger as a regular file clears the rewritten reservation" "0" "$RC"

# --- 6. another kind: bug ----------------------------------------------------------------
echo 50 > "$AA/.global-next-bug"
N=$(alloc_a bug)
check "BUG-294 setup: machine A allocates bug 50" "50" "$N"
rewrite_ref bug 50
recheck_a bug BUG-050
check "BUG-294: a rewritten bug reservation rechecks clear" "0" "$RC"
has "BUG-294: and is reported as this machine's own" "self, not a collision" "$MSG"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "ALL PASS"
  exit 0
else
  echo "$FAILS FAILURE(S)"
  exit 1
fi
