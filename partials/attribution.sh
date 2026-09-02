# partials/attribution.sh — incident→REQ attribution (REQ-593).
#
# Source this partial, then call the functions WITHIN THE SAME fenced block:
#   if [ -f .adlc/partials/attribution.sh ]; then . .adlc/partials/attribution.sh; else . ~/.claude/skills/partials/attribution.sh; fi
#   reqs=$(adlc_attr_blame_reqs "$repo" "$primary" "src/foo.js" 10 24)
#
# Derives "which REQ introduced this defect" from git history: blame the root-cause
# line range -> read each blamed commit's message -> extract an attested REQ id ->
# validate it against the PRIMARY repo's spec directory. Consumed by /bugfix Phase 2
# (derive + record) and /status (the derived reverse index).
#
# Functions exported:
#   adlc_attr_validate_req <primary> <id>              -> 0 iff id is well-formed AND its
#                                                          spec dir exists in <primary>
#   adlc_attr_req_context <repo> <sha>                 -> REQ id(s) attested by one commit
#   adlc_attr_commit_reqs <repo> <primary> <sha>       -> validated candidate(s), TASK-scoped
#   adlc_attr_blame_reqs <repo> <primary> <file> [s] [e] -> sorted-unique candidates for a range
#   adlc_attr_bugs_with_attribution <primary> [req]    -> "BUG-id<TAB>REQ-id" reverse index
#
# ---------------------------------------------------------------------------
# The three attested provenance forms (BR-2), in PRECEDENCE order:
#   1. a bracketed [REQ-xxx] or [TASK-xxx] anywhere in SUBJECT OR BODY
#   2. a bare subject prefix           REQ-xxx: ...
#   3. a conventional-commit scope     <type>(REQ-xxx): ...
#
# Form 1 reads the BODY as well as the subject, and that is the single most
# load-bearing decision here. `git blame --porcelain` exposes only a `summary`
# field, which is the SUBJECT ALONE. Measured on this repo (187 commits): 37
# commits carry a bracketed trailer in the subject, 37 in the body, 59 in either;
# 75 carry provenance in some accepted form. A subject-only read therefore finds
# 37 of 75 and silently loses 51% of available attributions. Hence `git log -1
# --format='%s%n%b'` rather than blame's own summary (REQ-593 ADR-3).
#
# A `<type>(BUG-xxx): ...` scope identifies a PRIOR FIX, not the change that
# introduced the behavior, so it contributes no form-3 candidate. Note the
# precedence interaction: a BUG-scoped commit that ALSO carries an explicit
# bracketed [REQ-xxx] still yields that id, because form 1 outranks form 3 and an
# explicit bracket is the strongest available attestation. No commit in this repo's
# history exercises that combination today; `attribution.test.sh` pins the behavior
# so it stays a decision rather than an accident.
#
# TASK->REQ resolution is SCOPED, never globbed (BR-10). A [TASK-yyy] resolves only
# within the REQ context of the SAME commit, by reading
# `<primary>/.adlc/specs/<that-req>-*/tasks/TASK-yyy*.md`. TASK ids are per-REQ
# scoped, not global: `TASK-001.md` exists as an exact filename in 3 REQ directories,
# and a `TASK-001*.md` glob matches 16 of the 157 task files on disk. An unscoped
# glob would return several unrelated REQs and manufacture a false multi-candidate
# halt. A bare [TASK-yyy] with no REQ context in the same commit is NOT resolvable
# and yields nothing.
#
# Portability (BR-6) — this file is sourced by SKILL.md fences that run under the
# operator's shell, which on macOS is zsh (LESSON-329):
#   * `grep -E` only. Never `-P`; never `\b`, which BSD grep silently fails to
#     honor in -E and which would make every id match evaporate (LESSON-013).
#   * `printf`, never `echo`, for anything containing a variable.
#   * Lists travel through `while IFS= read -r`, never `for x in $var` — zsh does
#     not word-split unquoted parameters, so the loop body would see one blob
#     instead of N elements (BUG-118 / LESSON-399).
#   * Possibly-empty matches go through `find`, never a bare shell glob: zsh aborts
#     the whole command on an unmatched glob (LESSON-335).
#   * No variable named `status` (zsh reserves it), and every local is `_`-prefixed
#     because POSIX sh has no `local` and this file is SOURCED into the caller.
# ---------------------------------------------------------------------------

# adlc_attr_validate_req <primary-repo> <id> -> 0 iff valid, 1 otherwise. Emits nothing.
#
# BR-5: the strict pattern AND an existence check, both mandatory before any id is
# written to an artifact. Widening the pattern is prohibited (REQ-423, LESSON-008).
# The existence check resolves against the PRIMARY repo, never the blamed repo: in
# cross-repo mode the blame runs in a sibling's history but spec directories exist
# only in the primary, so conflating the two would fail every cross-repo attribution
# closed to `none` (BR-5/BR-8 interaction, REQ-593 ADR-5).
adlc_attr_validate_req() {
  _aavr_pri=$1
  _aavr_id=$2
  [ -n "$_aavr_id" ] || return 1
  printf '%s\n' "$_aavr_id" | grep -qE '^REQ-[0-9]{3,6}$' || return 1
  [ -n "$_aavr_pri" ] || return 1
  _aavr_hit=$(find "$_aavr_pri/.adlc/specs" -maxdepth 1 -type d \
    \( -name "$_aavr_id" -o -name "$_aavr_id-*" \) 2>/dev/null | head -1)
  [ -n "$_aavr_hit" ]
}

# adlc_attr_req_context <repo> <sha> -> prints attested REQ id(s), one per line.
#
# Applies the three forms in precedence order and stops at the first that yields
# anything. Prints nothing (and still returns 0) when the commit carries no attested
# provenance — the benign path (BR-7): no attribution is a valid outcome, never an error.
adlc_attr_req_context() {
  _aarc_repo=$1
  _aarc_sha=$2
  _aarc_msg=$(git -C "$_aarc_repo" log -1 --format='%s%n%b' "$_aarc_sha" 2>/dev/null) || return 0
  [ -n "$_aarc_msg" ] || return 0
  _aarc_subj=$(printf '%s\n' "$_aarc_msg" | head -1)

  # Form 1 — bracketed [REQ-xxx], anywhere in subject OR body (ADR-3).
  _aarc_hit=$(printf '%s\n' "$_aarc_msg" \
    | grep -oE '\[REQ-[0-9]{3,6}\]' | tr -d '[]' | sort -u)
  if [ -n "$_aarc_hit" ]; then
    printf '%s\n' "$_aarc_hit"
    return 0
  fi

  # Form 2 — bare subject prefix `REQ-xxx: ...`.
  _aarc_hit=$(printf '%s\n' "$_aarc_subj" \
    | grep -oE '^REQ-[0-9]{3,6}:' | tr -d ':' | sort -u)
  if [ -n "$_aarc_hit" ]; then
    printf '%s\n' "$_aarc_hit"
    return 0
  fi

  # Form 3 — conventional-commit scope `<type>(REQ-xxx): ...`. Only the parenthesised
  # scope is searched, so a REQ id merely mentioned in prose is not an attestation and a
  # `fix(BUG-145):` scope contributes nothing.
  #
  # A multi-id scope writes its siblings as BARE numbers — this repo's history contains
  # `docs(REQ-593/594/595): ...` — so a plain `REQ-[0-9]{3,6}` scan finds only the first
  # id. Matching just that one would silently attribute a three-REQ commit to a single
  # REQ and present the result as certain, which is precisely the "fall back to the
  # closest guess" that LESSON-483 forbids. Expanding the run instead surfaces all of
  # them and lets BR-3's operator choice do its job.
  _aarc_hit=$(printf '%s\n' "$_aarc_subj" \
    | grep -oE '^[a-zA-Z]+\([^)]*\)' \
    | grep -oE 'REQ-[0-9]{3,6}(/[0-9]{3,6})*' \
    | while IFS= read -r _aarc_run; do
        [ -n "$_aarc_run" ] || continue
        # Normalize every token to `REQ-nnn`: the run's head already carries the prefix,
        # its siblings are bare. Stripping an optional prefix and re-adding it handles
        # both in one expression. Deliberately NOT a `case` statement: a case pattern's
        # unbalanced `)` inside `$( ... )` is a syntax error in bash and sh while zsh
        # parses it happily — the exact cross-shell trap AC-10 exists to catch.
        printf '%s\n' "$_aarc_run" | tr '/' '\n' | while IFS= read -r _aarc_tok; do
          [ -n "$_aarc_tok" ] || continue
          printf 'REQ-%s\n' "${_aarc_tok#REQ-}"
        done
      done | sort -u)
  if [ -n "$_aarc_hit" ]; then
    printf '%s\n' "$_aarc_hit"
  fi
  return 0
}

# adlc_attr_commit_reqs <repo> <primary> <sha> -> validated candidate REQ id(s).
#
# Resolves any [TASK-yyy] within the commit's own REQ context (BR-10 / ADR-2), then
# applies BR-5 validation. Prints nothing when no candidate survives.
adlc_attr_commit_reqs() {
  _aacr_repo=$1
  _aacr_pri=$2
  _aacr_sha=$3
  _aacr_msg=$(git -C "$_aacr_repo" log -1 --format='%s%n%b' "$_aacr_sha" 2>/dev/null) || return 0
  _aacr_ctx=$(adlc_attr_req_context "$_aacr_repo" "$_aacr_sha")

  # BR-10: with no REQ context in this commit, a bare [TASK-yyy] is unresolvable and
  # there is no other form to fall back on. Refuse rather than glob (LESSON-483).
  [ -n "$_aacr_ctx" ] || return 0

  _aacr_tasks=$(printf '%s\n' "$_aacr_msg" \
    | grep -oE '\[TASK-[0-9]{3,6}\]' | tr -d '[]' | sort -u)

  _aacr_out=""
  # `while IFS= read -r`, not `for ... in $var` — zsh does not word-split (BUG-118).
  _aacr_out=$(printf '%s\n' "$_aacr_ctx" | while IFS= read -r _aacr_req; do
    [ -n "$_aacr_req" ] || continue
    if [ -n "$_aacr_tasks" ]; then
      printf '%s\n' "$_aacr_tasks" | while IFS= read -r _aacr_task; do
        [ -n "$_aacr_task" ] || continue
        # Scoped lookup: only inside THIS REQ's task directory.
        _aacr_tf=$(find "$_aacr_pri/.adlc/specs" -maxdepth 3 -type f \
          -path "*/$_aacr_req-*/tasks/$_aacr_task*.md" 2>/dev/null | head -1)
        if [ -n "$_aacr_tf" ]; then
          # The task file's own frontmatter is authoritative for the edge. BOTH spellings
          # are accepted, and that is not defensive padding: REQ-593's spec says tasks
          # carry a `req:` field, but the canonical templates/task-template.md emits
          # `parent:`, and 157 of this repo's 163 task files use `parent:` while only 6
          # use `req:`. Reading only the documented spelling would miss 96% of real task
          # files. `req:` is tried first so the documented field wins where both exist.
          _aacr_fm=$(awk 'NR==1&&/^---/{f=1;next} f&&/^---/{exit} f' "$_aacr_tf" 2>/dev/null)
          _aacr_fr=$(printf '%s\n' "$_aacr_fm" \
            | grep -E '^req:' | grep -oE 'REQ-[0-9]{3,6}' | head -1)
          [ -n "$_aacr_fr" ] || _aacr_fr=$(printf '%s\n' "$_aacr_fm" \
            | grep -E '^parent:' | grep -oE 'REQ-[0-9]{3,6}' | head -1)
          if [ -n "$_aacr_fr" ]; then
            printf '%s\n' "$_aacr_fr"
          else
            printf '%s\n' "$_aacr_req"
          fi
        else
          # Task file absent (renamed, or never committed). The REQ context is itself
          # independently attested, so fall back to it rather than dropping a correct
          # attribution over a missing file (ADR-2 consequence).
          printf '%s\n' "$_aacr_req"
        fi
      done
    else
      printf '%s\n' "$_aacr_req"
    fi
  done)

  [ -n "$_aacr_out" ] || return 0
  printf '%s\n' "$_aacr_out" | sort -u | while IFS= read -r _aacr_cand; do
    [ -n "$_aacr_cand" ] || continue
    if adlc_attr_validate_req "$_aacr_pri" "$_aacr_cand"; then
      printf '%s\n' "$_aacr_cand"
    fi
  done
}

# adlc_attr_blame_reqs <repo> <primary> <file> [start] [end] -> sorted-unique candidates.
#
# Blames the root-cause line range and unions the per-commit candidates. Omitting
# start/end blames the whole file. Prints nothing when nothing survives (BR-7).
adlc_attr_blame_reqs() {
  _aabr_repo=$1
  _aabr_pri=$2
  _aabr_file=$3
  _aabr_start=$4
  _aabr_end=$5

  if [ -n "$_aabr_start" ] && [ -n "$_aabr_end" ]; then
    _aabr_raw=$(git -C "$_aabr_repo" blame -L "$_aabr_start,$_aabr_end" --porcelain \
      -- "$_aabr_file" 2>/dev/null)
  else
    _aabr_raw=$(git -C "$_aabr_repo" blame --porcelain -- "$_aabr_file" 2>/dev/null)
  fi
  [ -n "$_aabr_raw" ] || return 0

  # Porcelain header lines begin with the 40-hex sha at column 0; content lines are
  # TAB-prefixed and cannot match. Drop the all-zero sha (uncommitted lines).
  _aabr_shas=$(printf '%s\n' "$_aabr_raw" \
    | grep -oE '^[0-9a-f]{40}' \
    | grep -vE '^0{40}$' | sort -u)
  [ -n "$_aabr_shas" ] || return 0

  _aabr_out=$(printf '%s\n' "$_aabr_shas" | while IFS= read -r _aabr_sha; do
    [ -n "$_aabr_sha" ] || continue
    adlc_attr_commit_reqs "$_aabr_repo" "$_aabr_pri" "$_aabr_sha"
  done)

  [ -n "$_aabr_out" ] || return 0
  printf '%s\n' "$_aabr_out" | sort -u | grep -E '^REQ-[0-9]{3,6}$'
}

# adlc_attr_bugs_with_attribution <primary> [req] -> "BUG-id<TAB>REQ-id" per edge.
#
# BR-4: the reverse index (REQ -> its incidents) is DERIVED at read time by scanning
# `.adlc/bugs/*.md` frontmatter. It is never written into a REQ spec — a stored reverse
# edge is exactly the cross-reference rot that a moved or renumbered artifact breaks
# silently (LESSON-019), and it is why /manifest derives rather than stores too.
# Strictly read-only: this function opens nothing under `.adlc/specs/**` and writes
# nothing anywhere. Optional <req> filters to one REQ's incidents.
adlc_attr_bugs_with_attribution() {
  _aabwa_pri=$1
  _aabwa_filter=$2
  find "$_aabwa_pri/.adlc/bugs" -maxdepth 1 -type f -name '*.md' 2>/dev/null | sort \
  | while IFS= read -r _aabwa_f; do
      [ -n "$_aabwa_f" ] || continue
      _aabwa_bug=$(basename "$_aabwa_f" .md | grep -oE '^BUG-[0-9]{3,6}')
      [ -n "$_aabwa_bug" ] || continue
      # Frontmatter only — never the body, so a REQ id mentioned in prose is not an edge.
      _aabwa_fm=$(awk 'NR==1&&/^---/{f=1;next} f&&/^---/{exit} f' "$_aabwa_f" 2>/dev/null)
      [ -n "$_aabwa_fm" ] || continue
      _aabwa_line=$(printf '%s\n' "$_aabwa_fm" | grep -E '^introduced_by:' | head -1)
      [ -n "$_aabwa_line" ] || continue
      _aabwa_ids=$(printf '%s\n' "$_aabwa_line" | grep -oE 'REQ-[0-9]{3,6}' | sort -u)
      [ -n "$_aabwa_ids" ] || continue
      printf '%s\n' "$_aabwa_ids" | while IFS= read -r _aabwa_id; do
        [ -n "$_aabwa_id" ] || continue
        if [ -z "$_aabwa_filter" ] || [ "$_aabwa_filter" = "$_aabwa_id" ]; then
          printf '%s\t%s\n' "$_aabwa_bug" "$_aabwa_id"
        fi
      done
    done
}
