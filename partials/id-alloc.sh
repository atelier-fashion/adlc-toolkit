# partials/id-alloc.sh — collision-safe id allocation, remote as source of truth (REQ-518).
#
# Source this partial, then call adlc_alloc_id WITHIN THE SAME fenced block:
#   . .adlc/partials/id-alloc.sh 2>/dev/null || . ~/.claude/skills/partials/id-alloc.sh
#   REQ_NUM=$(adlc_alloc_id req)
#   # `exit 1` inside adlc_alloc_id's subshell terminates only the subshell — REQ_NUM
#   # would be silently empty. Guard the parent context (REQ-416 verify D-pass).
#   [ -n "$REQ_NUM" ] || { echo "ERROR: failed to allocate REQ number — aborting" >&2; exit 1; }
#
# The three counters (req/bug/lesson) share ONE allocation helper parameterized by
# kind (BR-5), replacing the near-identical inline blocks in /spec, /bugfix, /wrapup.
# Allocation order (BR-1): derive remote high-water -> max(remote, local) -> allocate
# max+1 -> fast-forward the local counter, all inside the existing mkdir lock with its
# symlink/TOCTOU guards intact. The local counter is a CACHE, not an authority.
#
# Functions exported:
#   adlc_id_kind_counter <kind>   -> prints the ~/.claude counter path for the kind
#   adlc_id_kind_lockdir <kind>   -> prints the mkdir-lock dir path for the kind
#   adlc_id_kind_prefix  <kind>   -> prints the id prefix (REQ|BUG|LESSON)
#   adlc_id_kind_scan    <kind>   -> prints "<find-path-glob> <find-type>" for bootstrap
#   adlc_remote_high     <kind>   -> prints the remote high-water number (0 if none/unreachable)
#   adlc_alloc_id        <kind>   -> prints max(local,remote)+1; fast-forwards the counter
#
# Degradation (BR-3): if any configured remote is unreachable, adlc_remote_high prints
# 0, emits a warning on stderr, and sets ADLC_ALLOC_DEGRADED=1 in the CALLER's env so
# the skill can record "id allocated without remote verification — verify before PR".
# Allocation NEVER blocks on network availability.
#
# Portable across sh/bash/zsh (BR-6): prefixed globals (no `local`), no `\b` in grep -E,
# no bare $<digit>, no [0] indexing, no `status=` variable. Modeled on trial-merge.sh.

# --- numeric normalizer -------------------------------------------------------------
# Strip leading zeros so a value is treated as DECIMAL, not octal: in sh/bash/zsh
# `$(( 042 ))` is 34 (octal). Portable across all three (no `10#` bashism). Keeps a
# lone 0 as 0; empty input -> 0.
adlc_id_dec() {
  printf '%s' "${1:-0}" | sed -E 's/^0+([0-9])/\1/' | sed -E 's/^$/0/'
}

# --- kind mappers (one table; three kinds; BR-8 one namespace per kind) -------------

adlc_id_kind_prefix() {
  case "$1" in
    req)    echo "REQ" ;;
    bug)    echo "BUG" ;;
    lesson) echo "LESSON" ;;
    *) echo "adlc_id_kind_prefix: unknown kind '$1' (want req|bug|lesson)" >&2; return 2 ;;
  esac
}

adlc_id_kind_counter() {
  case "$1" in
    req)    echo "$HOME/.claude/.global-next-req" ;;
    bug)    echo "$HOME/.claude/.global-next-bug" ;;
    lesson) echo "$HOME/.claude/.global-next-lesson" ;;
    *) echo "adlc_id_kind_counter: unknown kind '$1'" >&2; return 2 ;;
  esac
}

adlc_id_kind_lockdir() {
  case "$1" in
    req)    echo "$HOME/.claude/.global-next-req.lock.d" ;;
    bug)    echo "$HOME/.claude/.global-next-bug.lock.d" ;;
    lesson) echo "$HOME/.claude/.global-next-lesson.lock.d" ;;
    *) echo "adlc_id_kind_lockdir: unknown kind '$1'" >&2; return 2 ;;
  esac
}

# Prints "<find -path glob> <find -type flag>" for the bootstrap scan. REQ specs are
# directories (-type d); bugs and lessons are .md files (-type f) — deliberate, do not
# "correct" (see /bugfix SKILL.md note).
adlc_id_kind_scan() {
  case "$1" in
    req)    echo "*/.adlc/specs/REQ-* d" ;;
    bug)    echo "*/.adlc/bugs/BUG-* f" ;;
    lesson) echo "*/.adlc/knowledge/lessons/LESSON-* f" ;;
    *) echo "adlc_id_kind_scan: unknown kind '$1'" >&2; return 2 ;;
  esac
}

# --- remote high-water derivation (BR-2) --------------------------------------------
# Reads the REMOTE, not local clones' state — stale local checkouts must not LOWER the
# result. Reuses the /manifest derive-don't-store surface (ADR-2): pushed
# feat/REQ-* / fix/bug-* branch names + merged artifact dirs reachable from default
# branches across the participating repos. Participating repos = checkouts under
# $ADLC_REPOS_ROOT (default: parent of the current repo) that have a remote.
#
# Prints the max number found (0 if none). On an unreachable remote, prints 0, warns,
# and sets ADLC_ALLOC_DEGRADED=1.
adlc_remote_high() {
  adlc_rh_kind=$1
  adlc_rh_prefix=$(adlc_id_kind_prefix "$adlc_rh_kind") || return 2

  # Branch pattern per kind: REQ -> feat/REQ-NNN-, BUG -> fix/bug-NNN- (lesson has no
  # branch of its own; it rides a feat/fix branch, so its remote footprint is the
  # merged lessons dir, scanned below).
  case "$adlc_rh_kind" in
    req)    adlc_rh_branch_re='feat/REQ-[0-9][0-9]*' ;;
    bug)    adlc_rh_branch_re='fix/bug-[0-9][0-9]*' ;;
    lesson) adlc_rh_branch_re='' ;;
  esac

  adlc_rh_root="${ADLC_REPOS_ROOT:-$(cd "$(git rev-parse --show-toplevel 2>/dev/null)/.." 2>/dev/null && pwd)}"
  [ -n "$adlc_rh_root" ] || adlc_rh_root="."

  adlc_rh_max=0
  adlc_rh_saw_remote=0
  adlc_rh_unreachable=""

  # Enumerate participating repos: git checkouts directly under the root that have an
  # `origin` remote. One level deep is the common "all repos under one folder" layout.
  for adlc_rh_repo in "$adlc_rh_root"/*; do
    [ -d "$adlc_rh_repo/.git" ] || [ -f "$adlc_rh_repo/.git" ] || continue
    adlc_rh_url=$(git -C "$adlc_rh_repo" remote get-url origin 2>/dev/null) || continue
    [ -n "$adlc_rh_url" ] || continue
    adlc_rh_saw_remote=1

    # --- pushed branch names (req/bug) via ls-remote on the REMOTE -------------------
    if [ -n "$adlc_rh_branch_re" ]; then
      adlc_rh_refs=$(git -C "$adlc_rh_repo" ls-remote --heads origin 2>/dev/null)
      if [ $? -ne 0 ]; then
        adlc_rh_unreachable="$adlc_rh_unreachable $adlc_rh_url"
        continue
      fi
      # Extract NNN from refs/heads/<branch_re>-...; grep -oE then strip the prefix.
      adlc_rh_nums=$(printf '%s\n' "$adlc_rh_refs" \
        | grep -oE "$adlc_rh_branch_re" \
        | grep -oE '[0-9][0-9]*' )
      for adlc_rh_n in $adlc_rh_nums; do
        # strip any accidental leading zeros for the arithmetic compare (octal trap).
        adlc_rh_n=$(adlc_id_dec "$adlc_rh_n")
        [ "$adlc_rh_n" -gt "$adlc_rh_max" ] && adlc_rh_max=$adlc_rh_n
      done
    fi

    # --- merged artifact dirs/files reachable from the default branch ---------------
    # Prefer gh api (cheap tree read) when available; degrade to ls-remote ref scan of
    # the default branch tip via ls-tree. Either way we read the REMOTE's default
    # branch, never the local working tree.
    adlc_rh_owner=$(printf '%s' "$adlc_rh_url" \
      | sed -E 's#^git@github.com:##; s#^https://github.com/##; s#\.git$##')
    adlc_rh_artifact_nums=""
    if command -v gh >/dev/null 2>&1 && printf '%s' "$adlc_rh_owner" | grep -qE '^[^/]+/[^/]+$'; then
      case "$adlc_rh_kind" in
        req)    adlc_rh_path=".adlc/specs" ;;
        bug)    adlc_rh_path=".adlc/bugs" ;;
        lesson) adlc_rh_path=".adlc/knowledge/lessons" ;;
      esac
      adlc_rh_listing=$(gh api "repos/$adlc_rh_owner/contents/$adlc_rh_path" \
        --jq '.[].name' 2>/dev/null)
      if [ -n "$adlc_rh_listing" ]; then
        adlc_rh_artifact_nums=$(printf '%s\n' "$adlc_rh_listing" \
          | grep -oE "$adlc_rh_prefix-[0-9][0-9]*" \
          | grep -oE '[0-9][0-9]*')
      fi
    fi
    for adlc_rh_n in $adlc_rh_artifact_nums; do
      adlc_rh_n=$(adlc_id_dec "$adlc_rh_n")
      [ "$adlc_rh_n" -gt "$adlc_rh_max" ] && adlc_rh_max=$adlc_rh_n
    done
  done

  if [ -n "$adlc_rh_unreachable" ]; then
    echo "WARNING: remote(s) unreachable during $adlc_rh_prefix high-water derivation:$adlc_rh_unreachable" >&2
    echo "  -> id allocated without full remote verification — verify before PR (BR-3)." >&2
    ADLC_ALLOC_DEGRADED=1
  fi
  if [ "$adlc_rh_saw_remote" -eq 0 ]; then
    echo "WARNING: no participating repo with an origin remote found under '$adlc_rh_root' — local-only allocation (BR-3)." >&2
    ADLC_ALLOC_DEGRADED=1
  fi

  echo "$adlc_rh_max"
}

# --- bootstrap scan (counter absent) ------------------------------------------------
# Local-filesystem high-water across $ADLC_REPOS_ROOT — same as today's inline blocks.
# Only used to SEED an absent counter; remote derivation still runs on top.
adlc_local_scan_high() {
  adlc_ls_kind=$1
  adlc_ls_prefix=$(adlc_id_kind_prefix "$adlc_ls_kind") || return 2
  adlc_ls_scan=$(adlc_id_kind_scan "$adlc_ls_kind") || return 2
  # split "<glob> <type>"
  adlc_ls_glob=${adlc_ls_scan% *}
  adlc_ls_type=${adlc_ls_scan##* }
  adlc_ls_root="${ADLC_REPOS_ROOT:-$(cd "$(git rev-parse --show-toplevel 2>/dev/null)/.." 2>/dev/null && pwd)}"
  [ -n "$adlc_ls_root" ] || adlc_ls_root="."
  adlc_ls_high=$(find "$adlc_ls_root" -path "$adlc_ls_glob" -type "$adlc_ls_type" 2>/dev/null \
    | grep -oE "$adlc_ls_prefix-[0-9]+" | sed "s/$adlc_ls_prefix-//" | sort -n | tail -1)
  # Normalize to decimal — `$(( 042 + 1 ))` is 35 in sh/bash because a leading 0 means
  # octal (adlc_id_dec strips leading zeros portably).
  adlc_id_dec "${adlc_ls_high:-0}"
}

# --- the allocator (BR-1) -----------------------------------------------------------
# Prints the allocated NUMBER (not the prefixed id) on stdout. The lock block is ported
# VERBATIM from /spec Step 2 (REQ-416 verify rationale comments preserved — LESSON-023),
# extended only with the remote high-water max.
adlc_alloc_id() {
  adlc_ai_kind=$1
  adlc_ai_counter=$(adlc_id_kind_counter "$adlc_ai_kind") || return 2
  adlc_ai_lock=$(adlc_id_kind_lockdir "$adlc_ai_kind") || return 2

  # Remote high-water is derived OUTSIDE the lock — it makes network calls that must
  # not hold the mkdir lock for seconds; the lock only guards the local read/write.
  adlc_ai_remote=$(adlc_remote_high "$adlc_ai_kind")

  adlc_ai_num=$(
    LOCK="$adlc_ai_lock"
    COUNTER="$adlc_ai_counter"
    REMOTE_HIGH="$adlc_ai_remote"
    KIND="$adlc_ai_kind"
    if [ -L "$LOCK" ]; then
      echo "ERROR: $LOCK is a symlink — refusing (TOCTOU risk). Inspect manually." >&2
      exit 1
    fi
    for _ in $(seq 50); do mkdir "$LOCK" 2>/dev/null && break; sleep 0.1; done
    # Hard-fail if we never acquired the lock (50 retries × 0.1s = ~5s budget).
    # Without this guard, a contended lock would silently fall through to the
    # critical section unguarded — defeating mutual exclusion (REQ-416 verify C1).
    [ -d "$LOCK" ] || { echo "ERROR: failed to acquire $LOCK after 50 retries — aborting to avoid duplicate id" >&2; exit 1; }

    # Counter read inside lock. If the counter is ABSENT, bootstrap-seed it from the
    # local filesystem scan (same as today). If it exists but is unreadable/empty mid
    # critical-section, fail hard rather than silently resetting the global counter
    # (REQ-416 verify M2).
    if [ -f "$COUNTER" ]; then
      NUM=$(cat "$COUNTER" 2>/dev/null) || { echo "ERROR: counter $COUNTER unreadable inside lock — aborting" >&2; rmdir "$LOCK" 2>/dev/null; exit 1; }
      [ -n "$NUM" ] || { echo "ERROR: counter $COUNTER is empty — aborting (would reset to 1)" >&2; rmdir "$LOCK" 2>/dev/null; exit 1; }
    else
      NUM=$(( $(adlc_local_scan_high "$KIND") + 1 ))
    fi

    # The collision-safe step (BR-1): the local counter is a cache. Take the max of the
    # remotely-derived high-water and the local counter value, then allocate max+1.
    # Normalize both to decimal first (octal trap on any stray leading zero).
    NUM=$(adlc_id_dec "$NUM")
    REMOTE_HIGH=$(adlc_id_dec "$REMOTE_HIGH")
    LOCAL_HIGH=$(( NUM - 1 ))
    HIGH=$LOCAL_HIGH
    [ "$REMOTE_HIGH" -gt "$HIGH" ] && HIGH=$REMOTE_HIGH
    ALLOC=$(( HIGH + 1 ))

    # Fast-forward the local counter to one past the allocated id.
    echo $(( ALLOC + 1 )) > "$COUNTER"

    # rmdir is guarded by the same symlink check (residual TOCTOU window between
    # check and rmdir is accepted risk per ADR-4 — see LESSON-014).
    if [ ! -L "$LOCK" ]; then rmdir "$LOCK" 2>/dev/null; fi
    echo "$ALLOC"
  )
  # `exit 1` inside the $(...) subshell terminates only the subshell — adlc_ai_num
  # would be silently empty. The CALLER must also guard (see header usage example).
  [ -n "$adlc_ai_num" ] || { echo "ERROR: failed to allocate $adlc_ai_kind number" >&2; return 1; }
  echo "$adlc_ai_num"
}
