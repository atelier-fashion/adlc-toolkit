#!/bin/sh
# partials/tests/redact-fence.test.sh — a failed credential redaction never reaches
# the delegate. The corpus is a transcript or a diff, and a third party is on the
# other end of `adlc-read` (LESSON-746), so "best-effort" stops at the handover.
#
# The fences are EXTRACTED from the real files and run under the shell being tested,
# with a real skill-flag.sh and these stubs first on PATH:
#   sed         fails on an in-place edit, after leaving the .bak a real sed could
#               leave behind; every other call goes to the real sed
#   adlc-read   copies the corpus it was handed, so "reached" is a file on disk
#   extract-chat  copies the fixture transcript
#
# Cases, for wrapup/SKILL.md Step 4, proceed/SKILL.md Phase 5 and the
# agents/delegate-pre-pass.md protocol (its steps 3 and 4 run as one script):
#   <site>_sed_fails  — rc 0, the delegate is not reached, exactly one stderr line,
#                       no `invoked` or `exit` mark, nothing left in TMPDIR
#   <site>_sed_works  — the positive control (LESSON-602): the delegate IS reached,
#                       with the key redacted, and `invoked`/`exit` are marked
#   old_shape_control — the shape this harness retired, `sed … && rm` followed by an
#                       unconditional call, reaches the stub under the same failing
#                       sed: the defect as an executable fact, and proof that "the
#                       stub was not reached" is not the harness failing to run
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL):
#   ADLC_TEST_SHELL=dash sh partials/tests/redact-fence.test.sh
# or, for bash, zsh, /bin/sh and dash in turn:  sh partials/tests/run.sh
#
# Exits 0 iff every check passes and the executed-case count clears its floor.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
TOOLKIT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}
REAL_SED=$(command -v sed)

FAILS=0
CASES=0
pass() { echo "PASS: $1"; CASES=$((CASES + 1)); }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (expected '$2', got '$3')"; fi
}

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-redactfence.XXXXXX") || { echo "redact-fence.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "redact-fence.test.sh: sandbox path invalid" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-redactfence.*) ;;
  *) echo "redact-fence.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
trap 'rm -rf "$SANDBOX"' EXIT INT TERM
unset CLAUDE_PLUGIN_ROOT ADLC_TOOLKIT_ROOT

# Assembled here so the file itself holds nothing credential-shaped.
KEY="sk-$(printf 'a1b2%.0s' 1 2 3 4 5 6)"

# ===========================================================================
# 1. Extraction
# ===========================================================================
# Leading indentation is dropped (each fence sits in a list item). More or fewer
# than one match is a FAIL, never a skip: a moved fence must not pass vacuously.
extract() { # extract <desc> <file> <needle> <out>
  awk -v needle="$3" '
    { t = $0; sub(/^[ \t]+/, "", t) }
    !inf && t ~ /^```(sh|bash|shell)[ \t]*$/ { inf = 1; buf = ""; next }
    inf && t ~ /^```[ \t]*$/ { inf = 0; if (index(buf, needle)) { body = buf; n++ }; next }
    inf { buf = buf t "\n" }
    END { printf "%s", body; exit (n == 1 ? 0 : 1) }' "$2" > "$4"
  check "extraction: exactly one $1 fence" "0" "$?"
}

extract "wrapup delegate" "$TOOLKIT/wrapup/SKILL.md" 'command "$ADLC_READ_BIN" --no-warn --paths "$TMPFILE"' "$SANDBOX/wrapup.fence"
extract "proceed delegate" "$TOOLKIT/proceed/SKILL.md" 'command "$ADLC_READ_BIN" --no-warn --paths "$TMPFILE"' "$SANDBOX/proceed.fence"
extract "pre-pass redaction" "$TOOLKIT/agents/delegate-pre-pass.md" 'sed_exit=$?' "$SANDBOX/prepass-redact.fence"
extract "pre-pass delegate" "$TOOLKIT/agents/delegate-pre-pass.md" 'command "$ADLC_READ_BIN" --no-warn --paths "$TMP"' "$SANDBOX/prepass-call.fence"

# The prelude stands in for what precedes the fence in the real step, and is the
# only part of each script this harness wrote.
cat > "$SANDBOX/wrapup.prelude" <<'EOF'
"$DELEGATE_TOOLS"/skill-flag.sh mark "$flag" jsonl "$FIXTURE"
EOF
# proceed's fence makes its own temp file, EXIT trap and diff (BUG-299): its prelude
# is empty, so a fence that uses $TMPFILE without creating it fails here. The diff
# runs against a real repository whose local `main` is stale (see below); the
# placeholders are the only text this harness substitutes.
: > "$SANDBOX/proceed.prelude"
REPO="$SANDBOX/repo"
g() { git -C "$REPO" -c user.name=t -c user.email=t@example.invalid -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@"; }
# A: local main, stale. B: another REQ's merged work, on origin/main only.
# C: this REQ's change, on top of origin/main, holding the credential line.
git init -q "$REPO" && g checkout -q -b feat \
  && echo base > "$REPO/base.txt" && g add base.txt && g commit -q -m A && g branch main \
  && echo other > "$REPO/other-req.txt" && g add other-req.txt && g commit -q -m B \
  && g update-ref refs/remotes/origin/main HEAD \
  && printf 'plain line\nauthorization: %s trailing\n' "$KEY" > "$REPO/feature.txt" \
  && g add feature.txt && g commit -q -m C
check "fixture: the repository was built" "0" "$?"
subst_fence() { # subst_fence <integration branch> <out>
  "$REAL_SED" -e "s|<worktree>|$REPO|g" -e "s|<integrationBranch>|$1|g" "$SANDBOX/proceed.fence" > "$2"
}
cat > "$SANDBOX/prepass.prelude" <<'EOF'
REQ=REQ-000
TMP=$(mktemp "$TMPDIR/delegate-pre-pass.XXXXXX") || exit 1
trap 'rm -f "$TMP" "$TMP.bak"' EXIT
cp "$FIXTURE" "$TMP"
EOF
cat "$SANDBOX/wrapup.prelude" "$SANDBOX/wrapup.fence" > "$SANDBOX/wrapup.script"
subst_fence main "$SANDBOX/proceed.fence.main"
subst_fence no-such-branch "$SANDBOX/proceed.fence.nobase"
cat "$SANDBOX/proceed.prelude" "$SANDBOX/proceed.fence.main" > "$SANDBOX/proceed.script"
cat "$SANDBOX/proceed.prelude" "$SANDBOX/proceed.fence.nobase" > "$SANDBOX/proceed-nobase.script"
cat "$SANDBOX/prepass.prelude" "$SANDBOX/prepass-redact.fence" "$SANDBOX/prepass-call.fence" > "$SANDBOX/prepass.script"

# ===========================================================================
# 2. The harness
# ===========================================================================
run_case() { # run_case <name> <script> <sed-works|sed-fails> — leaves D/RC/ERR set
  D="$SANDBOX/$1"
  mkdir -p "$D/cwd/.adlc/partials" "$D/bin" "$D/tools" "$D/home" "$D/tmp"
  printf 'plain line\nauthorization: %s trailing\n' "$KEY" > "$D/fixture"
  cp "$TOOLKIT/tools/delegate/skill-flag.sh" "$D/tools/skill-flag.sh"

  printf 'ADLC_READ_BIN="%s"\nexport ADLC_READ_BIN\n' "$D/bin/adlc-read" > "$D/cwd/.adlc/partials/delegate-gate.sh"
  printf 'DELEGATE_TOOLS="%s"\nexport DELEGATE_TOOLS\n' "$D/tools" > "$D/cwd/.adlc/partials/delegate-tools-path.sh"

  printf '#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s"\n' "$D/telemetry" > "$D/tools/emit-telemetry.sh"
  printf '#!/bin/sh\ncp "$3" "%s"\n' "$D/delegate-saw" > "$D/bin/adlc-read"
  printf '#!/bin/sh\ncat "$1" > "$3"\n' > "$D/bin/extract-chat"
  if [ "$3" = "sed-fails" ]; then
    cat > "$D/bin/sed" <<EOF
#!/bin/sh
case " \$* " in
  *" -i.bak "*) for f; do :; done; cp "\$f" "\$f.bak"; exit 1 ;;
esac
exec "$REAL_SED" "\$@"
EOF
  fi
  chmod +x "$D"/bin/* "$D"/tools/*

  FLAG="$D/flag"
  : > "$FLAG"
  # The sourced partials supply what the pre-pass protocol's step 0 would.
  { printf '. ./.adlc/partials/delegate-gate.sh\n. ./.adlc/partials/delegate-tools-path.sh\n'
    cat "$2"; } > "$D/cwd/script.sh"
  ( cd "$D/cwd" && flag="$FLAG" FIXTURE="$D/fixture" HOME="$D/home" TMPDIR="$D/tmp" \
      PATH="$D/bin:$PATH" "$SUT" ./script.sh > "$D/stdout" 2> "$D/stderr" )
  RC=$?
  ERR=$(cat "$D/stderr")
}

marked() { "$TOOLKIT/tools/delegate/skill-flag.sh" read "$D/flag" "$1"; }
reached() { if [ -f "$D/delegate-saw" ]; then echo yes; else echo no; fi; }
leftovers() { find "$D/tmp" -type f | wc -l | tr -d ' '; }

expect_withheld() { # expect_withheld <site> <script> <stderr line> <telemetry args or ->
  run_case "$1_sed_fails" "$2" sed-fails
  check "$1_sed_fails: rc 0, a fall-through and not an error" "0" "$RC"
  check "$1_sed_fails: the delegate is not reached" "no" "$(reached)"
  check "$1_sed_fails: exactly one stderr line" "$3" "$ERR"
  check "$1_sed_fails: invoked stays unset" "" "$(marked invoked)"
  check "$1_sed_fails: exit stays unset" "" "$(marked exit)"
  check "$1_sed_fails: no temp file or .bak survives" "0" "$(leftovers)"
  if [ "$4" != "-" ]; then
    check "$1_sed_fails: telemetry" "$4" "$(cat "$D/telemetry" 2>/dev/null)"
  fi
}

expect_delegated() { # expect_delegated <site> <script> <marks? yes|no>
  run_case "$1_sed_works" "$2" sed-works
  check "$1_sed_works: rc 0" "0" "$RC"
  check "$1_sed_works: the delegate is reached" "yes" "$(reached)"
  check "$1_sed_works: no stderr" "" "$ERR"
  check "$1_sed_works: the key never left" "0" "$(grep -c "$KEY" "$D/delegate-saw" 2>/dev/null)"
  check "$1_sed_works: the redaction ran" "1" "$(grep -c '\[REDACTED\]' "$D/delegate-saw" 2>/dev/null)"
  check "$1_sed_works: no temp file or .bak survives" "0" "$(leftovers)"
  if [ "$3" = "yes" ]; then
    check "$1_sed_works: invoked marked" "1" "$(marked invoked)"
    check "$1_sed_works: exit marked" "0" "$(marked exit)"
  fi
}

# ===========================================================================
# 3. The cases
# ===========================================================================
expect_withheld wrapup "$SANDBOX/wrapup.script" "/wrapup: credential redaction failed — Claude drafting lesson directly" -
expect_delegated wrapup "$SANDBOX/wrapup.script" yes

expect_withheld proceed "$SANDBOX/proceed.script" "/proceed Phase 5: credential redaction failed for repo=<id> — reviewers running without candidates" -
expect_delegated proceed "$SANDBOX/proceed.script" yes
# BUG-299 / LESSON-391: the diff base is origin/<integrationBranch>, never local main.
# Local main is at A, so `main...HEAD` would hand over B, another REQ's work.
check "proceed_sed_works: the delegate saw this REQ's change" "1" "$(grep -c '^+++ b/feature.txt$' "$D/delegate-saw" 2>/dev/null)"
check "proceed_sed_works: not another REQ's work under a stale local main" "0" "$(grep -c 'other-req.txt' "$D/delegate-saw" 2>/dev/null)"

# BUG-299: a diff that cannot be taken (the base is not fetched) is a fall-through too.
run_case proceed_no_base "$SANDBOX/proceed-nobase.script" sed-works
check "proceed_no_base: rc 0, a fall-through and not an error" "0" "$RC"
check "proceed_no_base: the delegate is not reached" "no" "$(reached)"
check "proceed_no_base: one line of our own after git's" \
  "/proceed Phase 5: diff against origin/no-such-branch failed for repo=<id> — reviewers running without candidates" \
  "$(printf '%s\n' "$ERR" | tail -1)"
check "proceed_no_base: invoked stays unset" "" "$(marked invoked)"
check "proceed_no_base: no temp file or .bak survives" "0" "$(leftovers)"

# BUG-299: Phase 5's prose names the same base as its fence, in all three places.
check "proceed/SKILL.md: no diff against a local main" "0" "$(grep -c 'diff main\.\.\.HEAD' "$TOOLKIT/proceed/SKILL.md")"

expect_withheld prepass "$SANDBOX/prepass.script" \
  "delegate-pre-pass: credential redaction failed — not invoking the delegate; returning the degraded object" \
  "delegate-pre-pass Phase-5-prepass REQ-000 fail fallback redaction-failed -"
expect_delegated prepass "$SANDBOX/prepass.script" no

# BUG-299: the protocol's prose names the reason its step-3 fence emits. Step 3's
# lead-in and the field reference once said `api-error`, the one reason that claims
# the delegate was really called.
section() { # section <start regex> <end regex> — the lines from start up to end
  awk -v s="$1" -v e="$2" '$0 ~ s { on = 1 } on && $0 ~ e && !($0 ~ s) { exit } on' "$TOOLKIT/agents/delegate-pre-pass.md"
}
STEP3=$(section '^### 3\. ' '^```')
check "pre-pass step 3 prose: names redaction-failed" "yes" "$(printf '%s' "$STEP3" | grep -q 'reason="redaction-failed"' && echo yes || echo no)"
check "pre-pass step 3 prose: never api-error" "0" "$(printf '%s\n' "$STEP3" | grep -c 'api-error')"
REASONREF=$(section '^- `reason`=' '^- `duration_ms`')
check "pre-pass field reference: redaction-failed on a redaction failure" "yes" "$(printf '%s' "$REASONREF" | grep -q '`redaction-failed` on a redaction' && echo yes || echo no)"
check "pre-pass field reference: api-error is not a redaction failure" "0" "$(printf '%s\n' "$REASONREF" | grep -c 'non-zero OR a')"
GATEREF=$(section '^- `gate`' '^- `mode`')
check "pre-pass field reference: a redaction failure is gate=fail" "yes" "$(printf '%s' "$GATEREF" | grep -q '`fail` on a$' && printf '%s' "$GATEREF" | grep -q 'redaction (sed) failure too' && echo yes || echo no)"

cat > "$SANDBOX/old-shape.script" <<'EOF'
TMPFILE=$(mktemp "$TMPDIR/adlc-old.XXXXXX") || exit 1
trap 'rm -f "$TMPFILE" "$TMPFILE.bak"' EXIT
cp "$FIXTURE" "$TMPFILE"
sed -i.bak -E 's/x/y/' "$TMPFILE" && rm -f "$TMPFILE.bak"
command "$ADLC_READ_BIN" --no-warn --paths "$TMPFILE" --question "q"
EOF
run_case old_shape_control "$SANDBOX/old-shape.script" sed-fails
check "old_shape_control: the retired shape hands over the unredacted key" "1" "$(grep -c "$KEY" "$D/delegate-saw" 2>/dev/null)"

# ===========================================================================
# 4. Floor
# ===========================================================================
FLOOR=60
if [ "$CASES" -lt "$FLOOR" ]; then
  fail "executed-case floor: $CASES < $FLOOR"
fi
echo "redact-fence: $CASES checks, $FAILS failed"
[ "$FAILS" -eq 0 ]
