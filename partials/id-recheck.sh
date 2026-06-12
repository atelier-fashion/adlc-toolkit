# partials/id-recheck.sh — pre-push / PR-time id collision recheck (REQ-518 BR-4, BR-8).
#
# Source this partial, then call adlc_recheck_id WITHIN THE SAME fenced block:
#   . .adlc/partials/id-recheck.sh 2>/dev/null || . ~/.claude/skills/partials/id-recheck.sh
#   if ! adlc_recheck_id req REQ-518; then
#     echo "halt: rename before pushing (see message above)" >&2
#     exit 1
#   fi
#
# Allocation runs at spec/bug/lesson CREATION; this recheck runs later at the moment a
# branch is about to be created or an artifact file is about to be committed for push.
# Between those two moments a colleague on another machine may have pushed the same id.
# The recheck re-derives the remote footprint and halts with a renumber instruction
# rather than pushing a duplicate (BR-4). It is a SEPARATE partial from id-alloc.sh so
# the recheck call sites don't load the full allocation machinery (ADR-3), but it sources
# id-alloc.sh for the kind mappers + adlc_remote_high so there is one derivation surface.
#
# Contract — adlc_recheck_id <kind> <ID>:   (kind = req|bug|lesson; ID = REQ-518 etc.)
#   return 0 -> <ID> is NOT present on any reachable remote (safe to proceed), OR the
#               remote was unreachable (degraded: cannot find a collision; warns, BR-3).
#   return 1 -> COLLISION: <ID> is already on the remote. A halt message naming the exact
#               `adlc renumber <KIND-old> <KIND-new>` command is printed to stderr (BR-4/BR-9).
#   return 2 -> usage error (bad kind / malformed ID).
# NEVER blocks on network (BR-3): an unreachable remote can only fail to FIND a
# collision, never invent one from absence of data.
#
# REQ-523: the degraded condition is now read from adlc_remote_high's stdout (its
# second token), not the old parent-env ADLC_ALLOC_DEGRADED flag (which died in the
# $(...) subshell — the M1 dead-code bug). The exact-id artifact probe routes through
# the shared adlc_remote_artifact_nums helper so ADO + gh-absent artifacts are seen
# (BR-6 — one derivation surface, no recheck-only copy).
#
# Portable across sh/bash/zsh (BR-6): prefixed globals, no `\b` in grep -E, no bare
# $<digit>, no [0] indexing, no `status=` var.

# Resolve the directory THIS partial was sourced from, portably across bash and zsh,
# so we can find the sibling id-alloc.sh regardless of cwd. bash exposes ${BASH_SOURCE};
# zsh exposes the sourced file via ${(%):-%x}. Fall back to the two-level convention
# paths if neither is set (e.g. piped source). Computed once at source time.
if [ -n "${BASH_SOURCE:-}" ]; then
  _ADLC_RECHECK_DIR=$(dirname -- "${BASH_SOURCE}")
elif [ -n "${ZSH_VERSION:-}" ]; then
  # ${(%):-%x} expands to the path of the file currently being sourced under zsh.
  _ADLC_RECHECK_DIR=$(dirname -- "${(%):-%x}")
else
  _ADLC_RECHECK_DIR=""
fi

# Source the allocation partial for the kind mappers + adlc_remote_high. Prefer the
# resolved sibling dir, then the two-level convention fallback used at every call site.
adlc_recheck_id() {
  adlc_rc_kind=$1
  adlc_rc_id=$2

  if [ -z "$adlc_rc_kind" ] || [ -z "$adlc_rc_id" ]; then
    echo "adlc_recheck_id: usage: adlc_recheck_id <kind> <ID>" >&2
    return 2
  fi

  # Ensure the kind mappers + adlc_remote_high are available (idempotent re-source).
  if ! command -v adlc_remote_high >/dev/null 2>&1; then
    { [ -n "$_ADLC_RECHECK_DIR" ] && . "$_ADLC_RECHECK_DIR/id-alloc.sh" 2>/dev/null; } \
      || . .adlc/partials/id-alloc.sh 2>/dev/null \
      || . ~/.claude/skills/partials/id-alloc.sh 2>/dev/null \
      || { echo "adlc_recheck_id: cannot source id-alloc.sh (kind mappers)" >&2; return 2; }
  fi

  adlc_rc_prefix=$(adlc_id_kind_prefix "$adlc_rc_kind") || return 2

  # Strict id validation: must be exactly <PREFIX>-<digits> (LESSON-008 — reject
  # traversal / garbage that could leak into a shelled-out rename later).
  if ! printf '%s' "$adlc_rc_id" | grep -qE "^$adlc_rc_prefix-[0-9]{3,}$"; then
    echo "adlc_recheck_id: id '$adlc_rc_id' does not match ^$adlc_rc_prefix-[0-9]{3,}\$" >&2
    return 2
  fi

  # Extract the numeric component and normalize to decimal.
  adlc_rc_num=$(printf '%s' "$adlc_rc_id" | sed -E "s/^$adlc_rc_prefix-//")
  adlc_rc_num=$(adlc_id_dec "$adlc_rc_num")

  # adlc_remote_high re-derives the remote footprint (branches + merged artifact dirs)
  # and prints "<high_water> <degraded>" (REQ-523 BR-2). If the remote high-water is >=
  # our number, SOMETHING at-or-above this id exists on the remote. That alone is not
  # proof THIS exact id is taken — but combined with the exact-id branch/dir probe below
  # it is. We do BOTH: the cheap high-water short-circuit plus an exact-id presence probe
  # so we don't false-halt merely because a HIGHER id was allocated elsewhere.
  #
  # The degraded bit now arrives on stdout (token 2), NOT via the old parent-env
  # ADLC_ALLOC_DEGRADED write — that write died in the $(...) subshell and made this
  # degraded branch dead code (REQ-523 M1 / LESSON-015). Split the two tokens.
  adlc_rc_rh=$(adlc_remote_high "$adlc_rc_kind")
  adlc_rc_high=${adlc_rc_rh%% *}
  adlc_rc_degraded=${adlc_rc_rh##* }
  # Loud-fail guard (BUG-116): the high-water token must be numeric. Validate only the
  # first token (the output now carries a trailing space + degraded bit).
  case "$adlc_rc_high" in
    ''|*[!0-9]*)
      echo "ERROR: adlc_remote_high returned non-numeric high-water '$adlc_rc_high' during recheck of $adlc_rc_id — aborting (BUG-116)" >&2
      return 2 ;;
  esac
  adlc_rc_high=$(adlc_id_dec "$adlc_rc_high")

  # Degraded short-circuit MUST run BEFORE the exact-id walk so a degraded derivation
  # never produces a renumber suggestion computed from a possibly-zero high-water
  # (REQ-523 BR-2 — the M1 dead-code bug). A degraded scan can only fail to FIND a
  # collision, never invent one; proceed WITHOUT remote verification.
  if [ "$adlc_rc_degraded" = "1" ]; then
    echo "WARNING: remote derivation DEGRADED during recheck of $adlc_rc_id — proceeding WITHOUT remote verification (BR-2/BR-3)." >&2
    return 0
  fi

  # Exact-id presence probe across participating repos. We re-walk the same repo set
  # adlc_remote_high uses, looking for the EXACT id as a pushed branch or merged dir/file.
  adlc_rc_root="${ADLC_REPOS_ROOT:-$(cd "$(git rev-parse --show-toplevel 2>/dev/null)/.." 2>/dev/null && pwd)}"
  [ -n "$adlc_rc_root" ] || adlc_rc_root="."

  # Branch token per kind: REQ rides feat/REQ-NNN, BUG rides fix/bug-NNN (lowercase
  # `bug` in the branch name, NOT the BUG prefix). Lesson has no branch of its own.
  case "$adlc_rc_kind" in
    req)    adlc_rc_branch_grep='feat/REQ-[0-9][0-9]*' ;;
    bug)    adlc_rc_branch_grep='fix/bug-[0-9][0-9]*' ;;
    lesson) adlc_rc_branch_grep='' ;;
  esac

  adlc_rc_hit=""
  # zsh NOMATCH guard — same rationale as adlc_remote_high (BUG-116).
  if [ -n "${ZSH_VERSION:-}" ]; then setopt localoptions nullglob 2>/dev/null; fi
  for adlc_rc_repo in "$adlc_rc_root"/*; do
    [ -d "$adlc_rc_repo/.git" ] || [ -f "$adlc_rc_repo/.git" ] || continue
    git -C "$adlc_rc_repo" remote get-url origin >/dev/null 2>&1 || continue

    if [ -n "$adlc_rc_branch_grep" ]; then
      adlc_rc_refs=$(git -C "$adlc_rc_repo" ls-remote --heads origin 2>/dev/null) || continue
      # Extract every branch number, normalize to decimal, exact-match against our num.
      # `grep -qx` on the normalized list avoids fragile subshell-exit tricks (zsh-safe).
      # Prefix-sibling safe (REQ-524): the greedy -oE extraction pulls the FULL digit
      # run (feat/REQ-1200 -> 1200), and -qx is whole-line equality — rechecking
      # REQ-120 can never hit REQ-1200, and vice versa.
      # Normalize with a per-line sed, NOT `while read; do adlc_id_dec; done` —
      # adlc_id_dec prints no trailing newline, so multiple candidates concatenated
      # into one bogus number and real collisions went undetected (BUG-116).
      adlc_rc_branch_nums=$(printf '%s\n' "$adlc_rc_refs" \
        | grep -oE "$adlc_rc_branch_grep" | grep -oE '[0-9][0-9]*' \
        | sed -E 's/^0+([0-9])/\1/')
      if printf '%s\n' "$adlc_rc_branch_nums" | grep -qx "$adlc_rc_num"; then
        adlc_rc_hit="$adlc_rc_repo (pushed branch)"
        break
      fi
    fi

    # Merged artifact dir/file probe via the SHARED forge-aware scan (REQ-523 BR-6):
    # gh fast-path -> git-transport fallback -> ADO parity, the SAME surface
    # adlc_remote_high uses. No recheck-only gh-api copy. The helper prints the
    # space-joined artifact numbers on line 1 and a scan-ran bit on line 2; re-split the
    # numbers onto newlines and normalize to decimal before the exact-match probe.
    adlc_rc_art=$(adlc_remote_artifact_nums "$adlc_rc_repo" "$adlc_rc_kind" "$adlc_rc_prefix")
    adlc_rc_art_ran=$(printf '%s\n' "$adlc_rc_art" | sed -n '2p')
    if [ "$adlc_rc_art_ran" = "1" ]; then
      adlc_rc_art_nums=$(printf '%s\n' "$adlc_rc_art" | sed -n '1p' | tr ' ' '\n' \
        | sed -E '/^$/d' | sed -E 's/^0+([0-9])/\1/')
      if printf '%s\n' "$adlc_rc_art_nums" | grep -qx "$adlc_rc_num"; then
        adlc_rc_hit="$adlc_rc_repo (merged artifact)"
        break
      fi
    fi
  done

  if [ -n "$adlc_rc_hit" ]; then
    adlc_rc_next=$(( adlc_rc_high + 1 ))
    adlc_rc_newid=$(printf '%s-%03d' "$adlc_rc_prefix" "$adlc_rc_next")
    {
      echo "COLLISION: $adlc_rc_id already exists on the remote ($adlc_rc_hit)."
      echo "Refusing to push a duplicate id (BR-4). Renumber before continuing:"
      echo
      echo "    adlc renumber $adlc_rc_id $adlc_rc_newid"
      echo
      echo "(then re-run; the renumber helper re-checks the new id against the remote.)"
    } >&2
    return 1
  fi

  return 0
}
