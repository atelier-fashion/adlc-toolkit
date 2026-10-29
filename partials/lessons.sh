# partials/lessons.sh — LessonSet retrieval for the pipeline phases (REQ-647).
#
# Source this partial, then call adlc_lessons WITHIN THE SAME fenced block, after the
# fence's ToolkitRoot root line (conventions.md "Bash in skills"):
#   if [ -f .adlc/partials/lessons.sh ]; then . .adlc/partials/lessons.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lessons.sh"; fi
#   adlc_lessons select --set task --task-id TASK-012 --root "$wt" --spec "$spec" \
#     --component adlc/partials/forge --state-out "$state"
#   # rc 0: stdout is the log line, then one block of loaded text per lesson
#   # rc 2: stdout is one `lessons: unavailable — <reason>` line; log it and carry on
#
# Contract — adlc_lessons <select|text|log-line|ack-check> [args...]:
#   runs <ToolkitRoot>/tools/adlc/lessons.py with the arguments unchanged, and passes its
#   stdout and return code through. The engine's own contract is rc 0 success, rc 2 error.
#   The wrapper adds one case: when it cannot run the engine at all (no engine file, no
#   interpreter resolver, a relative root, an exit outside 0/2) it prints one
#   `lessons: unavailable — <reason>` line and returns 2.
# Retrieval is NEVER a gate: every caller treats rc 2 as "log the line, continue without
# lessons" (REQ-647 BR-7). Full contract: partials/lessons.md.
#
# The engine is the installed toolkit's, <ToolkitRoot>/tools/adlc/lessons.py, as for the
# lane check: ToolkitRoot is the plugin's cache copy or the clone behind ~/.claude/skills.
# Unset, it defaults to the symlink install.
#
# POSIX only, dash-clean: prefixed globals (no `local`), no arrays, no `case` inside
# `$( )` (LESSON-582).

# The interpreter comes from forge.sh's `_adlc_forge_python`, as lane-check.sh's does,
# so every engine runs under one Python (REQ-652 ADR-3's documented coupling). forge.sh
# is sourced with the guarded two-level spelling, and only when the function is not
# already defined. The fallback operand reads a bare $HOME, so it is not reached when
# neither ADLC_TOOLKIT_ROOT nor HOME is set: a `set -u` caller would abort on it.
if ! command -v _adlc_forge_python >/dev/null 2>&1 && { [ -n "${ADLC_TOOLKIT_ROOT:-}${HOME+x}" ] || [ -f .adlc/partials/forge.sh ]; }; then
  if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/forge.sh"; fi
fi

# _adlc_lessons_unavailable <reason> — the one-line error contract on stdout, rc 2.
_adlc_lessons_unavailable() {
  printf 'lessons: unavailable — %s\n' "$1"
  return 2
}

adlc_lessons() {
  if [ "$#" -eq 0 ]; then
    echo "adlc_lessons: usage: adlc_lessons <select|text|log-line|ack-check> [args...]" >&2
    _adlc_lessons_unavailable 'usage: adlc_lessons <select|text|log-line|ack-check> [args...]'
    return 2
  fi
  # The root must be absolute; with ADLC_TOOLKIT_ROOT unset it comes from HOME, so HOME
  # is checked first, which also keeps an unset HOME from aborting a `set -u` caller.
  if [ -z "${ADLC_TOOLKIT_ROOT:-}" ]; then
    case "${HOME:-}" in
      /*) ;;
      *)
        echo "adlc_lessons: HOME is not an absolute path ('${HOME:-}')" >&2
        _adlc_lessons_unavailable 'HOME is not an absolute path'
        return 2
        ;;
    esac
  fi
  adlc_ls_script="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/lessons.py"
  case "$adlc_ls_script" in
    /*) ;;
    *)
      echo "adlc_lessons: ADLC_TOOLKIT_ROOT is not an absolute path ('$ADLC_TOOLKIT_ROOT')" >&2
      _adlc_lessons_unavailable 'ADLC_TOOLKIT_ROOT is not an absolute path'
      return 2
      ;;
  esac
  if [ ! -f "$adlc_ls_script" ]; then
    echo "adlc_lessons: lessons.py not found at ${adlc_ls_script%/lessons.py}/ — the installed toolkit predates REQ-647 (symlink route: git pull the clone; plugin route: claude plugin update adlc@adlc-toolkit)" >&2
    _adlc_lessons_unavailable 'lessons.py not found in the installed toolkit'
    return 2
  fi
  if ! command -v _adlc_forge_python >/dev/null 2>&1; then
    echo "adlc_lessons: _adlc_forge_python is not defined (forge.sh did not load)" >&2
    _adlc_lessons_unavailable 'interpreter resolver _adlc_forge_python is not defined'
    return 2
  fi
  adlc_ls_py=$(_adlc_forge_python)
  if [ -z "$adlc_ls_py" ]; then
    _adlc_lessons_unavailable 'interpreter resolver _adlc_forge_python printed nothing'
    return 2
  fi
  # `command` so a shell function named `python3` cannot intercept the call (REQ-609 D5);
  # `-E` so PYTHONPATH cannot shadow a standard-library module. stdout and stderr are
  # not touched, so a 0 or 2 from the engine reaches the caller byte for byte.
  command "$adlc_ls_py" -E "$adlc_ls_script" "$@"
  adlc_ls_rc=$?
  case $adlc_ls_rc in
    0 | 2) return "$adlc_ls_rc" ;;
  esac
  _adlc_lessons_unavailable "lessons.py exited $adlc_ls_rc"
  return 2
}
