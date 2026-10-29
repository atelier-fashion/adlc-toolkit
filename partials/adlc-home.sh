# partials/adlc-home.sh — the toolkit's machine-state home, ADLC_HOME (REQ-654 BR-1, BR-2).
#
# Source this partial, then call its functions WITHIN THE SAME fenced block, after the
# fence's ToolkitRoot root line (conventions.md "Bash in skills"):
#   if [ -f .adlc/partials/adlc-home.sh ]; then . .adlc/partials/adlc-home.sh; else . "$ADLC_TOOLKIT_ROOT/partials/adlc-home.sh"; fi
#   h=$(adlc_home) || exit 1
#
# THE RULE (REQ-654 architecture ADR-2). Machine state — the id counters and their
# lock dirs, the reservations ledger, the machine config, the delegate venv, the
# skills view — lives under one directory:
#   * ADLC_HOME unset              -> $HOME/.claude, byte-identical to the literal every
#                                     caller used before REQ-654 (the plan's Rule A)
#   * ADLC_HOME set and absolute   -> that path, trailing slashes removed (a bare `/`
#                                     stays `/`), so `<home>/x` has no `//` in it
#   * ADLC_HOME set, empty or not absolute -> an error that names ADLC_HOME. Never a
#                                     silent fall-through to the default (BR-2).
# The machine config is $ADLC_CONFIG when that is set and non-empty, else
# <home>/adlc/config.yml; a set ADLC_CONFIG never consults the home.
#
# Written out at THREE sites, because a partial cannot import Python and a Python
# module cannot be sourced by sh. The other two:
#   * tools/adlc/adlc_home.py — the doctor, forge_config, agents render, harness detect
#   * tools/delegate/_machine_config.py::adlc_home — the self-contained delegation tools
# Change one, change all three: tools/adlc/tests/test_adlc_home.py drives all three over
# one input vector and fails on any disagreement. install.sh's ~/bin/adlc shim text and
# scripts/session-start.sh inline the same test, because neither can source this file.
#
# What does NOT live here: toolkit READS go through ToolkitRoot (REQ-669), whose default
# operand `~/.claude/skills` is one of REQ-654 BR-3's two compatibility aliases, and the
# paths Claude Code itself owns (its config dir, plugin cache, settings.json, CLAUDE.md,
# its skills and agents mounts) stay where Claude Code reads them.
#
# Functions exported:
#   adlc_home            -> prints the home; rc 1 and one stderr line when it cannot resolve
#   adlc_home_source     -> prints `env` or `default` (rc 1 as adlc_home)
#   adlc_machine_config  -> prints the machine config path (rc 1 as adlc_home, unless
#                           ADLC_CONFIG is set)
#
# POSIX, dash-clean: prefixed globals (adlc_ah_*), no `local`, no `case` inside `$( )`
# (LESSON-582), and `set -u` safe — ${ADLC_HOME+x} tells unset from empty without
# expanding an unset variable, and HOME is read as ${HOME:-}. Loading the file runs
# nothing, so sourcing it under `set -u` with HOME unset cannot abort a caller.

adlc_home() {
  if [ -z "${ADLC_HOME+x}" ]; then
    case "${HOME:-}" in
      /*) printf '%s\n' "$HOME/.claude"; return 0 ;;  # adlc-home: default
    esac
    echo "ERROR: HOME is not an absolute path ('${HOME:-}') and ADLC_HOME is unset — cannot place the toolkit's machine state. Set HOME, or set ADLC_HOME to an absolute path (REQ-654 BR-2)." >&2
    return 1
  fi
  case "$ADLC_HOME" in
    /*)
      adlc_ah_v=$ADLC_HOME
      while :; do
        case "$adlc_ah_v" in
          ?*/) adlc_ah_v=${adlc_ah_v%/} ;;
          *) break ;;
        esac
      done
      printf '%s\n' "$adlc_ah_v"
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
  if [ -z "${ADLC_HOME+x}" ]; then printf '%s\n' default; else printf '%s\n' env; fi
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
