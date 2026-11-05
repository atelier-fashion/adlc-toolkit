# partials/regression-check.sh — the regression-test setting and check, for /bugfix's
# fences (REQ-691; the engine is TASK-238's tools/adlc/regression_check.py).
#
# Source this partial, then call adlc_regression_check WITHIN THE SAME fenced block, after
# the fence's ToolkitRoot root line (conventions.md "Bash in skills"):
#   if [ -f .adlc/partials/regression-check.sh ]; then . .adlc/partials/regression-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/regression-check.sh"; fi
#   adlc_regression_check mode; rc=$?
#   case $rc in
#     0) : ;;                     # `regression-test: required` or `regression-test: off`
#     *) echo "stop" ;;           # 2 error: the setting is unreadable — never read as off
#   esac
#   adlc_regression_check check --require-recorded --base refs/remotes/origin/main BUG-123; rc=$?
#   case $rc in
#     0) : ;;                     # `regression-check: pass` or `regression-check: off`
#     *) echo "stop" ;;           # 1 fail, 2 error — an error is never a pass and never off
#   esac
#
# Contract — adlc_regression_check <mode|check> [args...]:
#   runs <ToolkitRoot>/tools/adlc/regression_check.py with the arguments unchanged
#   (`--base REF`, a full refs/remotes/... or refs/heads/... ref, reads the setting from
#   REF's config; the /bugfix Gate passes refs/remotes/origin/<integration-branch>).
#   mode  stdout: `regression-test: required|off`, then where the value came from (set,
#                 absent, or no config file); rc 0. `regression-test: error`, then why; rc 2.
#   check stdout: `regression-check: pass|fail`, then `passed=N waived=N legacy=N failed=N`,
#                 then one `BUG-nnn: <reason>` line per failed bug; rc 0 pass, 1 fail.
#                 `regression-check: off`, then the line saying regression tests are off; rc 0.
#                 `regression-check: error`, then why, with no counts line; rc 2.
# The wrapper adds no line and swallows no stderr. When the engine exits with a code the
# verb's contract has, and its first line is a verdict that code means for that verb,
# stdout and the code pass through unchanged. Anything else — an exit code outside the
# verb's contract (127 interpreter missing, 137 killed, 1 from `mode`, ...), or a code whose
# first line does not match it (no output at all, the other verb's verdict, a pass line
# with rc 1) — is replaced by the two-line error contract (`regression-check: error`, or
# `regression-test: error` for `mode`, then one reason line) and rc 2: an error is never a
# pass and never off (BR-17, LESSON-581). The engine has no --help for the same reason.
# One answer needs no engine: with no `.adlc/config.yml` in the tree under check and no
# `--base`, the wrapper prints the engine's own no-config `off` lines, rc 0, so such a
# run needs no Python. A run with `--base REF` always goes to the engine, and so needs
# Python: the /bugfix Gate answers a base with no config itself, with `git cat-file`,
# before it calls the wrapper. A `--root` with a `..` segment also goes to the engine.
# Full contract: partials/regression-check.md.
#
# The engine is ALWAYS the installed toolkit's, <ToolkitRoot>/tools/adlc/regression_check.py —
# never a copy in the tree under check, which could certify itself, or turn its own gate
# off (LESSON-718). ToolkitRoot is installed by definition: the fence's root line resolves
# ADLC_TOOLKIT_ROOT to the plugin's cache copy or to the clone behind the ~/.claude/skills
# symlink, never to the branch under review (REQ-669 ADR-2). Unset, it defaults to that
# symlink install, so a caller that never ran the root line keeps today's behavior.
# The tree under check is the engine's project root: the last `--root DIR` (or
# `--root=DIR`) before any `--`, else the current directory, as the engine reads it.
# The toolkit's own tests point HOME (or ADLC_TOOLKIT_ROOT) at a sandbox install that is
# the checkout under test.
#
# POSIX only, dash-clean: prefixed globals (no `local`), no arrays, no `case` inside
# `$( )` (LESSON-582).

# The interpreter comes from forge.sh's `_adlc_forge_python`, so the forge adapter,
# the lane check and the regression check never pick different Pythons (the delegate
# venv when it has PyYAML, else `python3`). Calling a `_`-prefixed function from
# another partial is a documented coupling (REQ-652 ADR-3); extracting the resolver
# into its own partial is a follow-up. forge.sh comes from the installed toolkit ONLY,
# never from `.adlc/partials/forge.sh` in the current directory: the resolver picks
# the interpreter that runs the engine, so a copy in the tree under check would pick
# what judges that tree (LESSON-718), and a stale vendored copy without the resolver
# can no longer be the one loaded either. It is sourced only when the function is
# not already defined (a fence that sourced forge.sh itself keeps its own), behind a
# `[ -f ]` guard; adlc_regression_check re-checks that it is defined. The operand
# reads a bare $HOME, so it is not reached when neither ADLC_TOOLKIT_ROOT nor HOME is
# set: a `set -u` caller would abort on it. The partial then loads without the
# resolver, and adlc_regression_check reports that.
if ! command -v _adlc_forge_python >/dev/null 2>&1 && [ -n "${ADLC_TOOLKIT_ROOT:-}${HOME+x}" ]; then
  adlc_rgc_forge="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/forge.sh"
  if [ -f "$adlc_rgc_forge" ]; then . "$adlc_rgc_forge"; fi
fi

# _adlc_regression_check_error <verdict-prefix> <detail> — the two-line error contract
# on stdout: the verb's error verdict, then one reason line (the engine's own shape).
_adlc_regression_check_error() {
  printf '%serror\n%s\n' "$1" "$2"
}

adlc_regression_check() {
  adlc_rgc_verb=${1-}
  # The error verdict names the verb's line, as the engine's does: `mode` reports
  # `regression-test: error`, everything else `regression-check: error`.
  case "$adlc_rgc_verb" in
    mode) adlc_rgc_prefix='regression-test: ' ;;
    *) adlc_rgc_prefix='regression-check: ' ;;
  esac
  case "$adlc_rgc_verb" in
    mode | check) ;;
    *)
      echo "adlc_regression_check: usage: adlc_regression_check <mode|check> [args...]" >&2
      _adlc_regression_check_error "$adlc_rgc_prefix" 'usage: adlc_regression_check <mode|check> [args...]'
      return 2
      ;;
  esac
  # The installed toolkit's engine, and only that one: ToolkitRoot's.
  # The root must be absolute: a relative one would resolve "installed" inside the
  # tree under check. With ADLC_TOOLKIT_ROOT unset the root comes from HOME, so HOME
  # is checked first, which also keeps an unset HOME from aborting a `set -u` caller.
  if [ -z "${ADLC_TOOLKIT_ROOT:-}" ]; then
    case "${HOME:-}" in
      /*) ;;
      *)
        echo "adlc_regression_check: HOME is not an absolute path ('${HOME:-}')" >&2
        _adlc_regression_check_error "$adlc_rgc_prefix" 'HOME is not an absolute path'
        return 2
        ;;
    esac
  fi
  adlc_rgc_script="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/regression_check.py"
  case "$adlc_rgc_script" in
    /*) ;;
    *)
      echo "adlc_regression_check: ADLC_TOOLKIT_ROOT is not an absolute path ('${ADLC_TOOLKIT_ROOT:-}')" >&2
      _adlc_regression_check_error "$adlc_rgc_prefix" 'ADLC_TOOLKIT_ROOT is not an absolute path'
      return 2
      ;;
  esac
  # stderr names the engine by route, never by an absolute path under HOME.
  if [ -n "${ADLC_TOOLKIT_ROOT:-}" ]; then
    adlc_rgc_where='<ToolkitRoot>/tools/adlc/regression_check.py (ToolkitRoot from ADLC_TOOLKIT_ROOT)'
  else
    adlc_rgc_where='<ToolkitRoot>/tools/adlc/regression_check.py (ToolkitRoot is the symlink install under HOME)'
  fi
  # The tree under check is the project root the engine will read, found the way
  # its argument parser finds it: the LAST `--root DIR` or `--root=DIR` wins, an
  # empty value means the current directory (os.path.abspath('')), nothing after a
  # `--` is an option, and with no `--root` it is the current directory. Reading it
  # any other way would let a second `--root` move the engine's root past the test.
  # adlc_rgc_plain stays 1 only while every argument is one the no-config answer
  # below can stand in for: `--root`, and for `check` `--require-recorded` and ids
  # of BUG- and ASCII digits. Anything else (`--base`, `--`, an unknown option, an
  # option-like `--root` value the engine's parser would reject) goes to the engine.
  adlc_rgc_root=.
  adlc_rgc_want_value=0
  adlc_rgc_plain=1
  adlc_rgc_seen_verb=0
  for adlc_rgc_arg in "$@"; do
    # The first argument is the verb itself, already checked above.
    if [ "$adlc_rgc_seen_verb" = 0 ]; then
      adlc_rgc_seen_verb=1
      continue
    fi
    if [ "$adlc_rgc_want_value" = 1 ]; then
      adlc_rgc_root=$adlc_rgc_arg
      adlc_rgc_want_value=0
      case "$adlc_rgc_arg" in -*) adlc_rgc_plain=0 ;; esac
      continue
    fi
    case "$adlc_rgc_arg" in
      --) adlc_rgc_plain=0; break ;;
      --root) adlc_rgc_want_value=1 ;;
      --root=*) adlc_rgc_root=${adlc_rgc_arg#--root=} ;;
      --require-recorded) [ "$adlc_rgc_verb" = check ] || adlc_rgc_plain=0 ;;
      BUG-*)
        adlc_rgc_digits=${adlc_rgc_arg#BUG-}
        case "$adlc_rgc_verb:$adlc_rgc_digits" in
          check:*[!0-9]* | check: | mode:*) adlc_rgc_plain=0 ;;
        esac
        ;;
      *) adlc_rgc_plain=0 ;;
    esac
  done
  if [ "$adlc_rgc_want_value" = 1 ]; then adlc_rgc_plain=0; fi
  if [ -z "$adlc_rgc_root" ]; then adlc_rgc_root=.; fi
  # A `..` segment is where `cd -P` and the engine part ways: the shell resolves it
  # physically, after following any symlink before it, and the engine
  # (os.path.abspath) lexically, by dropping the segment before it. `--root
  # proj/link/..` would be the link target's parent to the tests below and `proj`
  # to the engine, so an engine inside `proj` would never be seen. Such a root
  # therefore goes to the engine, never to the no-config answer, and the tests below
  # see it the engine's way: made absolute against the physical current directory
  # (os.getcwd), normalized segment by segment as os.path.normpath does, and only
  # then resolved with `cd -P`. A current directory that cannot be named leaves
  # the root unresolved, which the engine reports.
  adlc_rgc_resolve=1
  case "/$adlc_rgc_root/" in
    */../*)
      adlc_rgc_plain=0
      case "$adlc_rgc_root" in
        /*) adlc_rgc_rest=$adlc_rgc_root ;;
        *)
          adlc_rgc_cwd=$(pwd -P 2>/dev/null) || adlc_rgc_cwd=
          if [ -z "$adlc_rgc_cwd" ]; then adlc_rgc_resolve=0; fi
          adlc_rgc_rest="$adlc_rgc_cwd/$adlc_rgc_root"
          ;;
      esac
      adlc_rgc_lex=
      while [ -n "$adlc_rgc_rest" ]; do
        adlc_rgc_seg=${adlc_rgc_rest%%/*}
        case "$adlc_rgc_rest" in
          */*) adlc_rgc_rest=${adlc_rgc_rest#*/} ;;
          *) adlc_rgc_rest= ;;
        esac
        case "$adlc_rgc_seg" in
          '' | .) ;;
          ..) adlc_rgc_lex=${adlc_rgc_lex%/*} ;;
          *) adlc_rgc_lex="$adlc_rgc_lex/$adlc_rgc_seg" ;;
        esac
      done
      adlc_rgc_root=${adlc_rgc_lex:-/}
      ;;
  esac
  # An engine inside the tree under check is that tree's own copy, whatever the
  # root says (ADLC_TOOLKIT_ROOT pointed at the worktree, or at a copy vendored in
  # it): it could certify itself, or print `off` and skip its own gate (LESSON-718).
  # Both sides are resolved with `cd -P`, so a symlink on either side is followed
  # before the prefix test. A root that does not resolve is left to the engine,
  # which reports it as an error.
  adlc_rgc_eng_dir=$(CDPATH= cd -P -- "${adlc_rgc_script%/*}" 2>/dev/null && pwd -P) || adlc_rgc_eng_dir=
  adlc_rgc_root_dir=
  if [ "$adlc_rgc_resolve" = 1 ]; then
    adlc_rgc_root_dir=$(CDPATH= cd -P -- "$adlc_rgc_root" 2>/dev/null && pwd -P) || adlc_rgc_root_dir=
  fi
  if [ -n "$adlc_rgc_eng_dir" ] && [ -n "$adlc_rgc_root_dir" ]; then
    adlc_rgc_inside=0
    case "$adlc_rgc_eng_dir" in
      "$adlc_rgc_root_dir" | "$adlc_rgc_root_dir"/*) adlc_rgc_inside=1 ;;
    esac
    # On a case-insensitive filesystem (macOS by default) `pwd -P` keeps the case
    # a path was typed in under bash and /bin/sh, so the same directory can come
    # back in two spellings. The paths are compared case-folded as well, and
    # either comparison saying inside refuses: on doubt, refuse.
    adlc_rgc_eng_fold=$(printf '%s' "$adlc_rgc_eng_dir" | command tr '[:upper:]' '[:lower:]')
    adlc_rgc_root_fold=$(printf '%s' "$adlc_rgc_root_dir" | command tr '[:upper:]' '[:lower:]')
    case "$adlc_rgc_eng_fold" in
      "$adlc_rgc_root_fold" | "$adlc_rgc_root_fold"/*) adlc_rgc_inside=1 ;;
    esac
    if [ "$adlc_rgc_root_dir" = / ]; then adlc_rgc_inside=1; fi
    # One exemption, for `mode` only: the symlink install's own checkout. When
    # ~/.claude/skills resolves to the tree under check and the engine is that
    # install's (no ADLC_TOOLKIT_ROOT pointing anywhere else), the tree IS the
    # installed toolkit: the skill text reading the setting is read from the same
    # tree, so refusing protects nothing, and it would stop /bugfix on the toolkit
    # itself before Phase 1. `check` is the gate, and a gate never runs in the
    # tree it judges: the toolkit's own /bugfix runs its Gate from a fix worktree,
    # which does not contain the installed engine. A root named by
    # ADLC_TOOLKIT_ROOT, a vendored copy, or any other tree stays refused.
    if [ "$adlc_rgc_inside" = 1 ] && [ "$adlc_rgc_verb" = mode ] && [ -n "${HOME:-}" ]; then
      adlc_rgc_sym_dir=$(CDPATH= cd -P -- "$HOME/.claude/skills" 2>/dev/null && pwd -P) || adlc_rgc_sym_dir=  # adlc-home: alias
      if [ -n "$adlc_rgc_sym_dir" ] && [ "$adlc_rgc_sym_dir" = "$adlc_rgc_root_dir" ] && [ "$adlc_rgc_eng_dir" = "$adlc_rgc_sym_dir/tools/adlc" ]; then
        adlc_rgc_tk_dir=$adlc_rgc_sym_dir
        if [ -n "${ADLC_TOOLKIT_ROOT:-}" ]; then
          adlc_rgc_tk_dir=$(CDPATH= cd -P -- "$ADLC_TOOLKIT_ROOT" 2>/dev/null && pwd -P) || adlc_rgc_tk_dir=
        fi
        if [ "$adlc_rgc_tk_dir" = "$adlc_rgc_sym_dir" ]; then adlc_rgc_inside=0; fi
      fi
    fi
    if [ "$adlc_rgc_inside" = 1 ]; then
      echo "adlc_regression_check: the engine, $adlc_rgc_where, is inside the tree under check (the --root, else the current directory); it would check itself — point ADLC_TOOLKIT_ROOT at the installed toolkit, or run from a tree that does not contain it (a fix worktree, for the gate)" >&2
      _adlc_regression_check_error "$adlc_rgc_prefix" 'the engine is inside the tree under check'
      return 2
    fi
  fi
  # No config and no `--base`: the answer is the engine's no-config `off`, which
  # needs no interpreter, so a project that never named the setting never needs
  # Python. The lines are the engine's, byte for byte (the harness compares them
  # with a real run). The shortcut holds only where the engine would read the same
  # thing: a resolved root, arguments it can stand in for, no `.adlc/config.yml`
  # (nor a symlink there, which the engine reads as an error), and a `.adlc` that
  # is absent or a searchable real directory. Anything else goes to the engine.
  if [ "$adlc_rgc_plain" = 1 ] && [ -n "$adlc_rgc_root_dir" ]; then
    adlc_rgc_cfg="$adlc_rgc_root_dir/.adlc"
    if [ ! -L "$adlc_rgc_cfg/config.yml" ] && [ ! -e "$adlc_rgc_cfg/config.yml" ] && [ ! -L "$adlc_rgc_cfg" ] && { [ ! -e "$adlc_rgc_cfg" ] || { [ -d "$adlc_rgc_cfg" ] && [ -x "$adlc_rgc_cfg" ]; }; }; then
      adlc_rgc_why='.adlc/config.yml does not exist, which means off; set bugfix.regression_test: required in it to turn regression tests on'
      if [ "$adlc_rgc_verb" = mode ]; then
        printf 'regression-test: off\n%s\n' "$adlc_rgc_why"
      else
        printf 'regression-check: off\nregression tests are off for this project: %s\n' "$adlc_rgc_why"
      fi
      return 0
    fi
  fi
  if [ ! -f "$adlc_rgc_script" ]; then
    echo "adlc_regression_check: regression_check.py not found at $adlc_rgc_where — the installed toolkit predates REQ-691 or is not installed (symlink route: ./install.sh, or git pull the clone; plugin route: claude plugin install adlc@adlc-toolkit)" >&2
    _adlc_regression_check_error "$adlc_rgc_prefix" 'regression_check.py not found in the installed toolkit'
    return 2
  fi
  if ! command -v _adlc_forge_python >/dev/null 2>&1; then
    echo "adlc_regression_check: _adlc_forge_python is not defined (forge.sh did not load)" >&2
    _adlc_regression_check_error "$adlc_rgc_prefix" 'interpreter resolver _adlc_forge_python is not defined'
    return 2
  fi
  adlc_rgc_py=$(_adlc_forge_python)
  if [ -z "$adlc_rgc_py" ]; then
    _adlc_regression_check_error "$adlc_rgc_prefix" 'interpreter resolver _adlc_forge_python printed nothing'
    return 2
  fi
  # `command` so a shell function named `python3` cannot intercept the call (REQ-609 D5).
  # stdout is captured so it can be withheld when the run did not end in the contract;
  # stderr is not touched.
  # `-E` ignores PYTHONPATH and friends, so an empty PYTHONPATH entry (the current
  # directory, which is the tree under check) cannot shadow a standard-library
  # module. Not `-I`: the call keeps lane-check.sh's spelling, under which the
  # delegate venv's user site-packages stay reachable; this engine needs only the
  # standard library and its sibling harness_yaml.py (ADR-691-A), which it puts on
  # sys.path itself from its own directory.
  adlc_rgc_out=$(command "$adlc_rgc_py" -E "$adlc_rgc_script" "$@")
  adlc_rgc_rc=$?
  adlc_rgc_nl='
'
  adlc_rgc_head=${adlc_rgc_out%%"$adlc_rgc_nl"*}
  # The verdicts each code means, per verb. `mode` never exits 1, so a 1 from it is
  # outside its contract. A second verdict is empty when the code has only one.
  adlc_rgc_want=
  adlc_rgc_want2=
  case "$adlc_rgc_verb:$adlc_rgc_rc" in
    mode:0) adlc_rgc_want='regression-test: required'; adlc_rgc_want2='regression-test: off' ;;
    mode:2) adlc_rgc_want='regression-test: error' ;;
    check:0) adlc_rgc_want='regression-check: pass'; adlc_rgc_want2='regression-check: off' ;;
    check:1) adlc_rgc_want='regression-check: fail' ;;
    check:2) adlc_rgc_want='regression-check: error' ;;
  esac
  if [ -z "$adlc_rgc_want" ]; then
    _adlc_regression_check_error "$adlc_rgc_prefix" "regression_check.py exited $adlc_rgc_rc"
    return 2
  fi
  # Exact first-line match only. The second verdict is compared only when the code
  # has one, so an empty first line never matches an empty second verdict.
  adlc_rgc_ok=0
  if [ "$adlc_rgc_head" = "$adlc_rgc_want" ]; then adlc_rgc_ok=1; fi
  if [ -n "$adlc_rgc_want2" ] && [ "$adlc_rgc_head" = "$adlc_rgc_want2" ]; then adlc_rgc_ok=1; fi
  if [ "$adlc_rgc_ok" != 1 ]; then
    if [ -n "$adlc_rgc_want2" ]; then
      _adlc_regression_check_error "$adlc_rgc_prefix" "regression_check.py exited $adlc_rgc_rc without a '$adlc_rgc_want' or '$adlc_rgc_want2' line"
    else
      _adlc_regression_check_error "$adlc_rgc_prefix" "regression_check.py exited $adlc_rgc_rc without a '$adlc_rgc_want' line"
    fi
    return 2
  fi
  printf '%s\n' "$adlc_rgc_out"
  return "$adlc_rgc_rc"
}
