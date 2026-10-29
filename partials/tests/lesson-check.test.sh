#!/bin/sh
# partials/tests/lesson-check.test.sh — case matrix for partials/lesson-check.sh
# (REQ-646 BR-1, BR-3, BR-5, BR-10, BR-11, BR-12, BR-13; AC-1, AC-2, AC-3, AC-5, AC-7,
# AC-13).
#
# Fully offline: every fixture lesson is written into a mktemp sandbox from this file —
# never into .adlc/knowledge/. The template, taxonomy, skill and architecture cases
# read the real tree under $ROOT (read-only).
#
# The partial is sourced into the shell running THIS file, so the shell under test is
# whichever one executes the harness. run.sh drives all four:
#   bash partials/tests/lesson-check.test.sh
#   zsh  partials/tests/lesson-check.test.sh
#   sh   partials/tests/lesson-check.test.sh
#   dash partials/tests/lesson-check.test.sh
# or via the wrapper:  sh partials/tests/run.sh
#
# Case names are load-bearing: TASK-104..110 cite them verbatim in their verification
# obligations. Rename one and those obligations point at nothing.
#
# Every case is a PASS or a FAIL — there is no skip. Every text the cases read has
# landed, so a missing fence, section or doc row is a regression, not "later". The
# summary prints `lesson-check.test.sh: <N> cases executed` and the harness FAILS when
# N is below the floor (LESSON-019: a green that ran nothing — or ran half — is a red).
# The summary guard is itself tested: summary_guard_fails_short_runs runs it alone.
# lc_summary sets DONE; the EXIT trap turns any other way out — a fatal builtin error,
# a stray `exit`, a file cut short — into rc 1 and `lesson-check.test.sh: aborted
# before summary`, never the status of whatever command ran last.
# harness_aborts_without_summary runs a truncated copy of this file to prove it.
#
# Exits 0 iff every case passes and the case floor is met.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
ROOT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)
TSHELL=${ADLC_TEST_SHELL:-sh}

CASES=0
FAILS=0
DONE=
pass() { CASES=$((CASES + 1)); printf 'PASS: %s\n' "$1"; }
fail() { CASES=$((CASES + 1)); FAILS=$((FAILS + 1)); printf 'FAIL: %s\n' "$1"; }

# >>> summary-guard (extracted and run alone by summary_guard_fails_short_runs)
lc_summary() {
  DONE=1
  printf 'lesson-check.test.sh: %s cases executed\n' "$CASES"
  if [ "$CASES" -eq 0 ]; then
    printf '%s\n' "lesson-check.test.sh: FAIL — zero cases executed; a green that ran nothing is a red (LESSON-019)"
    exit 1
  fi
  if ! [ "$CASES" -ge 60 ]; then
    printf 'lesson-check.test.sh: FAIL — %s cases executed, below the floor of 60; a block lost to an early exit or an edit is a red\n' "$CASES"
    exit 1
  fi
  if [ "$FAILS" -eq 0 ]; then
    printf '%s\n' "lesson-check.test.sh: ALL CASES PASS"
    exit 0
  fi
  printf 'lesson-check.test.sh: %s CASE(S) FAILED\n' "$FAILS"
  exit 1
}
# <<< summary-guard

# LESSON-441's full-path mktemp template (BSD and GNU agree on it). The result is
# validated BEFORE anything can be removed under it: an empty SANDBOX would turn
# `rm -rf "$SANDBOX"` into a no-op at best and a disaster at worst.
SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-lcheck.XXXXXX") || { printf '%s\n' "lesson-check.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { printf '%s\n' "lesson-check.test.sh: sandbox path invalid" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-lcheck.*) ;;
  *) printf '%s\n' "lesson-check.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
# The signal traps exit, and the exit runs the EXIT trap — one cleanup path, and an
# interrupted run reports the conventional 128+n status instead of carrying on (the
# signal traps set DONE so the abort guard leaves that status alone). The EXIT trap is
# also the abort guard: unless lc_summary ran, the harness exits 1 and says so.
trap 'rm -rf "$SANDBOX"; if [ -z "${DONE-}" ]; then printf "%s\n" "lesson-check.test.sh: aborted before summary" >&2; exit 1; fi' EXIT
trap 'DONE=signal; exit 130' INT
trap 'DONE=signal; exit 143' TERM

. "$PARTIALS/lesson-check.sh"

# ===========================================================================
# Fixture builders
# ===========================================================================
# Credential-shaped values are assembled at run time so this file never holds a
# token-shaped literal for a scanner (or the BR-13 chain itself) to trip on.
T36=abcdefghijklmnopqrstuvwxyz0123456789
GHP="ghp""_$T36"
ASIA="AS""IA""ABCDEFGHIJKLMNOP"
AKIA="AK""IA""ABCDEFGHIJKLMNOP"
SKKEY="sk""-ABCDEFGHIJKLMNOPQRSTUVWX"
SK19="sk""-ABCDEFGHIJKLMNOPQRS"
BEARER="Bear""er abcdefghijklmnopqrstuvwxyz"
APIKEY="FOO_API""_KEY=xxxxxxxx"
PASSWD="DB_PASS""WORD=hunter22hunter"
GHPAT="github""_pat_11ABCDEFG0123456789abcdefghij"
XOXB="xo""xb-1234567890-abcdefghij"
AIZA="AI""za""SyA1234567890abcdefghijklmnopqrstuv"
JWT="ey""JhbGciOiJIUzI1NiJ9.ey""JzdWIiOiIxMjM0In0.c2ln"
PEM="-----BEGIN RSA PRIV""ATE KEY-----"
SK20="sk""-ABCDEFGHIJKLMNOPQRST"
BEARER19="Bear""er abcdefghijklmnopqrs"
GHO="gh""o_$T36"
GHS="gh""s_$T36"
ABIA="AB""IA""ABCDEFGHIJKLMNOP"
XOXP="xo""xp-1234567890-abcdefghij"
GHTOKEN="GITHUB_TO""KEN=xxxxxxxx"
CLSECRET="CLIENT_SEC""RET=abcdefgh1234"
DBPASSWD="DB_PASS""WD=hunter22hunter"
DBPASSLC="db_pass""word=hunter2hunter2"
APIKEY7="FOO_API""_KEY=xxxxxxx"
COLONTOK="MY_API_TO""KEN: abcdefgh12345"
URLCRED="https://admin"":hunter2""@db.example.net/x"
STRIPE="sk""_live_$T36"
RKTEST="rk""_test_$T36"
GLPAT="glp""at-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
NPMTOK="np""m_$T36"
XAPP="xa""pp-1-A012345678-abcdef"

# AC-3's benign evidence: a repo-relative path:line, /bin/sh, /dev/null and a ~/ path,
# all of which must pass the home-path rule (LESSON-440 — the benign path is a case).
EV_OK='partials/forge.sh:42 — exit 0 under /bin/sh, redirected to /dev/null; see ~/.claude/skills/partials/tests/run.sh'

TITLE_DEFAULT='A fixture lesson about forge exits'
TITLE=$TITLE_DEFAULT
TITLE_LINE=""

BODY_OK='## What Happened

A fixture.

## Lesson

Do the thing the evidence proves.

## Why It Matters

It matters.

## Applies When

When a capture step writes a lesson.'

# six <kind> <evidence> <confidence> [enforcement] [generalizes] [supersedes]
# Prints the six v2 lines; a `-` for kind/evidence/confidence omits that line.
six() {
  if [ "$1" != - ]; then printf 'kind: "%s"\n' "$1"; fi
  if [ "$2" != - ]; then printf 'evidence: "%s"\n' "$2"; fi
  if [ "$3" != - ]; then printf 'confidence: "%s"\n' "$3"; fi
  printf 'enforcement: %s\n' "${4:-none}"
  printf 'generalizes: %s\n' "${5:-[]}"
  printf 'supersedes: %s\n' "${6:-[]}"
}

# fx <stem> — the fixture path. The partial refuses a basename that is not
# LESSON-<digits>-<slug>.md, so every fixture carries one.
fx() { printf '%s\n' "$SANDBOX/LESSON-999-$1.md"; }

# lesson <stem> <six-field block> [body] [preamble] — writes $(fx <stem>). The title
# line is $TITLE_LINE when set, else `title: "$TITLE"`.
lesson() {
  {
    if [ -n "${4-}" ]; then printf '%s\n' "$4"; fi
    printf '%s\n' '---' 'id: LESSON-999'
    if [ -n "$TITLE_LINE" ]; then
      printf '%s\n' "$TITLE_LINE"
    else
      printf 'title: "%s"\n' "$TITLE"
    fi
    printf '%s\n' 'component: "adlc/partials"' 'domain: "adlc"' 'stack: ["bash"]' \
      'concerns: []' 'tags: []' 'req: REQ-646' 'created: 2026-01-01' 'updated: 2026-01-01'
    printf '%s\n' "$2"
    printf '%s\n' '---' ''
    printf '%s\n' "${3-$BODY_OK}"
  } > "$(fx "$1")"
}

# run_check <file> — sets RC, OUT, ERR
run_check() {
  adlc_lesson_check "$@" >"$SANDBOX/out" 2>"$SANDBOX/err"
  RC=$?
  OUT=$(cat "$SANDBOX/out")
  ERR=$(cat "$SANDBOX/err")
}

flat() { printf '%s' "$1" | tr '\n' '|'; }

# names_field <field> — 0 when a line of $ERR starts with "<field>: "
names_field() {
  printf '%s\n' "$ERR" | awk -v p="$1: " 'index($0, p) == 1 { f = 1 } END { exit (f ? 0 : 1) }'
}

# only_field <field> — 0 when $ERR is non-empty and EVERY line starts with "<field>: ",
# so a fixture cannot pass on the strength of some other, accidental violation.
only_field() {
  [ -n "$ERR" ] || return 1
  printf '%s\n' "$ERR" | awk -v p="$1: " 'index($0, p) != 1 { bad = 1 } END { exit (bad ? 1 : 0) }'
}

# expect_reject <case> <stem> <field> [reason-substring]
expect_reject() {
  run_check "$(fx "$2")"
  if [ "$RC" = 1 ] && [ -z "$OUT" ] && only_field "$3" \
     && { [ -z "${4-}" ] || printf '%s\n' "$ERR" | grep -qF -- "$4"; }; then
    pass "$1: rc 1, stderr names '$3' and nothing else ($(flat "$ERR"))"
  else
    fail "$1: expected rc 1, only '$3: ' lines on stderr${4:+ mentioning '$4'}, empty stdout; got rc $RC, stderr '$(flat "$ERR")', stdout '$(flat "$OUT")'"
  fi
}

# expect_accept <case> <stem> <what>
expect_accept() {
  if accepts "$2"; then
    pass "$1: rc 0, both streams empty — $3"
  else
    fail "$1: expected rc 0 with empty stdout/stderr ($3); got rc $RC, stderr '$(flat "$ERR")', stdout '$(flat "$OUT")'"
  fi
}

# expect_usage <case> <file> <stderr-substring> — rc 2, empty stdout, the substring on
# stderr, and never the sandbox directory (messages name the basename only).
expect_usage() {
  run_check "$2"
  if [ "$RC" = 2 ] && [ -z "$OUT" ] && printf '%s\n' "$ERR" | grep -qF -- "$3" \
     && ! printf '%s\n' "$ERR" | grep -qF -- "$SANDBOX"; then
    pass "$1: rc 2 with '$3' on stderr, basename only"
  else
    fail "$1: expected rc 2 with '$3' on stderr and no sandbox path; got rc $RC, stderr '$(flat "$ERR")', stdout '$(flat "$OUT")'"
  fi
}

# accepts <stem> — 0 when the file passes cleanly (rc 0, nothing on either stream)
accepts() {
  run_check "$(fx "$1")"
  [ "$RC" = 0 ] && [ -z "$OUT" ] && [ -z "$ERR" ]
}

# rejects_field <stem> <field> — 0 when rc is 1 and only <field> is named
rejects_field() {
  run_check "$(fx "$1")"
  [ "$RC" = 1 ] && [ -z "$OUT" ] && only_field "$2"
}

# ev_accept <case> <evidence> / ev_reject <case> <evidence> <reason> — one-field probes
# on evidence, every other field well-formed. The case name is the fixture stem.
ev_accept() {
  lesson "$1" "$(six process "$2" high)"
  expect_accept "$1" "$1" "evidence '$2'"
}
ev_reject() {
  lesson "$1" "$(six process "$2" high)"
  expect_reject "$1" "$1" evidence "$3"
}

# enf_accept / enf_reject <case> <enforcement> [reason] — one-field probes on enforcement
enf_accept() {
  lesson "$1" "$(six process "$EV_OK" high "$2")"
  expect_accept "$1" "$1" "enforcement '$2'"
}
enf_reject() {
  lesson "$1" "$(six process "$EV_OK" high "$2")"
  expect_reject "$1" "$1" enforcement "${3-}"
}

# ===========================================================================
# 1. The benign path (AC-3, BR-12, BR-13)
# ===========================================================================
lesson wf "$(six process "$EV_OK" high)"
if accepts wf; then
  pass "well_formed_passes: rc 0, stdout and stderr empty"
else
  fail "well_formed_passes: expected rc 0 with empty stdout/stderr; got rc $RC, stderr '$(flat "$ERR")', stdout '$(flat "$OUT")'"
fi
# >>> meta-cut — harness_aborts_without_summary runs this file up to here, no further

# ===========================================================================
# 2. Required fields and enums (BR-3, AC-3)
# ===========================================================================
lesson noev "$(six process - high)"
expect_reject missing_evidence_rejected noev evidence "missing"

lesson emptyev "$(six process '' high)"
expect_reject empty_evidence_rejected emptyev evidence "empty"

lesson nocite "$(six process 'we should be careful' high)"
expect_reject evidence_without_citation_token_rejected nocite evidence "no citation token"

lesson maybe "$(six process "$EV_OK" maybe)"
expect_reject confidence_maybe_rejected maybe confidence

lesson noconf "$(six process "$EV_OK" -)"
expect_reject missing_confidence_rejected noconf confidence "missing"

lesson emptyconf "$(six process "$EV_OK" '')"
expect_reject empty_confidence_rejected emptyconf confidence "empty"

lesson conflow "$(six process "$EV_OK" low)"
expect_accept confidence_low_accepted conflow "confidence: low"

lesson nokind "$(six - "$EV_OK" high)"
expect_reject missing_kind_rejected nokind kind "missing"

lesson kindfoo "$(six foo "$EV_OK" high)"
expect_reject kind_foo_rejected kindfoo kind "process or domain"

lesson badsup "$(six process "$EV_OK" high none '[]' '[LESSON-7]')"
expect_reject bad_supersedes_id_rejected badsup supersedes

lesson badgen "$(six process "$EV_OK" high none '[LESSON-404, BUG-249]')"
expect_reject generalizes_bad_entry_rejected badgen generalizes

lesson sqlist "$(six process "$EV_OK" high none "['LESSON-404']" '["LESSON-140", '"'LESSON-019'"']')"
expect_accept single_quoted_list_entry_accepted sqlist "['LESSON-404'] and a mixed-quote list read as lists of ids"

lesson qscalar "$(six process "$EV_OK" high none '[]' '"[LESSON-404]"')"
expect_reject quoted_scalar_list_rejected qscalar supersedes "not a list"

lesson badenf "$(six process "$EV_OK" high maybe-later)"
lesson goodenf "$(six process "$EV_OK" high '"lint:lesson-check-order"')"
if rejects_field badenf enforcement && accepts goodenf; then
  pass "enforcement_bad_pattern_rejected: 'maybe-later' rejected naming enforcement; quoted lint:<check-id> accepted"
else
  fail "enforcement_bad_pattern_rejected: last run rc $RC, stderr '$(flat "$ERR")'"
fi

enf_accept enforcement_script_path_accepted 'script:tools/x.sh'
enf_accept enforcement_test_path_accepted 'test:partials/tests/lesson-check.test.sh'
enf_accept enforcement_hook_accepted 'hook:pre-commit'
enf_reject enforcement_none_extra_rejected 'none extra' "must be none"
enf_reject enforcement_xlint_rejected 'xlint:foo' "must be none"
enf_reject enforcement_empty_lint_rejected 'lint:' "must be none"
enf_reject enforcement_absolute_test_path_rejected 'test:/Users/x.sh' "repo-relative"
enf_reject enforcement_parent_segment_rejected 'script:../x.sh' "repo-relative"
enf_reject enforcement_inner_parent_segment_rejected 'test:tools/../../x.sh' "repo-relative"
# Absolute paths outside any home directory, so only the repo-relative rule can fire.
enf_reject enforcement_etc_test_path_rejected 'test:/etc/x.sh' "no leading /"
enf_reject enforcement_opt_script_path_rejected 'script:/opt/x.sh' "no leading /"
enf_reject enforcement_trailing_parent_segment_rejected 'test:a/..' "no .. segment"
enf_reject enforcement_bare_parent_segment_rejected 'script:..' "no .. segment"

# List entries: the id is 3-6 digits inside a list too, and a single-quoted list is a
# string, like a double-quoted one.
lesson listbig "$(six process "$EV_OK" high none '[]' '[LESSON-1000000]')"
expect_reject list_lesson_1000000_rejected listbig supersedes "LESSON-nnn id"
lesson listsmall "$(six process "$EV_OK" high none '[LESSON-404, LESSON-99]')"
expect_reject list_lesson_99_rejected listsmall generalizes "LESSON-nnn id"
lesson sqscalar "$(six process "$EV_OK" high none '[]' "'[LESSON-404]'")"
expect_reject single_quoted_scalar_list_rejected sqscalar supersedes "not a list"

# evidence == title, after one quote layer is stripped from BOTH (title double-quoted,
# evidence single-quoted) — the citation token is present, so only this rule can fire.
TITLE='BUG-249 close-out skipped Step 8b'
lesson eqtitle "kind: \"process\"
evidence: 'BUG-249 close-out skipped Step 8b'
confidence: \"high\"
enforcement: none
generalizes: []
supersedes: []"
TITLE=$TITLE_DEFAULT
expect_reject evidence_equals_title_rejected eqtitle evidence "repeats the title"

# ===========================================================================
# 3. Home paths (BR-12) and credential shapes (BR-13)
# ===========================================================================
lesson homemac "$(six process 'BUG-249 repro at /Users/x/repo/file.sh' high)"
expect_reject home_path_rejected homemac evidence "home-directory path"

lesson homelinux "$(six process 'BUG-249 repro at /home/x/repo/file.sh' high)"
expect_reject home_path_linux_rejected homelinux evidence "home-directory path"

# The rest of the prefix family, the delimiters, and the look-alikes that must pass.
HOME_BAD=""
home_one() { # home_one <stem> <evidence> <reject|accept>
  lesson "$1" "$(six process "$2" high)"
  if [ "$3" = reject ]; then
    rejects_field "$1" evidence || HOME_BAD="$HOME_BAD [$1 not rejected: $(flat "$ERR")]"
  else
    accepts "$1" || HOME_BAD="$HOME_BAD [$1 not accepted: $(flat "$ERR")]"
  fi
}
home_one hdollar  'BUG-249 see $HOME/repo/x.sh' reject
home_one htilde   'BUG-249 see ~bob/repo/x.sh' reject
home_one hroot    'BUG-249 see /root/x.sh' reject
home_one hparen   'BUG-249 see (/Users/y/z.sh)' reject
home_one hbtick   'BUG-249 see `/home/y/z.sh`' reject
home_one hbenign  'BUG-249 see ~/Library/Logs/x.log, /tmp/adlc-x, https://example.com/a/b and /dev/null' accept
if [ -z "$HOME_BAD" ]; then
  pass "home_path_prefix_family: \$HOME/, ~name/, /root/, parenthesised and backticked prefixes rejected; ~/, /tmp, https:// and /dev/null accepted"
else
  fail "home_path_prefix_family:$HOME_BAD"
fi

# The delimiter shapes a whitespace tokenizer let through: the prefix is glued to an
# `=`, a bracket, a URL scheme, a flag, a comma, or spelled with braces.
ev_reject home_path_assignment_rejected 'BUG-249 ran with path=/Users/x/repo' "home-directory path"
ev_reject home_path_bracketed_rejected 'BUG-249 see [/Users/x/repo]' "home-directory path"
ev_reject home_path_file_url_rejected 'BUG-249 opened file:///Users/x/repo' "home-directory path"
ev_reject home_path_flag_value_rejected 'BUG-249 ran --dir=/home/x/repo' "home-directory path"
ev_reject home_path_after_comma_rejected 'BUG-249 paths a,/root/x' "home-directory path"
ev_reject home_path_braced_home_rejected 'BUG-249 see ${HOME}/x' "home-directory path"
ev_reject home_path_tilde_user_rejected 'BUG-249 see ~bob/x' "home-directory path"

# The look-alikes, one per case (LESSON-440 — the benign path is a case).
ev_accept home_lookalike_url_accepted 'BUG-249 see https://host/home/x'
ev_accept home_lookalike_tmp_accepted 'BUG-249 see /tmp/home/x'
ev_accept home_lookalike_dev_null_accepted 'BUG-249 redirected to /dev/null'
ev_accept home_lookalike_bin_sh_accepted 'BUG-249 under /bin/sh'
ev_accept home_lookalike_tilde_slash_accepted 'BUG-249 see ~/.claude/x'
ev_accept home_lookalike_repo_relative_accepted 'partials/forge.sh:42 exits 0'

# /Users/ needs no left delimiter and matches in any case: a mounted volume's Users
# directory, a prefix glued to `.-`, an upper-case spelling. `/tmp//home/x` is caught
# because the second `/` is a delimiter — fail-closed, by design.
ev_reject home_path_volumes_users_rejected 'BUG-249 see /Volumes/Macintosh HD/Users/bob/x' "home-directory path"
ev_reject home_path_after_dot_dash_rejected 'BUG-249 see x.-/Users/bob/x' "home-directory path"
ev_reject home_path_users_any_case_rejected 'BUG-249 see /USERS/bob/x' "home-directory path"
ev_reject home_path_double_slash_home_rejected 'BUG-249 see /tmp//home/x' "home-directory path"
ev_reject home_path_var_root_rejected 'BUG-249 see /var/root/x' "home-directory path"
lesson homeqhome "kind: process
evidence: 'BUG-249 see \"\$HOME\"/x'
confidence: high"
expect_reject home_path_quoted_home_rejected homeqhome evidence "home-directory path"
lesson homewin "kind: process
evidence: BUG-249 see C:\\Users\\bob\\x
confidence: high"
if grep -qF 'C:\Users\bob' "$(fx homewin)"; then
  expect_reject home_path_windows_users_rejected homewin evidence "home-directory path"
else
  fail "home_path_windows_users_rejected: fixture lost its backslashes — the case would test nothing"
fi

# The comment on enforcement is scanned too, and so is every other frontmatter line:
# an unknown key, and a `#` line that sets no key (named `frontmatter`).
enf_reject home_path_enforcement_comment_rejected 'none   # /Users/bob/x' "home-directory path"
lesson homeunknown "$(six process "$EV_OK" high)
notes: /home/bob/scratch.md"
expect_reject home_path_in_unknown_key_rejected homeunknown notes "home-directory path"
lesson homefmcom "$(six process "$EV_OK" high)
# drafted from /Users/bob/notes.md"
expect_reject home_path_in_frontmatter_comment_rejected homefmcom frontmatter "home-directory path"

# The rules read the line as written: behind a trailing ` #` comment is still committed.
lesson homecom "kind: process
evidence: \"BUG-249 the fix held\"   # repro lived at /Users/bob/repo
confidence: high"
expect_reject home_path_behind_comment_rejected homecom evidence "home-directory path"

lesson credcom "kind: process
evidence: BUG-249 the fix held   # $APIKEY
confidence: high"
expect_reject credential_behind_comment_rejected credcom evidence "credential-shaped"

lesson ghp "$(six process "BUG-249 leaked $GHP in the log" high)"
expect_reject credential_ghp_rejected ghp evidence "credential-shaped"

lesson asia "$(six process "BUG-249 leaked $ASIA in the log" high)"
expect_reject credential_asia_rejected asia evidence "credential-shaped"

# One case per arm of the chain.
ev_reject credential_akia_rejected "BUG-249 leaked $AKIA in the log" "credential-shaped"
ev_reject credential_bearer_rejected "BUG-249 sent $BEARER upstream" "credential-shaped"
ev_reject credential_api_key_assignment_rejected "BUG-249 ran with $APIKEY set" "credential-shaped"
ev_reject credential_password_assignment_rejected "BUG-249 ran with $PASSWD set" "credential-shaped"
ev_reject credential_github_pat_rejected "BUG-249 leaked $GHPAT in the log" "credential-shaped"
ev_reject credential_slack_token_rejected "BUG-249 leaked $XOXB in the log" "credential-shaped"
ev_reject credential_google_key_rejected "BUG-249 leaked $AIZA in the log" "credential-shaped"
ev_reject credential_jwt_rejected "BUG-249 leaked $JWT in the log" "credential-shaped"
ev_reject credential_pem_rejected "BUG-249 pasted $PEM into the log" "credential-shaped"

# The benign side: a short sk- prefix, and prose that names a token variable.
ev_accept credential_sk_19_chars_passes "BUG-249 the prefix $SK19 was truncated"
lesson tokprose "$(six process 'GITHUB_TOKEN: was unset in CI (BUG-123)' high)"
lesson tokproseu "kind: process
evidence: GITHUB_TOKEN: was unset in CI (BUG-123)
confidence: high"
if accepts tokprose && accepts tokproseu; then
  pass "credential_token_prose_passes: 'GITHUB_TOKEN: was unset in CI (BUG-123)' accepted quoted and unquoted"
else
  fail "credential_token_prose_passes: got rc $RC, stderr '$(flat "$ERR")'"
fi

# BR-13 covers every validated field, not only evidence: hook:<name> admits the
# token's characters, so only the credential rule can fire here.
lesson credenf "$(six process "$EV_OK" high "hook:$SKKEY")"
expect_reject credential_in_other_field_rejected credenf enforcement "credential-shaped"

TITLE="BUG-249 leaked $GHP"
lesson credtitle "$(six process "$EV_OK" high)"
TITLE=$TITLE_DEFAULT
expect_reject credential_in_title_rejected credtitle title "credential-shaped"

# The remaining validated fields: the token rides in a trailing `# <secret>` comment,
# which the value parse drops, so only the credential rule can fire on that field.
for cf in kind confidence generalizes supersedes; do
  lesson "credf$cf" "$(six process "$EV_OK" high | sed "s/^$cf: .*/&   # $GHP/")"
  expect_reject "credential_in_${cf}_rejected" "credf$cf" "$cf" "credential-shaped"
done

# Every frontmatter line is scanned: an unknown key is named by its own key, a line
# that sets no key as `frontmatter`.
lesson credunknown "$(six process "$EV_OK" high)
notes: \"see the log\"   # $GHP"
expect_reject credential_in_unknown_key_rejected credunknown notes "credential-shaped"
lesson credfmcom "$(six process "$EV_OK" high)
# $XOXP"
expect_reject credential_in_frontmatter_comment_rejected credfmcom frontmatter "credential-shaped"

# The widened arms, each pinned, and their benign edges.
ev_reject credential_sk_20_rejected "BUG-249 leaked $SK20 in the log" "credential-shaped"
ev_reject credential_gho_rejected "BUG-249 leaked $GHO in the log" "credential-shaped"
ev_reject credential_ghs_rejected "BUG-249 leaked $GHS in the log" "credential-shaped"
ev_reject credential_abia_rejected "BUG-249 leaked $ABIA in the log" "credential-shaped"
ev_reject credential_xoxp_rejected "BUG-249 leaked $XOXP in the log" "credential-shaped"
ev_reject credential_github_token_assignment_rejected "BUG-249 ran with $GHTOKEN set" "credential-shaped"
ev_reject credential_client_secret_rejected "BUG-249 ran with $CLSECRET set" "credential-shaped"
ev_reject credential_db_passwd_rejected "BUG-249 ran with $DBPASSWD set" "credential-shaped"
ev_reject credential_lowercase_password_rejected "BUG-249 ran with $DBPASSLC set" "credential-shaped"
ev_reject credential_url_userinfo_rejected "BUG-249 connected to $URLCRED" "credential-shaped"
ev_reject credential_stripe_live_rejected "BUG-249 leaked $STRIPE in the log" "credential-shaped"
ev_reject credential_stripe_restricted_test_rejected "BUG-249 leaked $RKTEST in the log" "credential-shaped"
ev_reject credential_gitlab_pat_rejected "BUG-249 leaked $GLPAT in the log" "credential-shaped"
ev_reject credential_npm_token_rejected "BUG-249 leaked $NPMTOK in the log" "credential-shaped"
ev_reject credential_slack_app_token_rejected "BUG-249 leaked $XAPP in the log" "credential-shaped"
ev_accept credential_api_key_7_chars_accepted "BUG-249 ran with $APIKEY7 set"
ev_accept credential_bearer_19_accepted "BUG-249 sent $BEARER19 upstream"
# The `=`-only assignment arm is deliberate (narrower than REQ-415's `[=:]`): prose
# that names a variable and a value with `: ` is not read as an assignment.
ev_accept credential_colon_assignment_accepted "BUG-249 $COLONTOK"

# ===========================================================================
# 4. Body sections (BR-3, BR-5) — the field is the heading: `## Applies When: ...`
# ===========================================================================
lesson noaw "$(six process "$EV_OK" high)" '## What Happened

A fixture.

## Lesson

Do the thing the evidence proves.'
expect_reject missing_applies_when_rejected noaw '## Applies When' "section missing"

lesson nolesson "$(six process "$EV_OK" high)" '## What Happened

A fixture.

## Applies When

When a capture step writes a lesson.'
expect_reject missing_lesson_section_rejected nolesson '## Lesson' "section missing"

lesson emptylesson "$(six process "$EV_OK" high)" '## Lesson

## Why It Matters

It matters.

## Applies When

When a capture step writes a lesson.'
expect_reject empty_section_rejected emptylesson '## Lesson' "empty"

lesson subhead "$(six process "$EV_OK" high)" '## Lesson

### In practice

Do the thing the evidence proves.

## Applies When

When a capture step writes a lesson.'
expect_accept subheading_under_lesson_accepted subhead "a ### heading under ## Lesson is content, not the section's end"

# Built with printf: trailing blanks in this file's source do not survive an editor.
lesson trailblank "$(six process "$EV_OK" high)" \
  "$(printf '## Lesson   \n\nDo the thing the evidence proves.\n\n## Applies When\t\n\nWhen a capture step writes a lesson.')"
if ! grep -q '^## Lesson   $' "$(fx trailblank)" || ! grep -q "^## Applies When$(printf '\t')\$" "$(fx trailblank)"; then
  fail "heading_trailing_blanks_accepted: fixture lost its trailing blanks — the case would test nothing"
else
  expect_accept heading_trailing_blanks_accepted trailblank "headings compared after trailing blanks are stripped"
fi

# A ### heading neither ends the section nor fills it: a ## Lesson holding only one
# is empty.
lesson subonly "$(six process "$EV_OK" high)" '## Lesson

### In practice

## Applies When

When a capture step writes a lesson.'
expect_reject subheading_only_section_is_empty subonly '## Lesson' "empty"

# A line inside a fence is never a heading — not a ``` fence's `## Applies When`, not
# a ~~~ fence's `## Lesson` (which would otherwise open, and fill, the section).
lesson fencedaw "$(six process "$EV_OK" high)" '## Lesson

Do the thing the evidence proves.

```md
## Applies When

Inside a fence, so not the section.
```'
expect_reject backtick_fenced_heading_is_not_a_heading fencedaw '## Applies When' "section missing"

lesson fencedles "$(six process "$EV_OK" high)" '~~~md
## Lesson

Inside a fence, so not the section.
~~~

## Lesson

## Applies When

When a capture step writes a lesson.'
expect_reject tilde_fenced_heading_is_not_a_heading fencedles '## Lesson' "empty"

# Only the first ## Lesson counts: a second one ends the first, which stays empty.
lesson twolesson "$(six process "$EV_OK" high)" '## Lesson

## Lesson

Do the thing the evidence proves.

## Applies When

When a capture step writes a lesson.'
expect_reject only_first_lesson_heading_counts twolesson '## Lesson' "empty"

# A level-1 heading ends the section as a level-2 one does.
lesson h1ends "$(six process "$EV_OK" high)" '## Lesson

# Notes

Text under a level-1 heading.

## Applies When

When a capture step writes a lesson.'
expect_reject level1_heading_ends_section h1ends '## Lesson' "empty"

# ===========================================================================
# 5. Frontmatter location and the usage contract (ADR-1, ADR-2)
# ===========================================================================
lesson htmlc "$(six process "$EV_OK" high)" "$BODY_OK" '<!--
Filename MUST be `LESSON-xxx-slug.md`.
-->'
if accepts htmlc; then
  pass "html_comment_before_frontmatter_passes: a 3-line <!-- --> block above --- is not 'no frontmatter'"
else
  fail "html_comment_before_frontmatter_passes: got rc $RC, stderr '$(flat "$ERR")'"
fi

lesson dashcom "$(six process "$EV_OK" high)" "$BODY_OK" '<!--
---
kind: not-the-frontmatter
---
-->
'
expect_accept dashes_inside_html_comment_ignored dashcom "a --- pair inside the comment above the block is not the block"

{ printf '%s\n' 'A note above the block.' ''; cat "$(fx wf)"; } > "$(fx textfirst)"
expect_usage text_before_frontmatter_is_usage_error_2 "$(fx textfirst)" "lesson-check: no frontmatter block in LESSON-999-textfirst.md"

awk '{ printf "%s\r\n", $0 }' "$(fx htmlc)" > "$(fx crlf)"
expect_accept crlf_file_passes crlf "CRLF line ends (comment-headed file) are normalised"

{ printf '\357\273\277'; cat "$(fx wf)"; } > "$(fx bom)"
expect_accept bom_file_passes bom "a leading UTF-8 BOM is dropped"
# The same file under a UTF-8 locale, macOS Terminal's default. There awk reads the BOM
# as one character, and a byte-wise `\357\273\277` regex no longer matches it; the
# partial runs its awk under LC_ALL=C so the strip stays byte-exact. A locale counts
# only when a bare awk in it really fails that strip (the defect this guards against
# is live there); with none available the regression is reported as not run, never as
# a pass. LC_ALL is set in this shell, not a subshell, so the case is counted, then
# put back.
UTF8_LOCALE=''
for l in en_US.UTF-8 C.UTF-8 en_US.utf8 C.utf8; do
  if [ "$(printf '\357\273\277x\n' | LC_ALL=$l awk '{ print sub(/^\357\273\277/, "") }' 2>/dev/null)" = 0 ]; then UTF8_LOCALE=$l; break; fi
done
if [ -n "$UTF8_LOCALE" ]; then
  _lc_set=${LC_ALL+x}; _lc_was=${LC_ALL-}
  LC_ALL=$UTF8_LOCALE; export LC_ALL
  expect_accept bom_file_passes_utf8_locale bom "a leading UTF-8 BOM is dropped under LC_ALL=$UTF8_LOCALE too"
  if [ -n "$_lc_set" ]; then LC_ALL=$_lc_was; export LC_ALL; else unset LC_ALL; fi
else
  echo "NOTE: no UTF-8 locale in which awk is multibyte; bom_file_passes_utf8_locale not run"
fi

printf '%s\n' "$BODY_OK" > "$(fx nofm)"
printf '%s\n' '---' 'id: LESSON-999' 'kind: "process"' '' "$BODY_OK" > "$(fx unclosed)"
run_check "$(fx nofm)"
nofm_ok=0
if [ "$RC" = 2 ] && [ -z "$OUT" ] \
   && printf '%s\n' "$ERR" | grep -qF "lesson-check: no frontmatter block in LESSON-999-nofm.md" \
   && ! printf '%s\n' "$ERR" | grep -qF "$SANDBOX"; then
  nofm_ok=1
fi
nofm_err=$ERR
run_check "$(fx unclosed)"
if [ "$nofm_ok" = 1 ] && [ "$RC" = 2 ] && [ -z "$OUT" ]; then
  pass "no_frontmatter_is_usage_error_2: no block and an unclosed block both rc 2 with the 'no frontmatter block' line, basename only"
else
  fail "no_frontmatter_is_usage_error_2: no-block stderr '$(flat "$nofm_err")'; unclosed rc $RC, stderr '$(flat "$ERR")'"
fi

run_check
if [ "$RC" = 2 ] && [ -z "$OUT" ] && printf '%s\n' "$ERR" | grep -qF 'lesson-check: usage:'; then
  pass "missing_argument_is_usage_error_2: rc 2 with the usage line"
else
  fail "missing_argument_is_usage_error_2: got rc $RC, stderr '$(flat "$ERR")'"
fi

expect_usage unreadable_file_is_usage_error_2 "$(fx does-not-exist)" 'lesson-check: cannot read LESSON-999-does-not-exist.md'

ln -s "$(fx wf)" "$(fx link)"
expect_usage symlink_is_usage_error_2 "$(fx link)" 'lesson-check: refusing a symlink: LESSON-999-link.md'

BASENAME_BAD=""
for bn in notes.md LESSON-abc-x.md LESSON-999.md LESSON-999-x.txt; do
  cp "$(fx wf)" "$SANDBOX/$bn"
  run_check "$SANDBOX/$bn"
  if ! { [ "$RC" = 2 ] && printf '%s\n' "$ERR" | grep -qF "not a lesson file name"; }; then
    BASENAME_BAD="$BASENAME_BAD [$bn: rc $RC, $(flat "$ERR")]"
  fi
done
if [ -z "$BASENAME_BAD" ]; then
  pass "bad_basename_is_usage_error_2: notes.md, LESSON-abc-x.md, LESSON-999.md and a .txt all rc 2"
else
  fail "bad_basename_is_usage_error_2:$BASENAME_BAD"
fi

# The id segment is 3+ digits and nothing else, and the whole name holds only
# A-Z a-z 0-9 . _ - (checked bytewise under LC_ALL=C). The control — a long id and a
# slug using every allowed punctuation mark — passes.
BN_BAD=""
EACUTE=$(printf '\303\251')
for bn in 'LESSON-12-x.md' 'LESSON-123a-x.md' 'LESSON-999-a b.md' 'LESSON-999-x$y.md' \
          'LESSON-999-x:y.md' "LESSON-999-caf$EACUTE.md"; do
  cp "$(fx wf)" "$SANDBOX/$bn"
  run_check "$SANDBOX/$bn"
  if ! { [ "$RC" = 2 ] && printf '%s\n' "$ERR" | grep -qF "not a lesson file name"; }; then
    BN_BAD="$BN_BAD [$bn: rc $RC, $(flat "$ERR")]"
  fi
done
cp "$(fx wf)" "$SANDBOX/LESSON-1234-a.b_c-d.md"
run_check "$SANDBOX/LESSON-1234-a.b_c-d.md"
[ "$RC" = 0 ] && [ -z "$ERR" ] || BN_BAD="$BN_BAD [control LESSON-1234-a.b_c-d.md: rc $RC, $(flat "$ERR")]"
if [ -z "$BN_BAD" ]; then
  pass "basename_id_digits_and_charset_enforced: 2-digit id, non-digit id, blank, \$, colon and non-ASCII names rc 2; LESSON-1234-a.b_c-d.md rc 0"
else
  fail "basename_id_digits_and_charset_enforced:$BN_BAD"
fi

# A crafted file name cannot forge a `<field>: <reason>` line: the newline in it is
# shown as `?`, and the message stays one line. (The name is refused before the file is
# read — a newline is outside the basename charset.)
NLNAME=$(printf 'LESSON-999-a\nevidence: forged.md')
printf '%s\n' "$BODY_OK" > "$SANDBOX/$NLNAME"
run_check "$SANDBOX/$NLNAME"
nl_lines=$(printf '%s\n' "$ERR" | grep -c .)
if [ "$RC" = 2 ] && [ "$nl_lines" = 1 ] \
   && printf '%s\n' "$ERR" | grep -q '^lesson-check: ' \
   && printf '%s\n' "$ERR" | grep -qF 'LESSON-999-a?evidence: forged.md'; then
  pass "stderr_names_file_by_sanitized_basename: a newline in the name prints as '?' on one line"
else
  fail "stderr_names_file_by_sanitized_basename: got rc $RC, $nl_lines line(s): '$(flat "$ERR")'"
fi

# `k=v/LESSON-...` as an awk operand is an assignment, and awk would read stdin
# instead of the file; the partial feeds awk on stdin, so the path is only ever a path.
mkdir "$SANDBOX/k=v"
cp "$(fx wf)" "$SANDBOX/k=v/LESSON-999-awk.md"
(cd "$SANDBOX" && adlc_lesson_check 'k=v/LESSON-999-awk.md') </dev/null >"$SANDBOX/out" 2>"$SANDBOX/err"
RC=$?
ERR=$(cat "$SANDBOX/err")
if [ "$RC" = 0 ] && [ -z "$ERR" ]; then
  pass "awk_assignment_shaped_path_read_as_file: k=v/LESSON-999-awk.md is rc 0"
else
  fail "awk_assignment_shaped_path_read_as_file: got rc $RC, stderr '$(flat "$ERR")'"
fi

# A `set -e` caller survives the check: an absent optional key makes `grep -c` exit 1,
# and that must not kill the caller before the verdict.
lesson seteok "kind: process
evidence: \"$EV_OK\"
confidence: high"
lesson setebad "kind: process
evidence: \"$EV_OK\""
sete_ok=$( (set -e; adlc_lesson_check "$(fx seteok)"; echo reached) 2>&1 )
sete_bad=$( (set -e; adlc_lesson_check "$(fx setebad)"; echo reached) 2>&1 )
sete_rc=$?
if [ "$sete_ok" = reached ] && [ "$sete_rc" = 1 ] \
   && printf '%s\n' "$sete_bad" | grep -q '^confidence: missing' \
   && ! printf '%s\n' "$sete_bad" | grep -q reached; then
  pass "set_e_caller_survives_absent_keys: rc 0 reaches the next line; rc 1 reports its violation, then stops the caller"
else
  fail "set_e_caller_survives_absent_keys: pass-path output '$(flat "$sete_ok")'; fail-path rc $sete_rc, output '$(flat "$sete_bad")'"
fi

# ===========================================================================
# 6. Keys: one line each, matched as `<key>:` + blank, parse errors named
# ===========================================================================
for dk in title kind evidence confidence enforcement generalizes supersedes; do
  case "$dk" in
    title) dl='title: "A second title"' ;;
    kind) dl='kind: "domain"' ;;
    evidence) dl='evidence: "BUG-250 another moment"' ;;
    confidence) dl='confidence: low' ;;
    enforcement) dl='enforcement: none' ;;
    generalizes) dl='generalizes: []' ;;
    *) dl='supersedes: []' ;;
  esac
  lesson "dup$dk" "$(six process "$EV_OK" high)
$dl"
  expect_reject "duplicate_${dk}_rejected" "dup$dk" "$dk" "key appears 2 times"
done

# The second copy wraps onto the next line: still one violation, the duplicate.
lesson dupmulti "$(six process "$EV_OK" high)
supersedes:
  - LESSON-404"
expect_reject duplicate_key_multiline_value_rejected dupmulti supersedes "key appears 2 times"

# Fail closed on spelling: a validated key written without the blank after its colon
# is rejected on that key with one line naming the spelling — never read as absent and
# passed over (as `supersedes:[LESSON-7]` beside a real supersedes once was).
SPELL_KIND='kind: must be written as "kind:" followed by a blank'
SPELL_SUP='supersedes: must be written as "supersedes:" followed by a blank'
lesson nospace "$(six - "$EV_OK" high)
kind:process"
lesson nospacesup "$(six process "$EV_OK" high)
supersedes:[LESSON-7]"
run_check "$(fx nospace)"
ns_kind_rc=$RC ns_kind_err=$ERR
run_check "$(fx nospacesup)"
if [ "$ns_kind_rc" = 1 ] && [ "$ns_kind_err" = "$SPELL_KIND" ] \
   && [ "$RC" = 1 ] && [ "$ERR" = "$SPELL_SUP" ]; then
  pass "key_needs_blank_after_colon: 'kind:process' and a second 'supersedes:[LESSON-7]' each rejected with exactly the spelling line"
else
  fail "key_needs_blank_after_colon: kind:process rc $ns_kind_rc '$(flat "$ns_kind_err")'; supersedes:[LESSON-7] rc $RC '$(flat "$ERR")'"
fi

lesson spsup "$(six process "$EV_OK" high | grep -v '^supersedes:')
supersedes:[LESSON-034]"
expect_reject key_spelling_no_blank_rejected spsup supersedes "$SPELL_SUP"

lesson spspace "$(six process - high)
evidence : BUG-249 the fix held"
expect_reject key_spelling_blank_before_colon_rejected spspace evidence 'must be written as "evidence:" followed by a blank'

lesson spquote "$(six process - high)
\"evidence\": BUG-249 the fix held"
expect_reject key_spelling_double_quoted_key_rejected spquote evidence 'must be written as "evidence:" followed by a blank'

lesson spsquote "$(six process "$EV_OK" - )
'confidence': high"
expect_reject key_spelling_single_quoted_key_rejected spsquote confidence 'must be written as "confidence:" followed by a blank'

# A flow collection opened and not closed on the key's line continues onto the next,
# even when that next line is a key; a plain line at column 0 continues the value too.
lesson flowopen "$(six process "$EV_OK" high none '[LESSON-404,' '[]')"
lesson flowbrace "$(six process "$EV_OK" high none '{x: LESSON-404' '[]')"
if rejects_field flowopen generalizes && printf '%s\n' "$ERR" | grep -qF 'next line'; then
  if rejects_field flowbrace generalizes && printf '%s\n' "$ERR" | grep -qF 'next line'; then
    pass "flow_collection_unclosed_rejected: '[LESSON-404,' and '{x: LESSON-404' with a key on the next line each rejected naming generalizes"
  else
    fail "flow_collection_unclosed_rejected: '{x: LESSON-404' got rc $RC, stderr '$(flat "$ERR")'"
  fi
else
  fail "flow_collection_unclosed_rejected: '[LESSON-404,' got rc $RC, stderr '$(flat "$ERR")'"
fi

lesson contcol0 "kind: process
evidence: BUG-249 the fix held
in CI after the retry
confidence: high"
expect_reject continuation_plain_line_rejected contcol0 evidence "next line"

lesson dashcol0 "kind: process
evidence: \"$EV_OK\"
confidence: high
supersedes:
- LESSON-404"
expect_reject list_item_column0_continuation_rejected dashcol0 supersedes "next line"

# The false positive this rule once had: an indented `# note` under a key is a comment.
lesson indcom "$(six process "$EV_OK" high)
  # a note the drafter left under supersedes"
expect_accept indented_comment_is_not_continuation indcom "an indented # line after a key is a comment, not a continuation"

TITLE_LINE='title: "An unclosed title'
lesson titleq "$(six process "$EV_OK" high)"
TITLE_LINE=""
expect_reject title_parse_error_rejected titleq title "never closed"

# ===========================================================================
# 7. Citation-token boundaries (ADR-3 — explicit delimiters, never a word boundary)
# ===========================================================================
# `latest_build` is the left-delimiter probe: `test_` sits inside a word there, so only
# the explicit `(^|[^A-Za-z0-9_])` class keeps it from reading as a test name.
lesson latest "$(six process 'the latest build' high)"
lesson latestu "$(six process 'the latest_build flag' high)"
lesson testname "$(six process 'test_marker_parse fails then passes' high)"
if rejects_field latest evidence && rejects_field latestu evidence; then
  if accepts testname; then
    pass "token_test_does_not_match_latest: 'the latest build' and 'latest_build' rejected; test_marker_parse accepted"
  else
    fail "token_test_does_not_match_latest: test_marker_parse not accepted: '$(flat "$ERR")'"
  fi
else
  fail "token_test_does_not_match_latest: 'the latest build' or 'latest_build' not rejected (rc $RC, stderr '$(flat "$ERR")')"
fi
ev_reject test_word_tests_rejected 'the tests pass' "no citation token"
ev_accept test_name_dot_test_accepted 'foo.test.sh fails then passes'
ev_accept test_name_camel_accepted 'testLoginFails flips'
ev_accept test_name_go_style_accepted 'TestFoo flips'

lesson effaced "$(six process 'the effaced build' high)"
lesson sha "$(six process 'fixed in cb177bc' high)"
if rejects_field effaced evidence; then
  if accepts sha; then
    pass "sha_token_does_not_match_effaced: 'effaced' rejected; cb177bc accepted"
  else
    fail "sha_token_does_not_match_effaced: cb177bc not accepted: '$(flat "$ERR")'"
  fi
else
  fail "sha_token_does_not_match_effaced: 'effaced' not rejected (rc $RC, stderr '$(flat "$ERR")')"
fi
ev_reject sha_6_rejected 'fixed in abc123' "no citation token"
ev_accept sha_7_accepted 'fixed in abc1234'
ev_accept sha_40_accepted 'fixed in 0123456789abcdef0123456789abcdef01234567'
ev_reject sha_41_rejected 'fixed in 0123456789abcdef0123456789abcdef012345678' "no citation token"
ev_reject sha_uppercase_rejected 'fixed in CB177BC' "no citation token"
ev_reject sha_all_digits_rejected 'fixed on 20261026 after 1234567 tries' "no citation token"

ev_reject id_lesson_99_rejected 'see LESSON-99' "no citation token"
ev_accept id_lesson_100_accepted 'see LESSON-100'
ev_accept id_lesson_999999_accepted 'see LESSON-999999'
ev_reject id_lesson_1000000_rejected 'see LESSON-1000000' "no citation token"
ev_reject id_bug_24_rejected 'see BUG-24' "no citation token"
ev_accept id_task_104_accepted 'see TASK-104'
ev_accept id_lesson_404_accepted 'see LESSON-404'

ev_accept path_line_makefile_accepted 'Makefile:12 drops the flag'
ev_accept path_line_extensionless_with_slash_accepted 'tools/run:5 drops the flag'
ev_reject path_line_url_port_not_a_citation 'see https://example.com:8080 for it' "no citation token"
ev_reject path_line_ip_port_not_a_citation 'see 127.0.0.1:8080 for it' "no citation token"
# A bare host:port — no `/`, last part com|org|net|io|dev — is an authority, not a file.
ev_reject path_line_domain_port_not_a_citation 'see example.com:8080 for it' "no citation token"
# Glued on the left, an id or a test token is part of a longer word.
ev_reject id_glued_prefix_not_a_citation 'see xBUG-249 for it' "no citation token"
ev_reject test_token_inside_word_not_a_citation 'my_test_foo fails then passes' "no citation token"
ev_reject sha_mixed_case_rejected 'fixed in cB177bc' "no citation token"

# ===========================================================================
# 8. The stderr contract: one line per violation, field first (ADR-1)
# ===========================================================================
lesson twobad "$(six - "$EV_OK" maybe)"
run_check "$(fx twobad)"
lines=$(printf '%s\n' "$ERR" | grep -c .)
if [ "$RC" = 1 ] && [ -z "$OUT" ] && [ "$lines" = 2 ] && names_field kind && names_field confidence; then
  pass "stderr_names_each_field: two violations -> two lines, one starting 'kind: ', one 'confidence: '"
else
  fail "stderr_names_each_field: got rc $RC, $lines line(s): '$(flat "$ERR")'"
fi

# ===========================================================================
# 9. Value parsing: quotes, trailing comments, and values a YAML reader would drop
# ===========================================================================
lesson parsed "kind: 'domain'
evidence: \"REQ-646 BR-3 — a quoted \\\"value\\\" with an escape\" # trailing comment
confidence: medium   # contrast observed, mechanism inferred
enforcement: \"test:partials/tests/lesson-check.test.sh\"
generalizes: [\"LESSON-404\"]   # the shape the template invites
supersedes: []"
if accepts parsed; then
  pass "quoted_and_commented_values_parse: single/double quotes, an escaped quote and trailing # comments all parse"
else
  fail "quoted_and_commented_values_parse: got rc $RC, stderr '$(flat "$ERR")'"
fi

lesson unterm "kind: \"process\"
evidence: \"BUG-249 never closed
confidence: \"high\""
expect_reject unterminated_quote_rejected unterm evidence "never closed"

# Q3: an unquoted `: ` is read, not rejected — the value up to a ` #` is the value.
lesson colon "kind: \"process\"
evidence: BUG-249: the close-out skipped Step 8b
confidence: \"high\""
expect_accept unquoted_colon_space_accepted colon "an unquoted value holding ': ' is read whole"

lesson wrapped "kind: \"process\"
evidence: \"$EV_OK\"
confidence: \"high\"
supersedes:
  - LESSON-404"
expect_reject wrapped_value_rejected wrapped supersedes "next line"

lesson sqopen "kind: process
evidence: 'BUG-249 never closed
confidence: high"
expect_reject unclosed_single_quote_rejected sqopen evidence "single quote is never closed"

# The citation sits after the `''`, so a parse that stopped at it would find none.
lesson sqesc "kind: process
evidence: 'it''s fixed in BUG-249'
confidence: high"
expect_accept single_quote_escape_accepted sqesc "'' inside single quotes is one quote, and the value runs on"

# The citation sits after the `#`, so a parse that read it as a comment would find none.
lesson hashtext "kind: process
evidence: see#BUG-249 for the repro
confidence: high"
expect_accept hash_without_blank_is_text hashtext "a # with no blank before it is part of the value"

# ===========================================================================
# 10. The template and taxonomy (TASK-104: BR-1, AC-1, AC-2)
# ===========================================================================
TPL="$ROOT/templates/lesson-template.md"
TAX="$ROOT/templates/taxonomy-template.md"
SIX_KEYS='kind evidence confidence enforcement generalizes supersedes'

# fm_of <file> — the frontmatter lines (ADR-2: first `---` to the next)
fm_of() {
  awk 's == 0 && $0 == "---" { s = 1; next } s == 1 && $0 == "---" { exit } s == 1 { print }' "$1"
}

close=$(awk '$0 == "---" { n++; if (n == 2) { print NR; exit } }' "$TPL" 2>/dev/null)
case "$close" in
  ''|*[!0-9]*)
    fail "template_frontmatter_closes_by_line_25: no closing --- found in templates/lesson-template.md" ;;
  *)
    if [ "$close" -le 25 ]; then
      pass "template_frontmatter_closes_by_line_25: closes at line $close"
    else
      fail "template_frontmatter_closes_by_line_25: closes at line $close (cap 25)"
    fi ;;
esac

TPL_FM=$(fm_of "$TPL" 2>/dev/null)
six_bad=""
for k in kind evidence confidence enforcement generalizes supersedes; do
  cnt=$(printf '%s\n' "$TPL_FM" | grep -c "^$k:")
  com=$(printf '%s\n' "$TPL_FM" | grep "^$k:" | grep -c ' #')
  nxt=$(printf '%s\n' "$TPL_FM" | awk -v k="$k:" 'p { print; exit } index($0, k) == 1 { p = 1 }')
  [ "$cnt" = 1 ] || six_bad="$six_bad $k(count=$cnt)"
  [ "$com" = 1 ] || six_bad="$six_bad $k(no trailing # comment)"
  case "$nxt" in
    ''|[A-Za-z_]*:*) ;;
    *) six_bad="$six_bad $k(continues onto the next line)" ;;
  esac
done
# BR-1: immediately before the closing `---`, in this order.
tail_keys=$(printf '%s\n' "$TPL_FM" | tail -n 6 | sed 's/:.*//' | tr '\n' ' ' | sed 's/ $//')
[ "$tail_keys" = "$SIX_KEYS" ] || six_bad="$six_bad (last six frontmatter keys are '$tail_keys')"
if [ -z "$six_bad" ]; then
  pass "template_has_six_fields_one_line_each: each key once, one line, trailing comment, last six before ---"
else
  fail "template_has_six_fields_one_line_each:$six_bad"
fi

tax_bad=""
TAGS_LN=$(awk 'index($0, "## tags (free-form)") == 1 { print NR; exit }' "$TAX" 2>/dev/null)
case "$TAGS_LN" in ''|*[!0-9]*) tax_bad="$tax_bad (no '## tags (free-form)' section)"; TAGS_LN=0 ;; esac
enum_section() { # enum_section <heading-prefix> <value>... — appends problems to tax_bad
  es_h=$1; shift
  es_ln=$(awk -v h="$es_h" 'index($0, h) == 1 { print NR; exit }' "$TAX" 2>/dev/null)
  case "$es_ln" in
    ''|*[!0-9]*) tax_bad="$tax_bad ($es_h missing)"; return 0 ;;
  esac
  [ "$es_ln" -lt "$TAGS_LN" ] || tax_bad="$tax_bad ($es_h not before tags)"
  es_body=$(awk -v h="$es_h" 'index($0, h) == 1 { f = 1; next } f && /^## / { exit } f' "$TAX")
  printf '%s\n' "$es_body" | grep -qF 'adlc_lesson_check' \
    || tax_bad="$tax_bad ($es_h does not say adlc_lesson_check enforces it)"
  for es_v in "$@"; do
    printf '%s\n' "$es_body" | grep -qF -- "\`$es_v" || tax_bad="$tax_bad ($es_h lacks \`$es_v)"
  done
  return 0
}
enum_section '## kind (' 'process`' 'domain`'
enum_section '## confidence (' 'high`' 'medium`' 'low`'
enum_section '## enforcement (' 'none`' 'lint:' 'test:' 'script:' 'hook:'
# ADR-7: the retrieval tags stay advisory; only the three lesson enums are enforced.
awk '/^## / { exit } { print }' "$TAX" 2>/dev/null | grep -qi 'advisory' \
  || tax_bad="$tax_bad (intro no longer calls the retrieval tags advisory)"
if [ -z "$tax_bad" ]; then
  pass "taxonomy_documents_three_enums: kind, confidence, enforcement sections before tags, values listed, intro still advisory"
else
  fail "taxonomy_documents_three_enums:$tax_bad"
fi

# AC-2: a fixture built from the template with all six fields filled keeps its
# frontmatter inside /spec Step 1.6's 30-line read, and its five retrieval-tag lines
# are byte-identical to the same fixture without the six keys — so the scorer, which
# reads only those five, scores both the same.
TPL_FULL=$(fx tpl-full)
sed -e 's#^component: ""#component: "adlc/partials"#' \
    -e 's#^domain: ""#domain: "adlc"#' \
    -e 's#^stack: \[\]#stack: ["bash", "markdown"]#' \
    -e 's#^concerns: \[\]#concerns: ["structural-enforcement"]#' \
    -e 's#^tags: \[\]#tags: ["lesson-check", "fixture"]#' \
    "$TPL" > "$SANDBOX/tpl-tags.md" 2>/dev/null
sed -e 's#^kind: ""#kind: "process"#' \
    -e 's#^evidence: ""#evidence: "partials/forge.sh:42 exits 0 under /bin/sh"#' \
    -e 's#^confidence: ""#confidence: "high"#' \
    -e 's#^generalizes: \[\]#generalizes: [LESSON-404]#' \
    -e 's#^supersedes: \[\]#supersedes: [LESSON-019]#' \
    "$SANDBOX/tpl-tags.md" > "$TPL_FULL"
grep -vE '^(kind|evidence|confidence|enforcement|generalizes|supersedes):' \
    "$SANDBOX/tpl-tags.md" > "$SANDBOX/tpl-bare.md"
fx_bad=""
fx_close=$(awk '$0 == "---" { n++; if (n == 2) { print NR; exit } }' "$TPL_FULL")
case "$fx_close" in
  ''|*[!0-9]*) fx_bad="$fx_bad (filled fixture has no closing ---)" ;;
  *) [ "$fx_close" -le 30 ] || fx_bad="$fx_bad (filled fixture closes at line $fx_close > 30)" ;;
esac
head -n 30 "$TPL_FULL" > "$SANDBOX/tpl-head30.md"
for k in kind evidence confidence enforcement generalizes supersedes component domain stack concerns tags; do
  grep -q "^$k:" "$SANDBOX/tpl-head30.md" || fx_bad="$fx_bad ($k not within the first 30 lines)"
done
tags_full=$(fm_of "$TPL_FULL" | grep -E '^(component|domain|stack|concerns|tags):')
tags_bare=$(fm_of "$SANDBOX/tpl-bare.md" | grep -E '^(component|domain|stack|concerns|tags):')
tag_lines=$(printf '%s\n' "$tags_full" | grep -c .)
[ "$tag_lines" = 5 ] || fx_bad="$fx_bad (expected 5 retrieval-tag lines, found $tag_lines)"
[ "$tags_full" = "$tags_bare" ] || fx_bad="$fx_bad (retrieval-tag lines differ with and without the six keys)"
if [ -z "$fx_bad" ]; then
  pass "six_field_fixture_frontmatter_within_30_lines_and_tags_unchanged: closes at line $fx_close; five tag lines byte-identical"
else
  fail "six_field_fixture_frontmatter_within_30_lines_and_tags_unchanged:$fx_bad"
fi

# The template as a drafter fills it — trailing comments kept, the comment block above
# `---` — passes the check: the template and the checker agree on one shape.
run_check "$TPL_FULL"
if [ "$RC" = 0 ] && [ -z "$OUT" ] && [ -z "$ERR" ]; then
  pass "template_filled_passes_check: the filled template, comments and all, is rc 0"
else
  fail "template_filled_passes_check: got rc $RC, stderr '$(flat "$ERR")'"
fi

# ===========================================================================
# 11. No ship-date cutoff literal (AC-5, BR-2)
# ===========================================================================
DATE_RE='[0-9]{4}-[0-9]{2}-[0-9]{2}'

# lesson_fences <SKILL.md> — the body of every fenced block that calls adlc_lesson_check
lesson_fences() {
  awk '
    /^[ \t]*```/ {
      if (inf) { if (hit) printf "%s", buf; inf = 0; buf = ""; hit = 0 }
      else { inf = 1 }
      next
    }
    inf { buf = buf $0 "\n"; if (index($0, "adlc_lesson_check")) hit = 1 }
  ' "$1" 2>/dev/null
}

# Positive control (LESSON-602): the extractor and the regex must both fire on a planted
# fence before their silence over the real files means anything.
printf '%s\n' 'prose' '```sh' 'adlc_lesson_check x.md  # cutoff 2026-10-27' '```' \
  '```sh' 'echo unrelated 2026-10-27' '```' > "$SANDBOX/probe-SKILL.md"
probe=$(lesson_fences "$SANDBOX/probe-SKILL.md" | grep -cE "$DATE_RE")
if [ "$probe" != 1 ]; then
  fail "no_date_literal_in_partial_or_skills: control failed — the extractor+regex found $probe date line(s) in the planted probe (expected 1)"
else
  hits=$(grep -nE "$DATE_RE" "$PARTIALS/lesson-check.sh")
  if [ -z "$hits" ]; then
    pass "no_date_literal_in_partial_or_skills: partials/lesson-check.sh carries no YYYY-MM-DD literal"
  else
    fail "no_date_literal_in_partial_or_skills: partials/lesson-check.sh: $(flat "$hits")"
  fi
  for sk in wrapup bugfix; do
    body=$(lesson_fences "$ROOT/$sk/SKILL.md")
    if [ -z "$body" ]; then
      fail "no_date_literal_in_partial_or_skills: $sk/SKILL.md has no adlc_lesson_check fence — the capture step lost its check"
    else
      hits=$(printf '%s\n' "$body" | grep -E "$DATE_RE")
      if [ -z "$hits" ]; then
        pass "no_date_literal_in_partial_or_skills: $sk/SKILL.md adlc_lesson_check fence(s) carry no YYYY-MM-DD literal"
      else
        fail "no_date_literal_in_partial_or_skills: $sk/SKILL.md fence: $(flat "$hits")"
      fi
    fi
  done
fi

# ===========================================================================
# 12. architecture.md names the six fields (TASK-110: BR-11, AC-13)
# ===========================================================================
ARCH="$ROOT/.adlc/context/architecture.md"
if [ ! -f "$ARCH" ]; then
  fail "architecture_doc_names_six_fields: .adlc/context/architecture.md is absent"
elif awk '
    index($0, "`lesson-template.md`") {
      n = split("kind evidence confidence enforcement generalizes supersedes", ks, " ")
      c = 0
      for (i = 1; i <= n; i++) if ($0 ~ ("(^|[^A-Za-z0-9_])" ks[i] "([^A-Za-z0-9_]|$)")) c++
      if (c == n) found = 1
    }
    END { exit (found ? 0 : 1) }' "$ARCH"; then
  pass "architecture_doc_names_six_fields: the lesson-template.md row names all six v2 fields"
else
  fail "architecture_doc_names_six_fields: no line naming \`lesson-template.md\` names all six of: $SIX_KEYS"
fi

# ===========================================================================
# 13. Skill-text cases Tier 1 owes (TASK-109 is this harness's only Tier-2 writer)
# ===========================================================================
# The text these read landed with TASK-106 (/wrapup), TASK-107 (/bugfix) and
# TASK-108 (/review, /spec), so each is a PASS or a FAIL — never a skip. Every
# section extraction is tested non-empty before it is grepped, so a renamed
# heading is a FAIL rather than a grep that silently searched nothing.
WRAPUP_MD="$ROOT/wrapup/SKILL.md"
BUGFIX_MD="$ROOT/bugfix/SKILL.md"
REVIEW_MD="$ROOT/review/SKILL.md"
SPEC_MD="$ROOT/spec/SKILL.md"

# Inside /wrapup Step 5: the fenced templates, the `### Lessons captured` headings in
# them, how many headings are followed by a body line, and how many are not.
lc_counts=$(awk '
  index($0, "### Step 5:") == 1 { s5 = 1; next }
  s5 && index($0, "### Step 6:") == 1 { exit }
  !s5 { next }
  /^[ \t]*```/ { if (inf) { if (want) bad++; inf = 0; want = 0 } else { inf = 1; t++ } next }
  inf && want { if ($0 ~ /^[ \t]*$/ || $0 ~ /^[ \t]*#/) bad++; else ok++; want = 0; next }
  inf && $0 == "### Lessons captured" { n++; want = 1 }
  END { printf "templates=%d headings=%d with-body=%d without-body=%d", t, n, ok, bad
        exit !(t >= 2 && n == t && ok == n && bad == 0) }
' "$WRAPUP_MD" 2>/dev/null)
if [ $? -eq 0 ]; then
  pass "wrapup_templates_carry_lessons_captured: every Step 5 template has '### Lessons captured' with a body line ($lc_counts)"
else
  fail "wrapup_templates_carry_lessons_captured: expected >= 2 Step 5 templates, each with '### Lessons captured' followed by a body line; got '$lc_counts'"
fi

# /bugfix Step 6 runs to the next `## ` heading outside a fence (its template opens
# with `## BUG-xxx`, inside the fence).
bf_s6=$(awk '
  index($0, "**Step 6 ") == 1 { f = 1 }
  !f { next }
  /^[ \t]*```/ { inf = !inf; print; next }
  !inf && /^## / { exit }
  { print }
' "$BUGFIX_MD" 2>/dev/null)
if [ -z "$bf_s6" ]; then
  fail "bugfix_summary_uses_no_entry_form: no '**Step 6 ' section in bugfix/SKILL.md"
elif ! printf '%s\n' "$bf_s6" | grep -qF 'NO_ENTRY: <reason>'; then
  fail "bugfix_summary_uses_no_entry_form: Step 6 does not carry 'NO_ENTRY: <reason>'"
elif printf '%s\n' "$bf_s6" | grep -qF 'None — fix was straightforward'; then
  fail "bugfix_summary_uses_no_entry_form: Step 6 still carries 'None — fix was straightforward'"
else
  pass "bugfix_summary_uses_no_entry_form: Step 6 carries 'NO_ENTRY: <reason>' and not 'None — fix was straightforward'"
fi

rv_missing=""
for rv_s in '(matched LESSON-xxx, confidence low — not escalated)' \
            '(matched LESSON-xxx, superseded by LESSON-yyy — not escalated)' \
            'escalates as today'; do
  grep -qF -- "$rv_s" "$REVIEW_MD" 2>/dev/null || rv_missing="$rv_missing '$rv_s'"
done
if [ -z "$rv_missing" ]; then
  pass "review_step4_states_both_exemptions: review/SKILL.md carries both not-escalated annotations and the legacy 'escalates as today' sentence"
else
  fail "review_step4_states_both_exemptions: review/SKILL.md lacks:$rv_missing"
fi

# BR-7: the five scoring lines, consecutive and in order, each compared whole after
# its list indentation is stripped.
cat > "$SANDBOX/scoring.txt" <<'EOF'
- `+3` if `doc.component == query.component`
- `+2` if `doc.domain == query.domain`
- `+2 × |doc.concerns ∩ query.concerns|`
- `+1 × |doc.stack ∩ query.stack|`
- `+1 × |doc.tags ∩ query.tags|`
EOF
sc_at=$(awk '
  NR == FNR { w[++n] = $0; next }
  { s = $0; sub(/^[ \t]+/, "", s); L[++m] = s }
  END {
    for (i = 1; i + n - 1 <= m; i++) {
      ok = 1
      for (j = 1; j <= n; j++) if (L[i + j - 1] != w[j]) { ok = 0; break }
      if (ok) { print i; exit }
    }
  }
' "$SANDBOX/scoring.txt" "$SPEC_MD" 2>/dev/null)
if [ -n "$sc_at" ]; then
  pass "spec_scoring_rule_unchanged: the five Step 1.6 scoring lines are verbatim and consecutive at spec/SKILL.md:$sc_at"
else
  fail "spec_scoring_rule_unchanged: spec/SKILL.md does not carry the five scoring lines (+3, +2, +2 ×, +1 ×, +1 ×) verbatim and consecutive"
fi

ss_s8=$(awk 'index($0, "8. **Surface the retrieval summary**") == 1 { f = 1 } f && index($0, "9. ") == 1 { exit } f' "$SPEC_MD" 2>/dev/null)
ss_s3=$(awk 'index($0, "### Step 3:") == 1 { f = 1; next } f && index($0, "### Step 4:") == 1 { exit } f' "$SPEC_MD" 2>/dev/null)
ss_bad=""
if [ -z "$ss_s8" ]; then
  ss_bad="$ss_bad (no Step 1.6 sub-step 8 found)"
elif ! printf '%s\n' "$ss_s8" | grep -qF 'superseded by LESSON-'; then
  ss_bad="$ss_bad (Step 1.6 sub-step 8 lacks 'superseded by LESSON-')"
fi
if [ -z "$ss_s3" ]; then
  ss_bad="$ss_bad (no Step 3 found)"
elif ! printf '%s\n' "$ss_s3" | grep -qF 'superseded by LESSON-'; then
  ss_bad="$ss_bad (Step 3 lacks 'superseded by LESSON-')"
fi
if [ -z "$ss_bad" ]; then
  pass "spec_summary_annotation_documented: 'superseded by LESSON-' is in Step 1.6 sub-step 8 and in Step 3"
else
  fail "spec_summary_annotation_documented:$ss_bad"
fi

# BR-5: every lesson-capture-rules block in both capture skills carries the granularity
# sentence. A skill with no block at all is a FAIL, not a vacuous pass.
gran_bad=""
for sk in wrapup bugfix; do
  g=$(awk '
    { t = $0; sub(/^[ \t]+/, "", t); sub(/[ \t]+$/, "", t) }
    t == "<!-- lesson-capture-rules -->" { inb = 1; n++; has = 0; next }
    inb && t == "<!-- /lesson-capture-rules -->" { inb = 0; if (has) ok++; next }
    inb && index(t, "Granularity:") == 1 && index(t, "too generic") && index(t, "too specific") { has = 1 }
    END { printf "blocks=%d with-granularity=%d", n, ok; exit !(n >= 1 && ok == n) }
  ' "$ROOT/$sk/SKILL.md" 2>/dev/null) || gran_bad="$gran_bad $sk($g)"
done
if [ -z "$gran_bad" ]; then
  pass "granularity_line_in_both_skills_rules_blocks: every lesson-capture-rules block in wrapup and bugfix carries the Granularity line"
else
  fail "granularity_line_in_both_skills_rules_blocks:$gran_bad"
fi

# ADR-6: /review's reverse lookup. The awk program is EXTRACTED from the lookup line in
# review/SKILL.md — the text between `-exec awk -v id="$ID" '` and `' {} +` — and run
# over a sandbox corpus, so the case tests the shipped program, never a copy that
# drifts from it. No lookup line, or more than one, is a FAIL — never a skip.
RL_PROG=$(awk -v a="-exec awk -v id=\"\$ID\" '" -v b="' {} +" '
  {
    i = index($0, a); if (!i) next
    r = substr($0, i + length(a)); j = index(r, b); if (!j) next
    n++; p = substr(r, 1, j - 1)
  }
  END { if (n == 1) print p; exit (n == 1 ? 0 : 1) }' "$REVIEW_MD" 2>/dev/null)
rl_n=$(grep -cF -- "-exec awk -v id=\"\$ID\" '" "$REVIEW_MD" 2>/dev/null)
mkdir "$SANDBOX/rl"
rl() { # rl <file> <supersedes-line> [body] — a plain frontmatter lesson
  printf '%s\n' '---' 'id: LESSON-5xx' "$2" '---' '' "${3-Body text.}" > "$SANDBOX/rl/$1"
}
# The hit behind a leading HTML comment, whose own `---` pair is a decoy.
printf '%s\n' '<!--' 'Filename MUST be `LESSON-xxx-slug.md`.' '---' 'supersedes: [LESSON-999]' '---' '-->' \
  '---' 'id: LESSON-501' 'supersedes: [LESSON-40]' '---' '' 'Body text.' > "$SANDBOX/rl/LESSON-501-comment-headed.md"
rl LESSON-502-body.md 'supersedes: []' 'supersedes: [LESSON-40] (quoted in the body)'
rl LESSON-503-trailing-comment.md 'supersedes: []   # was LESSON-40'
rl LESSON-504-longer-id.md 'supersedes: [LESSON-404]'
rl LESSON-505-left-glued-id.md 'supersedes: [LESSON-140]'
# A real hit with CRLF line ends.
printf '%s\r\n' '---' 'id: LESSON-506' 'supersedes: [LESSON-40]' '---' '' 'Body text.' > "$SANDBOX/rl/LESSON-506-crlf.md"
# A BOM file: its frontmatter supersedes LESSON-400 (the second run's only hit), and
# its body mentions LESSON-40.
{ printf '\357\273\277'; printf '%s\n' '---' 'id: LESSON-507' 'supersedes: [LESSON-400]' '---' '' \
  'supersedes: [LESSON-40] (quoted in the body)'; } > "$SANDBOX/rl/LESSON-507-bom.md"
# A frontmatter-less legacy file: `---` rules around a supersedes line are not a block.
printf '%s\n' '# A legacy lesson' '' 'Some text.' '' '---' '' 'supersedes: [LESSON-40]' '' '---' \
  > "$SANDBOX/rl/LESSON-508-legacy.md"
for rl_md in "$REVIEW_MD" "$(dirname "$REVIEW_MD")/../spec/SKILL.md"; do
  if grep -qF -- "LC_ALL=C find .adlc/knowledge/lessons -maxdepth 1 -type f -name 'LESSON-*.md' -exec awk -v id=\"\$ID\" '" "$rl_md"; then
    pass "supersedes_lookup_runs_bytewise: $(basename "$(dirname "$rl_md")")/SKILL.md runs the lookup under LC_ALL=C, so a BOM-headed lesson matches under a UTF-8 locale"
  else
    fail "supersedes_lookup_runs_bytewise: $rl_md's supersedes lookup is not 'LC_ALL=C find ... -exec awk' — under a UTF-8 locale macOS awk misses a BOM-headed lesson"
  fi
done
if [ -z "$RL_PROG" ]; then
  fail "supersedes_reverse_lookup_is_exact: no single lookup program extracted from review/SKILL.md ($rl_n line(s) carry '-exec awk -v id=\"\$ID\" '' — want exactly 1, closed by \"' {} +\")"
else
  # LC_ALL=C: the program's BOM strip is a byte-wise regex, which a multibyte awk
  # (any UTF-8 locale) does not match. The lookup line in review/SKILL.md and its
  # twin in spec/SKILL.md run it as `LC_ALL=C find ... -exec awk`, so the case runs
  # it the same way; supersedes_lookup_runs_bytewise pins that prefix.
  rl_hits=$(LC_ALL=C awk -v id=LESSON-40 "$RL_PROG" "$SANDBOX"/rl/*.md 2>&1 | sed 's#.*/##' | tr '\n' ' ')
  rl_bom=$(LC_ALL=C awk -v id=LESSON-400 "$RL_PROG" "$SANDBOX"/rl/*.md 2>&1 | sed 's#.*/##' | tr '\n' ' ')
  if [ "$rl_hits" = "LESSON-501-comment-headed.md LESSON-506-crlf.md " ] \
     && [ "$rl_bom" = "LESSON-507-bom.md " ]; then
    pass "supersedes_reverse_lookup_is_exact: review/SKILL.md's program finds LESSON-40 in the comment-headed and CRLF files only (not the body, a comment, 404, 140, the BOM file's body or the legacy rules), and LESSON-400 in the BOM file's frontmatter"
  else
    fail "supersedes_reverse_lookup_is_exact: id=LESSON-40 want 'LESSON-501-comment-headed.md LESSON-506-crlf.md ', got '$rl_hits'; id=LESSON-400 want 'LESSON-507-bom.md ', got '$rl_bom' (program: $RL_PROG)"
  fi
fi

# conventions.md "Bash in skills": the partial holds none of the constructs that break
# under BSD grep, macOS mktemp or POSIX sh. The control proves the grep fires.
FORBID='\\b|mktemp -t|\[\[|local '
printf '%s\n' "x \\""b" "mk""temp -t foo" "[""[ -n x ]]" "loc""al x" > "$SANDBOX/forbid-probe.sh"
fb_probe=$(grep -cE "$FORBID" "$SANDBOX/forbid-probe.sh")
fb_hits=$(grep -nE "$FORBID" "$PARTIALS/lesson-check.sh")
if [ "$fb_probe" != 4 ]; then
  fail "partial_has_no_forbidden_constructs: control failed — the grep found $fb_probe of 4 planted constructs"
elif [ -n "$fb_hits" ]; then
  fail "partial_has_no_forbidden_constructs: $(flat "$fb_hits")"
else
  pass "partial_has_no_forbidden_constructs: no backslash-b, mktemp -t, double bracket or local in partials/lesson-check.sh"
fi

# The companion is the one home for the rule table; the README entry points at it.
CMP="$PARTIALS/lesson-check.md"
cmp_bad=""
if [ ! -f "$CMP" ]; then
  cmp_bad=" (partials/lesson-check.md absent)"
else
  for cmp_s in '## Return-code registry' '## Rule table' '## Departures from the original ADR-3' 'adlc_lesson_check'; do
    grep -qF -- "$cmp_s" "$CMP" || cmp_bad="$cmp_bad (lacks '$cmp_s')"
  done
fi
if [ -z "$cmp_bad" ]; then
  pass "companion_doc_present: lesson-check.md carries the rc registry, the rule table and the departures from the original ADR-3"
else
  fail "companion_doc_present:$cmp_bad"
fi

RDM_ENTRY=$(awk '
  index($0, "- `lesson-check.sh`") == 1 { f = 1; print; next }
  f && ($0 ~ /^- / || $0 ~ /^[ \t]*$/) { exit }
  f { print }' "$PARTIALS/README.md" 2>/dev/null)
rdm_bad=""
if [ -z "$RDM_ENTRY" ]; then
  rdm_bad=" (no '- \`lesson-check.sh\`' entry in partials/README.md)"
else
  for rdm_s in 'adlc_lesson_check' '**0**' '**1**' '**2**' 'lesson-check.md' 'tests/lesson-check.test.sh'; do
    printf '%s\n' "$RDM_ENTRY" | grep -qF -- "$rdm_s" || rdm_bad="$rdm_bad (entry lacks '$rdm_s')"
  done
fi
if [ -z "$rdm_bad" ]; then
  pass "readme_lists_lesson_check: partials/README.md entry names the function, rc 0/1/2, the companion and the harness"
else
  fail "readme_lists_lesson_check:$rdm_bad"
fi

# ===========================================================================
# 14. The summary guard, run alone (LESSON-019)
# ===========================================================================
# Extract the guard from THIS file and run it in the shell under test with fixed
# counts: a vacuous run and a short run must exit 1; the control (a full, clean run)
# must exit 0, or a guard that always fails would pass this case.
GUARD_SRC=$(awk '
  index($0, "# >>> summary-guard") == 1 { f = 1; next }
  index($0, "# <<< summary-guard") == 1 { f = 0 }
  f' "$HERE/lesson-check.test.sh")
guard_rc() { # guard_rc <cases> <fails> — the exit status of the guard alone
  printf 'CASES=%s\nFAILS=%s\n%s\nlc_summary\n' "$1" "$2" "$GUARD_SRC" > "$SANDBOX/guard-only.sh"
  "$TSHELL" "$SANDBOX/guard-only.sh" >/dev/null 2>&1
  printf '%s' "$?"
}
if [ -z "$GUARD_SRC" ]; then
  fail "summary_guard_fails_short_runs: no summary-guard block found in lesson-check.test.sh"
else
  g0=$(guard_rc 0 0); g59=$(guard_rc 59 0); g60f=$(guard_rc 60 1); g60=$(guard_rc 60 0)
  if [ "$g0" = 1 ] && [ "$g59" = 1 ] && [ "$g60f" = 1 ] && [ "$g60" = 0 ]; then
    pass "summary_guard_fails_short_runs: 0 cases -> 1, 59 cases -> 1, a failure -> 1, 60 clean -> 0 (under $TSHELL)"
  else
    fail "summary_guard_fails_short_runs: under $TSHELL got 0->$g0, 59->$g59, 60+fail->$g60f, 60 clean->$g60 (want 1, 1, 1, 0)"
  fi
fi

# ===========================================================================
# 15. The abort guard, end to end (a harness cut short is a red)
# ===========================================================================
# A copy of THIS file, cut at the meta-cut marker after its first case — so it never
# reaches lc_summary — runs in the shell under test as a subprocess, in its own tree
# (the partial copied beside it) with its own sandbox under a TMPDIR inside ours. It
# must print that first case's PASS (so it ran, and did not just crash), print no
# summary, exit 1 with the abort line, and leave its TMPDIR empty (its cleanup ran).
META="$SANDBOX/meta"
mkdir -p "$META/partials/tests" "$META/tmp"
cp "$PARTIALS/lesson-check.sh" "$META/partials/lesson-check.sh"
awk 'index($0, "# >>> meta-cut") == 1 { exit } { print }' "$HERE/lesson-check.test.sh" \
  > "$META/partials/tests/lesson-check.test.sh"
meta_bad=""
grep -q '^lc_summary$' "$META/partials/tests/lesson-check.test.sh" \
  && meta_bad="$meta_bad (the cut copy still calls lc_summary — no meta-cut marker before it)"
grep -q "aborted before summary" "$META/partials/tests/lesson-check.test.sh" \
  || meta_bad="$meta_bad (the cut copy lost the EXIT trap)"
TMPDIR="$META/tmp" "$TSHELL" "$META/partials/tests/lesson-check.test.sh" >"$META/out" 2>"$META/err"
meta_rc=$?
[ "$meta_rc" = 1 ] || meta_bad="$meta_bad (rc $meta_rc, want 1)"
grep -q '^PASS: well_formed_passes' "$META/out" || meta_bad="$meta_bad (no PASS: well_formed_passes — the copy did not run its case)"
grep -q 'cases executed' "$META/out" && meta_bad="$meta_bad (a summary printed)"
grep -qF 'lesson-check.test.sh: aborted before summary' "$META/err" \
  || meta_bad="$meta_bad (no abort line on stderr: '$(flat "$(cat "$META/err")")')"
[ -z "$(ls -A "$META/tmp")" ] || meta_bad="$meta_bad (the copy's sandbox was left behind)"
if [ -z "$meta_bad" ]; then
  pass "harness_aborts_without_summary: a copy cut before lc_summary ran its case, then exited 1 with the abort line and cleaned its sandbox (under $TSHELL)"
else
  fail "harness_aborts_without_summary:$meta_bad"
fi

# ===========================================================================
# ===========================================================================
# 13. Executor-shell wrapper (LESSON-717). The Claude Code Bash tool defines `grep`
# as a shell function routed to its own matcher; its `-vq` returns 0 on empty input
# where grep returns 1, which made _alc_ids_ok reject the template's `[]` in the
# first real /wrapup run. The partial calls `command grep`, so a wrapper that
# returns 0 for everything must change no verdict: a well-formed lesson still
# passes and a bad list entry is still rejected.
# ===========================================================================
lesson wrapok "$(six process "$EV_OK" high none '[]' '[]')"
lesson wrapbad "$(six process "$EV_OK" high none '[]' '[LESSON-7]')"
# The wrapper lives in a subshell so no later case inherits it. It runs the real grep
# for its output and then discards its status — exactly the executor's behaviour on
# empty input, applied to every call.
_wrap_rc_ok=$( grep() { command grep "$@"; return 0; }; adlc_lesson_check "$(fx wrapok)" >/dev/null 2>&1; echo $? )
_wrap_rc_bad=$( grep() { command grep "$@"; return 0; }; adlc_lesson_check "$(fx wrapbad)" >/dev/null 2>&1; echo $? )
if [ "$_wrap_rc_ok" = 0 ]; then
  pass "executor_grep_wrapper_keeps_accept: well-formed lesson still rc 0 under an always-0 grep wrapper"
else
  fail "executor_grep_wrapper_keeps_accept: expected rc 0 under an always-0 grep wrapper, got rc $_wrap_rc_ok (a grep site is not 'command grep' — LESSON-717)"
fi
if [ "$_wrap_rc_bad" = 1 ]; then
  pass "executor_grep_wrapper_keeps_reject: bad supersedes entry still rc 1 under an always-0 grep wrapper"
else
  fail "executor_grep_wrapper_keeps_reject: expected rc 1 under an always-0 grep wrapper, got rc $_wrap_rc_bad (a grep site is not 'command grep' — LESSON-717)"
fi

lc_summary
