# partials/lane-check.sh — the lite lane's mechanical diff check (REQ-652 BR-6).
#
# Source this partial, then call adlc_lane_check WITHIN THE SAME fenced block, after the
# fence's ToolkitRoot root line (conventions.md "Bash in skills"):
#   if [ -f .adlc/partials/lane-check.sh ]; then . .adlc/partials/lane-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lane-check.sh"; fi
#   git -C "$worktree" fetch origin "$integration_branch"     # caller refreshes the base
#   adlc_lane_check "$worktree" "origin/$integration_branch"; rc=$?
#   case $rc in
#     0) : ;;                     # pass — the change stayed inside the lite lane
#     *) echo "crossed a line" ;; # 1 escalate, 2 error — an error is never a pass
#   esac
#
# Contract — adlc_lane_check <worktree> <base-ref>:
#   stdout: the engine's normalized lines — `lane_check=<pass|escalate|error>`,
#           `files_counted=<n>`, then one `trigger=<t>` / `detail=<d>` pair per failing fact
#   return 0 -> pass; 1 -> escalate; 2 -> error (dirty tree, git failure, bad config, usage,
#           engine or interpreter missing, or an engine run that ended any other way)
# The wrapper adds no line and swallows no stderr. When the engine exits 0, 1 or 2 and its
# first line is the verdict that code means, stdout and the code pass through unchanged.
# Anything else — an exit code outside 0-2 (127 interpreter missing, 137 killed, ...), or a
# code whose first line does not match it — is replaced by the three-line error contract
# (`lane_check=error`, `trigger=check-error`, `detail=...`) and rc 2: an error is never a
# pass (LESSON-581). It does NOT fetch; the caller passes an already-fetched
# `origin/<integrationBranch>` (LESSON-391, never local `main`). Full contract, rule table,
# defaults and the closed vocabulary: partials/lane-check.md.
#
# The engine is ALWAYS the installed toolkit's, <ToolkitRoot>/tools/adlc/lane_check.py —
# never a copy in the tree under check, which could certify itself (REQ-652 review M1,
# LESSON-718). ToolkitRoot is installed by definition: the fence's root line resolves
# ADLC_TOOLKIT_ROOT to the plugin's cache copy or to the clone behind the ~/.claude/skills
# symlink, never to the branch under review (REQ-669 ADR-2). Unset, it defaults to that
# symlink install, so a caller that never ran the root line keeps today's behavior.
# The toolkit's own tests point HOME (or ADLC_TOOLKIT_ROOT) at a sandbox install that is
# the checkout under test.
#
# POSIX only, dash-clean: prefixed globals (no `local`), no arrays, no `case` inside
# `$( )` (LESSON-582).

# The interpreter comes from forge.sh's `_adlc_forge_python`, so the forge adapter
# and the lane check never pick different Pythons (the delegate venv when it has
# PyYAML, else `python3`). Calling a `_`-prefixed function from another partial is a
# documented coupling (REQ-652 ADR-3); extracting the resolver into its own partial
# is a follow-up. forge.sh is sourced with the guarded two-level spelling, and only
# when the function is not already defined; adlc_lane_check re-checks that it is.
# The fallback operand reads a bare $HOME, so it is not reached when neither
# ADLC_TOOLKIT_ROOT nor HOME is set: a `set -u` caller would abort on it. The
# partial then loads without the resolver, and adlc_lane_check reports that.
if ! command -v _adlc_forge_python >/dev/null 2>&1 && { [ -n "${ADLC_TOOLKIT_ROOT:-}${HOME+x}" ] || [ -f .adlc/partials/forge.sh ]; }; then
  if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/forge.sh"; fi
fi

# _adlc_lane_check_error <detail> — the three-line error contract on stdout.
_adlc_lane_check_error() {
  printf 'lane_check=error\ntrigger=check-error\ndetail=%s\n' "$1"
}

adlc_lane_check() {
  adlc_lc_wt=$1
  adlc_lc_base=$2
  if [ -z "$adlc_lc_wt" ] || [ -z "$adlc_lc_base" ]; then
    echo "adlc_lane_check: usage: adlc_lane_check <worktree> <base-ref>" >&2
    _adlc_lane_check_error 'usage: adlc_lane_check <worktree> <base-ref>'
    return 2
  fi
  # The installed toolkit's engine, and only that one: ToolkitRoot's.
  # The root must be absolute: a relative one would resolve "installed" inside the
  # tree under check. With ADLC_TOOLKIT_ROOT unset the root comes from HOME, so HOME
  # is checked first, which also keeps an unset HOME from aborting a `set -u` caller.
  if [ -z "${ADLC_TOOLKIT_ROOT:-}" ]; then
    case "${HOME:-}" in
      /*) ;;
      *)
        echo "adlc_lane_check: HOME is not an absolute path ('${HOME:-}')" >&2
        _adlc_lane_check_error 'HOME is not an absolute path'
        return 2
        ;;
    esac
  fi
  adlc_lc_script="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/lane_check.py"
  case "$adlc_lc_script" in
    /*) ;;
    *)
      echo "adlc_lane_check: ADLC_TOOLKIT_ROOT is not an absolute path ('$ADLC_TOOLKIT_ROOT')" >&2
      _adlc_lane_check_error 'ADLC_TOOLKIT_ROOT is not an absolute path'
      return 2
      ;;
  esac
  # An engine inside the tree under check is that tree's own copy, whatever the
  # root says (ADLC_TOOLKIT_ROOT pointed at the worktree, or at a copy vendored in
  # it): it could certify itself (LESSON-718). Both sides are resolved with
  # `cd -P`, so a symlink on either side is followed before the prefix test. A
  # worktree that does not resolve is left to the engine, which reports it.
  adlc_lc_eng_dir=$(CDPATH= cd -P -- "${adlc_lc_script%/*}" 2>/dev/null && pwd -P) || adlc_lc_eng_dir=
  adlc_lc_wt_dir=$(CDPATH= cd -P -- "$adlc_lc_wt" 2>/dev/null && pwd -P) || adlc_lc_wt_dir=
  if [ -n "$adlc_lc_eng_dir" ] && [ -n "$adlc_lc_wt_dir" ]; then
    adlc_lc_inside=0
    case "$adlc_lc_eng_dir" in
      "$adlc_lc_wt_dir" | "$adlc_lc_wt_dir"/*) adlc_lc_inside=1 ;;
    esac
    if [ "$adlc_lc_wt_dir" = / ]; then adlc_lc_inside=1; fi
    if [ "$adlc_lc_inside" = 1 ]; then
      echo "adlc_lane_check: the engine at ${adlc_lc_script%/lane_check.py}/ is inside the worktree under check ($adlc_lc_wt); it would check itself — point ADLC_TOOLKIT_ROOT at the installed toolkit" >&2
      _adlc_lane_check_error 'the engine is inside the worktree under check'
      return 2
    fi
  fi
  if [ ! -f "$adlc_lc_script" ]; then
    echo "adlc_lane_check: lane_check.py not found at ${adlc_lc_script%/lane_check.py}/ — install the toolkit (symlink route: ./install.sh; plugin route: claude plugin install adlc@adlc-toolkit)" >&2
    _adlc_lane_check_error 'lane_check.py not found in the installed toolkit'
    return 2
  fi
  if ! command -v _adlc_forge_python >/dev/null 2>&1; then
    echo "adlc_lane_check: _adlc_forge_python is not defined (forge.sh did not load)" >&2
    _adlc_lane_check_error 'interpreter resolver _adlc_forge_python is not defined'
    return 2
  fi
  adlc_lc_py=$(_adlc_forge_python)
  if [ -z "$adlc_lc_py" ]; then
    _adlc_lane_check_error 'interpreter resolver _adlc_forge_python printed nothing'
    return 2
  fi
  # `command` so a shell function named `python3` cannot intercept the call (REQ-609 D5).
  # stdout is captured so it can be withheld when the run did not end in the contract;
  # stderr is not touched.
  # `-E` ignores PYTHONPATH and friends, so an empty PYTHONPATH entry (the current
  # directory, which is the tree under check) cannot shadow a standard-library
  # module. Not `-I`: that also drops user site-packages, where PyYAML may live.
  adlc_lc_out=$(command "$adlc_lc_py" -E "$adlc_lc_script" --worktree "$adlc_lc_wt" --base "$adlc_lc_base")
  adlc_lc_rc=$?
  adlc_lc_nl='
'
  adlc_lc_head=${adlc_lc_out%%"$adlc_lc_nl"*}
  case $adlc_lc_rc in
    0) adlc_lc_want='lane_check=pass' ;;
    1) adlc_lc_want='lane_check=escalate' ;;
    2) adlc_lc_want='lane_check=error' ;;
    *) adlc_lc_want= ;;
  esac
  if [ -z "$adlc_lc_want" ]; then
    _adlc_lane_check_error "lane_check.py exited $adlc_lc_rc"
    return 2
  fi
  if [ "$adlc_lc_head" != "$adlc_lc_want" ]; then
    _adlc_lane_check_error "lane_check.py exited $adlc_lc_rc without a $adlc_lc_want line"
    return 2
  fi
  printf '%s\n' "$adlc_lc_out"
  return "$adlc_lc_rc"
}
