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

  # adlc_remote_high re-derives the remote footprint (branches + merged artifact dirs).
  # If the remote high-water is >= our number, SOMETHING at-or-above this id exists on
  # the remote. That alone is not proof THIS exact id is taken — but combined with the
  # exact-id branch/dir probe below it is. We do BOTH: the cheap high-water short-circuit
  # plus an exact-id presence probe so we don't false-halt merely because a HIGHER id
  # was allocated elsewhere.
  ADLC_ALLOC_DEGRADED=""
  adlc_rc_high=$(adlc_remote_high "$adlc_rc_kind")
  adlc_rc_high=$(adlc_id_dec "$adlc_rc_high")

  if [ -n "$ADLC_ALLOC_DEGRADED" ]; then
    echo "WARNING: remote unreachable during recheck of $adlc_rc_id — proceeding WITHOUT remote verification (BR-3)." >&2
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
  for adlc_rc_repo in "$adlc_rc_root"/*; do
    [ -d "$adlc_rc_repo/.git" ] || [ -f "$adlc_rc_repo/.git" ] || continue
    git -C "$adlc_rc_repo" remote get-url origin >/dev/null 2>&1 || continue

    if [ -n "$adlc_rc_branch_grep" ]; then
      adlc_rc_refs=$(git -C "$adlc_rc_repo" ls-remote --heads origin 2>/dev/null) || continue
      # Extract every branch number, normalize to decimal, exact-match against our num.
      # `grep -qx` on the normalized list avoids fragile subshell-exit tricks (zsh-safe).
      adlc_rc_branch_nums=$(printf '%s\n' "$adlc_rc_refs" \
        | grep -oE "$adlc_rc_branch_grep" | grep -oE '[0-9][0-9]*' \
        | while IFS= read -r adlc_rc_seen; do adlc_id_dec "$adlc_rc_seen"; done)
      if printf '%s\n' "$adlc_rc_branch_nums" | grep -qx "$adlc_rc_num"; then
        adlc_rc_hit="$adlc_rc_repo (pushed branch)"
        break
      fi
    fi

    # Merged artifact dir/file probe via gh api (when available). Artifact dirs/files
    # carry the UPPERCASE prefix (REQ-/BUG-/LESSON-).
    if command -v gh >/dev/null 2>&1; then
      adlc_rc_url=$(git -C "$adlc_rc_repo" remote get-url origin 2>/dev/null)
      adlc_rc_owner=$(printf '%s' "$adlc_rc_url" \
        | sed -E 's#^git@github.com:##; s#^https://github.com/##; s#\.git$##')
      if printf '%s' "$adlc_rc_owner" | grep -qE '^[^/]+/[^/]+$'; then
        case "$adlc_rc_kind" in
          req)    adlc_rc_path=".adlc/specs" ;;
          bug)    adlc_rc_path=".adlc/bugs" ;;
          lesson) adlc_rc_path=".adlc/knowledge/lessons" ;;
        esac
        adlc_rc_names=$(gh api "repos/$adlc_rc_owner/contents/$adlc_rc_path" --jq '.[].name' 2>/dev/null)
        adlc_rc_art_nums=$(printf '%s\n' "$adlc_rc_names" \
          | grep -oE "$adlc_rc_prefix-[0-9]+" | sed -E "s/^$adlc_rc_prefix-//" \
          | while IFS= read -r adlc_rc_seen; do adlc_id_dec "$adlc_rc_seen"; done)
        if printf '%s\n' "$adlc_rc_art_nums" | grep -qx "$adlc_rc_num"; then
          adlc_rc_hit="$adlc_rc_repo (merged artifact)"
          break
        fi
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
