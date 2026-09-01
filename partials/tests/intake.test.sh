#!/bin/sh
# partials/tests/intake.test.sh — AC test matrix for partials/intake.sh (REQ-594 TASK-005).
#
# Fully offline: sandbox fixtures under mktemp -d, no network, no adlc-read invocation.
# The delegate is never called here — the delegation contract lives in spec/SKILL.md
# prose; what this harness owns is the partial's behavior plus the two validation
# regexes the SKILL.md specifies (see section 7's coupling note).
#
# Run under BOTH shells (BR-9 / cross-shell AC):
#   bash partials/tests/intake.test.sh
#   zsh  partials/tests/intake.test.sh
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
absent() { # absent <desc> <needle> <haystack>
  case "$3" in
    *"$2"*) fail "$1 (unexpectedly found '$2')" ;;
    *) pass "$1 (absent '$2')" ;;
  esac
}

SANDBOX=$(mktemp -d)
trap 'rm -rf "$SANDBOX"' EXIT

# The section derivation reads the requirement template relative to the CWD
# (repo-local first), so run from the repo root.
CDPATH= cd -- "$ROOT" || exit 1

. "$PARTIALS/intake.sh"

# Build a line-numbered fixture of N lines. Written with a while loop rather than
# `seq` so the harness does not depend on a non-POSIX utility.
mkfixture() { # mkfixture <path> <count> <prefix>
  _i=1
  : > "$1"
  while [ "$_i" -le "$2" ]; do
    echo "$3 $_i" >> "$1"
    _i=$((_i + 1))
  done
}

# ===========================================================================
# 1. BR-1 trigger detection — the three positive triggers and the negative
# ===========================================================================
printf 'one\ntwo\n' > "$SANDBOX/team-notes.md"

adlc_intake_detect "$SANDBOX/team-notes.md"; rc=$?
check "detect (b) bare file path rc" "0" "$rc"
check "detect (b) reason" "path" "$ADLC_INTAKE_REASON"

adlc_intake_detect "--intake $SANDBOX/team-notes.md"; rc=$?
check "detect (a) --intake <path> rc" "0" "$rc"
check "detect (a) reason" "flag" "$ADLC_INTAKE_REASON"
check "detect (a) path captured" "$SANDBOX/team-notes.md" "$ADLC_INTAKE_PATH"

adlc_intake_detect "--intake=$SANDBOX/team-notes.md"; rc=$?
check "detect (a) --intake=<path> rc" "0" "$rc"
check "detect (a=) path captured" "$SANDBOX/team-notes.md" "$ADLC_INTAKE_PATH"

LONG=$(_i=1; while [ "$_i" -le 30 ]; do echo "requirement line $_i"; _i=$((_i + 1)); done)
adlc_intake_detect "$LONG"; rc=$?
check "detect (c) 30-line input rc" "0" "$rc"
check "detect (c) reason" "lines" "$ADLC_INTAKE_REASON"

# AC-1: the common path. A one-line feature request must trip nothing.
adlc_intake_detect "add a logout button to the settings screen"; rc=$?
check "AC-1 one-line request does NOT trigger intake" "1" "$rc"
check "AC-1 no reason exported" "" "$ADLC_INTAKE_REASON"
check "AC-1 no kind exported" "" "$ADLC_INTAKE_KIND"
check "AC-1 no path exported" "" "$ADLC_INTAKE_PATH"

# Threshold boundary: BR-1(c) says "exceeding 25 lines", so 25 must NOT trigger.
B25=$(_i=1; while [ "$_i" -le 25 ]; do echo "line $_i"; _i=$((_i + 1)); done)
adlc_intake_detect "$B25"; check "boundary 25 lines does not trigger" "1" "$?"
B26=$(_i=1; while [ "$_i" -le 26 ]; do echo "line $_i"; _i=$((_i + 1)); done)
adlc_intake_detect "$B26"; check "boundary 26 lines triggers" "0" "$?"

# A path that does not exist is not a trigger on its own.
adlc_intake_detect "$SANDBOX/does-not-exist.txt"; check "nonexistent path does not trigger" "1" "$?"

# ===========================================================================
# 2. Kind classification
# ===========================================================================
printf 'x\n' > "$SANDBOX/standup-transcript.txt"
adlc_intake_detect "$SANDBOX/standup-transcript.txt"
check "kind transcript (filename)" "transcript" "$ADLC_INTAKE_KIND"

printf 'x\n' > "$SANDBOX/JIRA-42-issue.txt"
adlc_intake_detect "$SANDBOX/JIRA-42-issue.txt"
check "kind ticket (filename)" "ticket" "$ADLC_INTAKE_KIND"

printf 'x\n' > "$SANDBOX/meeting-notes.md"
adlc_intake_detect "$SANDBOX/meeting-notes.md"
check "kind notes (filename)" "notes" "$ADLC_INTAKE_KIND"

# Content signal: leading clock times mark a transcript even without a telling name.
printf '09:01 Alice: hi\n09:02 Bob: hello\n09:03 Alice: ok\n09:04 Bob: bye\n' > "$SANDBOX/raw.txt"
adlc_intake_detect "$SANDBOX/raw.txt"
check "kind transcript (timestamp content)" "transcript" "$ADLC_INTAKE_KIND"

printf 'We should let owners archive projects. It needs a confirm step.\n' > "$SANDBOX/blurb.txt"
adlc_intake_detect "$SANDBOX/blurb.txt"
check "kind prose (fallback)" "prose" "$ADLC_INTAKE_KIND"

# ===========================================================================
# 3. BR-12 segmentation and the ADR-3 budget
# ===========================================================================
mkfixture "$SANDBOX/src450.txt" 450 "line"
adlc_intake_detect "$SANDBOX/src450.txt"
adlc_intake_segment "$ADLC_INTAKE_PATH"; rc=$?
check "segment 450 lines rc" "0" "$rc"
check "segment 450 -> 3 segments" "3" "$ADLC_INTAKE_SEGMENTS"
check "segment 450 line count" "450" "$ADLC_INTAKE_LINES"
CORPUS450="$ADLC_INTAKE_CORPUS"

contains "corpus has source header" '<source name="src450.txt"' "$(cat "$CORPUS450")"
contains "corpus has S01" '<segment id="S01" lines="1-200">' "$(cat "$CORPUS450")"
contains "corpus has S02" '<segment id="S02" lines="201-400">' "$(cat "$CORPUS450")"
contains "corpus has S03 (short tail)" '<segment id="S03" lines="401-450">' "$(cat "$CORPUS450")"
check "corpus segment-block count" "3" "$(grep -c '<segment id=' "$CORPUS450")"

# AC-8 / BR-7: only the basename may appear. The sandbox dir path must not leak.
absent "AC-8 corpus carries no full path" "$SANDBOX" "$(cat "$CORPUS450")"
rm -f "$CORPUS450"

# Every source line must survive segmentation — no silent truncation anywhere.
mkfixture "$SANDBOX/src37.txt" 37 "z"
adlc_intake_detect "$SANDBOX/src37.txt"
adlc_intake_segment "$ADLC_INTAKE_PATH"
check "37 lines -> 1 segment" "1" "$ADLC_INTAKE_SEGMENTS"
check "all 37 body lines present in corpus" "37" "$(grep -c '^z ' "$ADLC_INTAKE_CORPUS")"
contains "last line survives" "z 37" "$(cat "$ADLC_INTAKE_CORPUS")"
rm -f "$ADLC_INTAKE_CORPUS"

# A final line with no trailing newline must still be counted, or the tail is lost.
printf 'a\nb\nc' > "$SANDBOX/noeol.txt"
adlc_intake_detect "$SANDBOX/noeol.txt"
adlc_intake_segment "$ADLC_INTAKE_PATH"
check "unterminated final line is counted" "3" "$ADLC_INTAKE_LINES"
rm -f "$ADLC_INTAKE_CORPUS"

# Budget boundary: 8000 lines is exactly 40 segments and must pass.
mkfixture "$SANDBOX/at-budget.txt" 8000 "b"
adlc_intake_detect "$SANDBOX/at-budget.txt"
adlc_intake_segment "$ADLC_INTAKE_PATH"; rc=$?
check "AC-10 at-budget (8000 lines) accepted" "0" "$rc"
check "AC-10 at-budget -> 40 segments" "40" "$ADLC_INTAKE_SEGMENTS"
rm -f "$ADLC_INTAKE_CORPUS"

# One line over must be REFUSED, with the size named, and no corpus produced.
#
# Called DIRECTLY (stderr redirected to a file) rather than via `ERR=$(...)`:
# command substitution runs the function in a subshell, so its variable resets
# would not reach this shell and the ADLC_INTAKE_CORPUS assertion below would read
# a stale value from the at-budget call above. Real call sites in spec/SKILL.md
# invoke it directly too, so this shape is also the faithful one.
mkfixture "$SANDBOX/over-budget.txt" 8001 "b"
adlc_intake_detect "$SANDBOX/over-budget.txt"
adlc_intake_segment "$ADLC_INTAKE_PATH" 2>"$SANDBOX/refusal.err"; rc=$?
ERR=$(cat "$SANDBOX/refusal.err")
check "AC-10 over-budget (8001 lines) rc=3" "3" "$rc"
contains "AC-10 refusal names the actual size" "8001 lines" "$ERR"
contains "AC-10 refusal names the budget" "40 segments / 8000 lines" "$ERR"
contains "AC-10 refusal says it never truncates" "never truncates" "$ERR"
check "AC-10 no corpus written on refusal" "" "$ADLC_INTAKE_CORPUS"

# Unreadable source is a distinct failure (2), not a budget refusal (3).
adlc_intake_segment "$SANDBOX/absent.txt" >/dev/null 2>&1
check "unreadable source rc=2" "2" "$?"

# ===========================================================================
# 4. BR-12 direct-read ranges (stateless — see the partial's rationale)
# ===========================================================================
check "range S01 of 4200" "1 200" "$(adlc_intake_range 1 4200)"
check "range S07 of 4200" "1201 1400" "$(adlc_intake_range 7 4200)"
check "range S21 of 4200 (exact last)" "4001 4200" "$(adlc_intake_range 21 4200)"
check "range clamps short tail" "401 450" "$(adlc_intake_range 3 450)"
adlc_intake_range 22 4200 >/dev/null 2>&1
check "range rejects out-of-range segment" "2" "$?"
adlc_intake_range 0 4200 >/dev/null 2>&1
check "range rejects segment 0" "2" "$?"
adlc_intake_range abc 4200 >/dev/null 2>&1
check "range rejects non-numeric segment" "2" "$?"
adlc_intake_range 3 >/dev/null 2>&1
check "range rejects missing total-lines" "2" "$?"

# LESSON-396 regression: segment labels are zero-padded (S01..S40), so the natural
# call after reconciliation spots a missing S08 is `adlc_intake_range 08 <lines>`.
# $(( 08 )) is an OCTAL literal — bash errors "value too great for base", zsh
# silently accepts. Shell-divergent, so a regression here would pass under the
# macOS executor shell and fail under bash. Assert every padded label 01-09.
check "LESSON-396 padded 01" "1 200"       "$(adlc_intake_range 01 4200 2>&1)"
check "LESSON-396 padded 07" "1201 1400"   "$(adlc_intake_range 07 4200 2>&1)"
check "LESSON-396 padded 08" "1401 1600"   "$(adlc_intake_range 08 4200 2>&1)"
check "LESSON-396 padded 09" "1601 1800"   "$(adlc_intake_range 09 4200 2>&1)"
check "LESSON-396 padded 10" "1801 2000"   "$(adlc_intake_range 10 4200 2>&1)"
check "LESSON-396 padded total-lines" "1 200" "$(adlc_intake_range 1 0900 2>&1)"
adlc_intake_range 08 4200 >/dev/null 2>&1
check "LESSON-396 padded call returns 0" "0" "$?"

# The range must be usable to recover the omitted segment's real content.
mkfixture "$SANDBOX/recover.txt" 450 "line"
set -- $(adlc_intake_range 2 450)
check "recovered S02 first line" "line 201" "$(sed -n "${1},${2}p" "$SANDBOX/recover.txt" | head -1)"
check "recovered S02 last line" "line 400" "$(sed -n "${1},${2}p" "$SANDBOX/recover.txt" | tail -1)"

# ===========================================================================
# 5. Credential redaction — all five patterns
# ===========================================================================
{
  echo "openai sk-abcdefghij0123456789XYZlmnop"
  echo "aws AKIAABCDEFGHIJKLMNOP"
  echo "github ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  echo "header Bearer abcdefghijklmnopqrstuvwxyz012345"
  echo "MOONSHOT_API_KEY=supersecretvalue"
  echo "SERVICE_TOKEN: tok_abcdefghijklmnop"
  echo "keep this ordinary line"
} > "$SANDBOX/creds.txt"

adlc_intake_redact "$SANDBOX/creds.txt"
check "redact rc" "0" "$?"
RED=$(cat "$SANDBOX/creds.txt")
absent "redact sk- key"        "sk-abcdefghij"    "$RED"
absent "redact AKIA key"       "AKIAABCDEFGH"     "$RED"
absent "redact ghp_ token"     "ghp_aaaaaaaa"     "$RED"
absent "redact Bearer token"   "abcdefghijklmnop" "$RED"
absent "redact _API_KEY assign" "supersecretvalue" "$RED"
absent "redact _TOKEN assign"  "tok_abcdefghijklmnop" "$RED"
contains "redact preserves ordinary text" "keep this ordinary line" "$RED"
check "redact removes the .bak file" "" "$(ls "$SANDBOX/creds.txt.bak" 2>/dev/null)"

adlc_intake_redact "$SANDBOX/nope.txt" >/dev/null 2>&1
check "redact rejects unwritable path" "2" "$?"

# ===========================================================================
# 6. Template-derived gap sections
# ===========================================================================
SECTIONS=$(adlc_intake_sections)
check "sections rc" "0" "$?"
for want in "System Model" "Business Rules" "Acceptance Criteria" "External Dependencies" "Out of Scope"; do
  contains "sections include '$want'" "$want" "$SECTIONS"
done
# Excluded because they are OUTPUTS of intake, not inputs to it. Provenance and
# Retrieved Context genuinely appear as '## ' headings in the template's guidance
# comments, so these exclusions are load-bearing, not defensive.
for skip in "Description" "Assumptions" "Open Questions" "Retrieved Context" "Provenance"; do
  absent "sections exclude '$skip'" "$skip" "$SECTIONS"
done
check "sections count" "5" "$(printf '%s\n' "$SECTIONS" | grep -c .)"

# ===========================================================================
# 7. AC-7 citation-validation regexes
#
# COUPLING NOTE: these regexes are specified in spec/SKILL.md Step 1.4 sub-step 3.5,
# not in this partial — the validation is Claude's to perform on delegate output.
# They are asserted here so that a future divergence between the documented regex
# and a tested one is visible rather than silent. If Step 1.4's regexes change,
# change these too.
# ===========================================================================
req_ok()    { printf '%s' "$1" | grep -qE '^REQ-[0-9]{3,6}$'; }
lesson_ok() { printf '%s' "$1" | grep -qE '^LESSON-[0-9]{3,6}$'; }
# Path check: charset AND no '..' anywhere (the charset permits '.', so '..' would
# otherwise slip through as parent-directory traversal).
path_ok() {
  printf '%s' "$1" | grep -qE '^[A-Za-z0-9_./-]+$' || return 1
  case "$1" in *..*) return 1 ;; esac
  return 0
}

req_ok "REQ-594";     check "AC-7 REQ-594 accepted" "0" "$?"
req_ok "REQ-999999";  check "AC-7 REQ-999999 charset-valid (dropped later by ls)" "0" "$?"
req_ok "REQ-9999999"; check "AC-7 REQ-9999999 rejected (7 digits)" "1" "$?"
req_ok "REQ-1";       check "AC-7 REQ-1 rejected (too few digits)" "1" "$?"
req_ok "REQ-594; rm -rf /"; check "AC-7 REQ with shell metachars rejected" "1" "$?"
lesson_ok "LESSON-013";   check "AC-7 LESSON-013 accepted" "0" "$?"
lesson_ok "LESSON-abc";   check "AC-7 LESSON-abc rejected" "1" "$?"

path_ok "partials/intake.sh";        check "AC-7 ordinary path accepted" "0" "$?"
path_ok "../../etc/passwd";          check "AC-7 traversal path rejected" "1" "$?"
path_ok "partials/../../../etc/pw";  check "AC-7 embedded traversal rejected" "1" "$?"
path_ok "spec/..SKILL.md";           check "AC-7 adjacent '..' rejected" "1" "$?"
path_ok 'partials/x;rm -rf /';       check "AC-7 metachar path rejected" "1" "$?"
path_ok 'partials/$(whoami).sh';     check "AC-7 command-substitution path rejected" "1" "$?"

# A REQ id that is charset-valid but does not exist must still be dropped by the
# existence check the SKILL.md pairs with the regex. That pairing is the actual
# AC-7 defense; the regex alone is necessary but not sufficient.
check "AC-7 REQ-999999 has no spec dir" "" "$(ls -d "$ROOT"/.adlc/specs/REQ-999999-* 2>/dev/null)"

# ===========================================================================
# 8. AC-9 segment-omission reconciliation
#
# Simulates a delegate response that returned S01 and S03 but silently dropped S02
# — the exact failure adversary finding F5 named. Reconciliation must notice.
# ===========================================================================
mkfixture "$SANDBOX/recon.txt" 450 "line"
adlc_intake_detect "$SANDBOX/recon.txt"
adlc_intake_segment "$ADLC_INTAKE_PATH"
EXPECTED="$ADLC_INTAKE_SEGMENTS"
TOTAL="$ADLC_INTAKE_LINES"
rm -f "$ADLC_INTAKE_CORPUS"

cat > "$SANDBOX/response.txt" <<'RESPONSE'
<segment id="S01">covered the opening</segment>
<segment id="S03">covered the tail</segment>
<distilled>a feature request</distilled>
RESPONSE

RETURNED=$(grep -o '<segment id="S[0-9][0-9]"' "$SANDBOX/response.txt" | grep -c .)
check "AC-9 expected segment count" "3" "$EXPECTED"
check "AC-9 delegate returned fewer" "2" "$RETURNED"

MISSING=""
_n=1
while [ "$_n" -le "$EXPECTED" ]; do
  _lbl=$(printf 'S%02d' "$_n")
  if ! grep -q "<segment id=\"$_lbl\"" "$SANDBOX/response.txt"; then
    MISSING="$MISSING $_lbl"
  fi
  _n=$((_n + 1))
done
check "AC-9 reconciliation identifies the omitted segment" " S02" "$MISSING"

# And the omitted segment must be recoverable by direct read at its range.
set -- $(adlc_intake_range 2 "$TOTAL")
check "AC-9 omitted segment recovered by direct read" "line 201" \
  "$(sed -n "${1},${2}p" "$SANDBOX/recon.txt" | head -1)"

# ===========================================================================
# 9. AC-6 second half — the disabled path degrades, it does not fail closed
# ===========================================================================
. "$PARTIALS/delegate-gate.sh"
( export ADLC_DISABLE_DELEGATE=1
  adlc_delegate_gate_check; g=$?
  check "AC-6 ADLC_DISABLE_DELEGATE=1 -> gate=1 (disabled)" "1" "$g"
  [ -n "$ADLC_DELEGATE_GATE_REASON" ] \
    && pass "AC-6 disabled reason recorded ($ADLC_DELEGATE_GATE_REASON)" \
    || fail "AC-6 disabled reason not recorded"
) || FAILS=$((FAILS + 1))

# With delegation disabled the intake functions must still work end to end —
# the source is read directly and the spec is still produced.
( export ADLC_DISABLE_DELEGATE=1
  adlc_intake_detect "$SANDBOX/recon.txt" || exit 1
  adlc_intake_segment "$ADLC_INTAKE_PATH" || exit 1
  [ "$ADLC_INTAKE_SEGMENTS" -eq 3 ] || exit 1
  adlc_intake_sections >/dev/null || exit 1
  rm -f "$ADLC_INTAKE_CORPUS"
)
check "AC-6 intake still operates with delegation disabled" "0" "$?"

# ===========================================================================
echo
if [ "$FAILS" -eq 0 ]; then
  echo "intake.test.sh: ALL PASS"
  exit 0
fi
echo "intake.test.sh: $FAILS FAILURE(S)"
exit 1
