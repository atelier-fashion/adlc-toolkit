#!/bin/sh
# partials/tests/migrate-home.test.sh — REQ-663 AC-4, BR-5, BR-6, BR-15 (TASK-236).
#
# A sandbox HOME, default-installed and then migrated by the real install.sh, under which
# the id-alloc fence runs in the shell run.sh hands it ($ADLC_TEST_SHELL):
#
#   current_copy_allocates  — a consumer whose vendored partials are current allocates N,
#                             fast-forwards the migrated counter to N+1, and leaves no
#                             directory at the old lock path
#   stale_copy_fails_loud   — a consumer carrying the pre-REQ-654 id-alloc.sh, frozen in
#                             fixtures/, aborts within six seconds with the allocator's
#                             own lock error, allocates nothing, and leaves the migrated
#                             counter and its compatibility symlink alone
#   back_again              — after --back the same current copy allocates under the
#                             default home
#
# Sandbox by construction: every child gets an explicit HOME and ADLC_REPOS_ROOT, and a
# stub launchctl first on PATH, because `launchctl bootout gui/<uid> <plist>` finds its
# agent by the label inside the plist and would reach the real one. The consumer has no
# remote, so adlc_remote_high degrades, as AC-4 says it must to reach the lock.
#
#   ADLC_TEST_SHELL=dash sh partials/tests/migrate-home.test.sh
# or, for bash, zsh, /bin/sh and dash in turn:  sh partials/tests/run.sh
#
# Exits 0 iff every check passes and the executed-check count clears its floor.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
ROOT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}

FAILS=0
CHECKS=0
pass() { CHECKS=$((CHECKS + 1)); echo "PASS: $1"; }
fail() { CHECKS=$((CHECKS + 1)); echo "FAIL: $1"; FAILS=$((FAILS + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (expected '$2', got '$3')"; fi
}

# ${T%/}: the engine normalizes <dir>, and a macOS TMPDIR ends in a slash.
T=${TMPDIR:-/tmp}
SANDBOX=$(mktemp -d "${T%/}/adlc-migrate-test.XXXXXX") || { echo "migrate-home.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "migrate-home.test.sh: sandbox path invalid" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-migrate-test.*) ;;
  *) echo "migrate-home.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

H="$SANDBOX/home"
CLONE="$SANDBOX/clone"
STUB="$SANDBOX/stub"
REPOS="$SANDBOX/repos"
DEST="$H/adlc-home"
mkdir -p "$H" "$STUB" "$REPOS" "$CLONE/partials" "$CLONE/tools/adlc" "$CLONE/tools/delegate" "$CLONE/agents" "$CLONE/spec" \
  || { echo "migrate-home.test.sh: could not build the sandbox" >&2; exit 1; }

printf '#!/bin/sh\nexit 0\n' > "$STUB/launchctl"
chmod +x "$STUB/launchctl"
SANDBOX_PATH="$STUB:/usr/bin:/bin:/usr/sbin:/sbin"
case "$(PATH=$SANDBOX_PATH command -v launchctl)" in
  "$STUB/launchctl") ;;
  *) echo "migrate-home.test.sh: launchctl must resolve to the stub" >&2; exit 1 ;;
esac

# A minimal clone: the installers, the partials, the Python tools, one skill, one agent.
cp "$ROOT/install.sh" "$ROOT/VERSION" "$CLONE/"
cp "$PARTIALS"/*.sh "$CLONE/partials/"
cp "$ROOT"/tools/adlc/*.py "$CLONE/tools/adlc/"
for f in "$ROOT"/tools/delegate/*; do
  if [ -f "$f" ]; then cp "$f" "$CLONE/tools/delegate/"; fi
done
cp -R "$ROOT/.claude-plugin" "$CLONE/"
printf -- '---\nname: spec\ndescription: d\n---\n' > "$CLONE/spec/SKILL.md"
printf -- '---\nname: reflector\n---\n' > "$CLONE/agents/reflector.md"
( cd "$CLONE" && git init -q && git add -A \
    && git -c user.email=t@t -c user.name=t commit -q -m clone ) \
  || { echo "migrate-home.test.sh: could not commit the sandbox clone" >&2; exit 1; }

# run_sandboxed <command...> — a scrubbed environment, cwd the sandbox HOME.
run_sandboxed() {
  ( cd "$H" && env -i HOME="$H" PATH="$SANDBOX_PATH" USER="${USER:-u}" ADLC_REPOS_ROOT="$REPOS" \
      TMPDIR="${TMPDIR:-/tmp}" PYTHONDONTWRITEBYTECODE=1 GIT_TERMINAL_PROMPT=0 "$@" )
}

printf '# rc\n' > "$H/.zshrc"; cp "$H/.zshrc" "$H/.bash_profile"; cp "$H/.zshrc" "$H/.profile"
run_sandboxed bash "$CLONE/install.sh" > "$SANDBOX/install.log" 2>&1
check "setup: the default install exits 0" 0 "$?"
printf '41\n' > "$H/.claude/.global-next-req"
printf '7\n' > "$H/.claude/.global-next-bug"
printf '9\n' > "$H/.claude/.global-next-lesson"
printf 'delegate:\n  enabled: false\n' > "$H/.claude/adlc/config.yml"

run_sandboxed bash "$CLONE/install.sh" --migrate-home "$DEST" > "$SANDBOX/migrate.log" 2>&1
RC=$?
check "setup: the migration exits 0" 0 "$RC"
if [ "$RC" -ne 0 ]; then
  sed -n '1,40p' "$SANDBOX/migrate.log"
  echo "migrate-home.test.sh [$SUT]: setup failed, stopping"
  exit 1
fi
check "setup: the counter link names the migrated home" "$DEST/.global-next-req" "$(readlink "$H/.claude/.global-next-req")"

# A consumer repo, with a vendored copy of the partials a skill would source first.
mk_consumer() { # mk_consumer <name>
  mkdir -p "$REPOS/$1/.adlc/partials" || return 1
  cp "$PARTIALS"/*.sh "$REPOS/$1/.adlc/partials/" || return 1
  ( cd "$REPOS/$1" && git init -q )
}
mk_consumer current || exit 1
mk_consumer stale || exit 1
cp "$HERE/fixtures/id-alloc-pre-req-654.sh" "$REPOS/stale/.adlc/partials/id-alloc.sh"

# The fence AC-4 names. HOME's ~/.claude/skills is the sandbox clone.
FENCE='if [ -f .adlc/partials/id-alloc.sh ]; then . .adlc/partials/id-alloc.sh; else . ~/.claude/skills/partials/id-alloc.sh; fi; adlc_alloc_id req'
run_fence() { # run_fence <consumer>
  ( cd "$REPOS/$1" && env -i HOME="$H" PATH="$SANDBOX_PATH" USER="${USER:-u}" ADLC_REPOS_ROOT="$REPOS" \
      GIT_TERMINAL_PROMPT=0 "$SUT" -c "$FENCE" ) > "$SANDBOX/fence.out" 2> "$SANDBOX/fence.err"
}

# ---------------------------------------------------------------------------
run_fence current
check "current_copy_allocates: rc 0" 0 "$?"
check "current_copy_allocates: allocates N" 41 "$(cat "$SANDBOX/fence.out")"
check "current_copy_allocates: fast-forwards the migrated counter" 42 "$(cat "$DEST/.global-next-req")"
check "current_copy_allocates: the old path still resolves to it" 42 "$(cat "$H/.claude/.global-next-req")"
if [ -d "$H/.claude/.global-next-req.lock.d" ]; then fail "current_copy_allocates: a directory at the old lock path"
else pass "current_copy_allocates: no directory at the old lock path"; fi
if [ -f "$H/.claude/.global-next-req.lock.d" ]; then pass "current_copy_allocates: the tombstone stands"
else fail "current_copy_allocates: the tombstone is gone"; fi

# ---------------------------------------------------------------------------
STARTED=$(date +%s)
run_fence stale
RC=$?
ELAPSED=$(( $(date +%s) - STARTED ))
if [ "$RC" -ne 0 ]; then pass "stale_copy_fails_loud: non-zero (rc $RC)"
else fail "stale_copy_fails_loud: the stale copy returned 0"; fi
check "stale_copy_fails_loud: allocates nothing" "" "$(cat "$SANDBOX/fence.out")"
if grep -q 'failed to acquire .* after 50 retries' "$SANDBOX/fence.err"; then pass "stale_copy_fails_loud: the allocator's own abort message"
else fail "stale_copy_fails_loud: stderr was: $(cat "$SANDBOX/fence.err")"; fi
if [ "$ELAPSED" -le 7 ]; then pass "stale_copy_fails_loud: within the lock budget (${ELAPSED}s)"
else fail "stale_copy_fails_loud: took ${ELAPSED}s"; fi
check "stale_copy_fails_loud: the migrated counter stands" 42 "$(cat "$DEST/.global-next-req")"
check "stale_copy_fails_loud: the old path still resolves to it" 42 "$(cat "$H/.claude/.global-next-req")"
check "stale_copy_fails_loud: still a symlink" "$DEST/.global-next-req" "$(readlink "$H/.claude/.global-next-req")"
if [ -d "$H/.claude/.global-next-req.lock.d" ]; then fail "stale_copy_fails_loud: it made a directory at the lock path"
else pass "stale_copy_fails_loud: no directory at the lock path"; fi

# ---------------------------------------------------------------------------
run_sandboxed bash "$CLONE/install.sh" --migrate-home --back > "$SANDBOX/back.log" 2>&1
check "back_again: --back exits 0" 0 "$?"
run_fence current
check "back_again: allocates under the default home" "42" "$(cat "$SANDBOX/fence.out")"
check "back_again: the real counter moved on" 43 "$(cat "$H/.claude/.global-next-req")"
if [ -L "$H/.claude/.global-next-req" ]; then fail "back_again: the counter is still a symlink"
else pass "back_again: the counter is a real file"; fi
if [ -e "$DEST" ]; then fail "back_again: the migrated home remains"
else pass "back_again: the migrated home is gone"; fi

# ---------------------------------------------------------------------------
FLOOR=22
if [ "$CHECKS" -lt "$FLOOR" ]; then
  echo "FAIL: only $CHECKS checks ran (floor $FLOOR) — a case was skipped"
  FAILS=$((FAILS + 1))
fi
echo "migrate-home.test.sh [$SUT]: $CHECKS checks, $FAILS failure(s)"
[ "$FAILS" -eq 0 ]
