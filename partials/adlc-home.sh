# partials/adlc-home.sh — the toolkit's machine-state home, ADLC_HOME (REQ-654 BR-1, BR-2).
#
# Source this partial, then call its functions WITHIN THE SAME fenced block, after the
# fence's ToolkitRoot root line (conventions.md "Bash in skills"):
#   if [ -f .adlc/partials/adlc-home.sh ]; then . .adlc/partials/adlc-home.sh; else . "$ADLC_TOOLKIT_ROOT/partials/adlc-home.sh"; fi
#   h=$(adlc_home) || exit 1
#
# THE RULE (REQ-654 architecture ADR-2, REQ-663 BR-8). Machine state — the id counters
# and their lock dirs, the reservations ledger, the machine config, the delegate venv,
# the skills view — lives under one directory:
#   * ADLC_HOME set and absolute   -> that path, trailing slashes removed (a bare `/`
#                                     stays `/`), so `<home>/x` has no `//` in it
#   * ADLC_HOME set, empty or not absolute -> an error that names ADLC_HOME. Never a
#                                     silent fall-through to the default (BR-2).
#   * ADLC_HOME unset, pointer present -> the home in $HOME/.claude/.adlc-home, which
#                                     `install.sh --migrate-home` writes (REQ-663 BR-8)
#   * ADLC_HOME unset, no pointer  -> $HOME/.claude, byte-identical to the literal every
#                                     caller used before REQ-654 (the plan's Rule A)
#   * ADLC_HOME set and different from the pointer -> an error naming both. A fence that
#                                     honoured it would allocate from a second counter.
#   * a pointer that is not a regular file, holds no absolute path, or names a directory
#     that does not exist -> an error naming the pointer, never the default.
# The machine config is $ADLC_CONFIG when that is set and non-empty, else
# <home>/adlc/config.yml; a set ADLC_CONFIG never consults the home.
#
# Written out at THREE sites, because a partial cannot import Python and a Python
# module cannot be sourced by sh. The other two:
#   * tools/adlc/adlc_home.py — the doctor, forge_config, agents render, harness detect
#   * tools/delegate/_machine_config.py::adlc_home — the self-contained delegation tools
# Change one, change all three: tools/adlc/tests/test_adlc_home.py drives all three over
# one input vector and fails on any disagreement. install.sh's ~/bin/adlc shim text and
# scripts/session-start.sh inline the same test, because neither can source this file;
# there an unusable home means no venv and no config, and adlc itself names the problem.
#
# What does NOT live here: toolkit READS go through ToolkitRoot (REQ-669), whose default
# operand `~/.claude/skills` is one of REQ-654 BR-3's two compatibility aliases, and the
# paths Claude Code itself owns (its config dir, plugin cache, settings.json, CLAUDE.md,
# its skills and agents mounts) stay where Claude Code reads them.
#
# Functions exported:
#   adlc_home            -> prints the home; rc 1 and one stderr line when it cannot resolve
#   adlc_default_home    -> prints $HOME/.claude; the only name the default has (rc 1 likewise)
#   adlc_home_source     -> prints `env`, `pointer` or `default` (rc 1 as adlc_home)
#   adlc_machine_config  -> prints the machine config path (rc 1 as adlc_home, unless
#                           ADLC_CONFIG is set)
#
# POSIX, dash-clean: prefixed globals (adlc_ah_*), no `local`, no `case` inside `$( )`
# (LESSON-582), and `set -u` safe — ${ADLC_HOME+x} tells unset from empty without
# expanding an unset variable, and HOME is read as ${HOME:-}. Loading the file runs
# nothing, so sourcing it under `set -u` with HOME unset cannot abort a caller.

adlc_default_home() {
  case "${HOME:-}" in
    /*) printf '%s\n' "$HOME/.claude"; return 0 ;;  # adlc-home: default
  esac
  echo "ERROR: HOME is not an absolute path ('${HOME:-}') and ADLC_HOME is unset — cannot place the toolkit's machine state. Set HOME, or set ADLC_HOME to an absolute path (REQ-654 BR-2)." >&2
  return 1
}

# _adlc_home_trim — strip trailing slashes from adlc_ah_v; a bare `/` stays `/`.
_adlc_home_trim() {
  while :; do
    case "$adlc_ah_v" in
      ?*/) adlc_ah_v=${adlc_ah_v%/} ;;
      *) break ;;
    esac
  done
}

# _adlc_home_pointer — sets adlc_ah_ptr to the pointer's home, or to nothing when no
# pointer is present. rc 1 and one stderr line when the pointer cannot be used. A HOME
# that is not absolute has no pointer to find, so ADLC_HOME keeps working without one.
_adlc_home_pointer() {
  adlc_ah_ptr=""
  case "${HOME:-}" in
    /*) ;;
    *) return 0 ;;
  esac
  adlc_ah_pf="$HOME/.claude/.adlc-home"  # adlc-home: default
  if [ ! -e "$adlc_ah_pf" ] && [ ! -L "$adlc_ah_pf" ]; then
    return 0
  fi
  if [ -L "$adlc_ah_pf" ] || [ ! -f "$adlc_ah_pf" ]; then
    echo "ERROR: the ADLC home pointer $adlc_ah_pf is not a regular file — run: install.sh --migrate-home <dir> to repair it, or remove it if this machine was never migrated (REQ-663 BR-8)." >&2
    return 1
  fi
  # read returns non-zero on a last line with no newline, and still sets the variable.
  IFS= read -r adlc_ah_v < "$adlc_ah_pf" || :
  case "${adlc_ah_v:-}" in
    /*) ;;
    *)
      echo "ERROR: the ADLC home pointer $adlc_ah_pf does not hold an absolute path, got '${adlc_ah_v:-}' — run: install.sh --migrate-home <dir> to repair it (REQ-663 BR-8)." >&2
      return 1
      ;;
  esac
  _adlc_home_trim
  if [ ! -d "$adlc_ah_v" ]; then
    echo "ERROR: the ADLC home pointer $adlc_ah_pf names '$adlc_ah_v', which does not exist — mount it, or run: install.sh --migrate-home '$adlc_ah_v' to restore it from the backup (REQ-663 BR-8)." >&2
    return 1
  fi
  adlc_ah_ptr=$adlc_ah_v
  return 0
}

adlc_home() {
  if [ -z "${ADLC_HOME+x}" ]; then
    _adlc_home_pointer || return 1
    if [ -n "$adlc_ah_ptr" ]; then
      printf '%s\n' "$adlc_ah_ptr"
      return 0
    fi
    adlc_default_home
    return $?
  fi
  case "$ADLC_HOME" in
    /*)
      adlc_ah_v=$ADLC_HOME
      _adlc_home_trim
      adlc_ah_env=$adlc_ah_v
      _adlc_home_pointer || return 1
      if [ -n "$adlc_ah_ptr" ] && [ "$adlc_ah_ptr" != "$adlc_ah_env" ]; then
        echo "ERROR: ADLC_HOME is '$adlc_ah_env' but the ADLC home pointer names '$adlc_ah_ptr' — unset ADLC_HOME, or run install.sh --migrate-home --back first (REQ-663 BR-8)." >&2
        return 1
      fi
      printf '%s\n' "$adlc_ah_env"
      return 0
      ;;
    '')
      echo "ERROR: ADLC_HOME is set but empty — unset it to use \$HOME/.claude, or set it to an absolute path (REQ-654 BR-2)." >&2  # adlc-home: default
      return 1
      ;;
  esac
  echo "ERROR: ADLC_HOME must be an absolute path, got '$ADLC_HOME' — unset it to use \$HOME/.claude, or set an absolute path (REQ-654 BR-2)." >&2  # adlc-home: default
  return 1
}

adlc_home_source() {
  adlc_ah_src=$(adlc_home) || return 1
  if [ -n "${ADLC_HOME+x}" ]; then printf '%s\n' env; return 0; fi
  _adlc_home_pointer 2>/dev/null
  if [ -n "$adlc_ah_ptr" ]; then printf '%s\n' pointer; else printf '%s\n' default; fi
}

adlc_machine_config() {
  if [ -n "${ADLC_CONFIG:-}" ]; then
    printf '%s\n' "$ADLC_CONFIG"
    return 0
  fi
  adlc_ah_cfg=$(adlc_home) || return 1
  # ${…%/}: a home of `/` must not yield `//adlc/config.yml` (Python's join does not).
  printf '%s\n' "${adlc_ah_cfg%/}/adlc/config.yml"
}
