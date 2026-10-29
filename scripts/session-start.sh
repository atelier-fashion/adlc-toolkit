#!/bin/sh
# scripts/session-start.sh — the adlc plugin's SessionStart hook (REQ-669 ADR-4).
#
# hooks/hooks.json runs it as `sh "${CLAUDE_PLUGIN_ROOT}/scripts/session-start.sh"`
# at the start of every Claude Code session that has the plugin enabled. It does
# three idempotent things, and it writes nothing at all unless CLAUDE_PLUGIN_ROOT
# validates first (LESSON-017):
#
#   1. Pointer. ~/.claude/adlc/plugin-root gets the plugin root and a newline,
#      through a temp file in the same directory and `mv`, and only when the
#      content differs. Arm 3 of the ToolkitRoot line (ADR-1) reads it, for skill
#      text Claude Code did not substitute. The pointer is machine-global and the
#      last session to start wins, so it is written ONLY for a plugin-cache copy:
#      a root that resolves (`cd -P`) under the resolved
#      ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/cache/, and the resolved path
#      is what is written. A `--plugin-dir` checkout or a local-path marketplace
#      runs from a working tree, and publishing that would make every other
#      session's subagents source partials and the lane-check engine from it
#      (LESSON-718). Such a root leaves the pointer exactly as it was, with one
#      stderr note when a pointer is there to be left (none when there is no
#      pointer at all); the config and PATH steps still run.
#   2. Config. <ADLC_HOME>/adlc/config.yml gets install.sh's `ensure_config`
#      scaffold, delegation off, only when nothing is at that path. ADLC_HOME
#      defaults to ~/.claude (REQ-654), so by default this is
#      ~/.claude/adlc/config.yml, beside the pointer; a set ADLC_HOME that is
#      empty or not absolute writes no config and says so. The rule is
#      partials/adlc-home.sh's, inlined, because this hook sources nothing. The temp file
#      is hard-linked into place: `ln` without -f fails when anything is already
#      there, so a config another writer creates meanwhile is never replaced.
#      tools/adlc/tests/test_config_scaffold_parity.py pins the two byte-equal.
#   3. PATH. When CLAUDE_ENV_FILE is set, one line appends <root>/scripts AFTER
#      the user's PATH, so `adlc doctor` runs and a ~/bin/adlc still wins. A
#      marker comment on that line keeps a second run from appending again. A
#      marker line for a different root (a plugin update, then a resumed
#      session) is replaced by this root's line; the same root's line is kept.
#
# A hook failure must never cost the user their session, so every path exits 0,
# nothing reaches stdout (a SessionStart hook's stdout becomes session context),
# and at most one `adlc:` line reaches stderr. POSIX sh with no python; the
# harness is partials/tests/session-start.test.sh (bash, zsh, sh and dash).

adlc_ss_nl='
'
adlc_ss_marker='# adlc-plugin-path'
# install.sh's ensure_config text. The write adds the trailing newline, exactly
# as install.sh's atomic_write does.
adlc_ss_scaffold='# ADLC toolkit config (scaffolded by install.sh, REQ-519).
# Delegation is OFF by default (REQ-515 BR-11). To enable, set enabled: true and
# provide an API key per the provider you choose; then run:
#   ./install.sh --with-delegation
delegate:
  enabled: false'
adlc_ss_msg=

# adlc_ss_note <text> — keep the first problem; it is reported once, at exit.
adlc_ss_note() {
  if [ -z "$adlc_ss_msg" ]; then adlc_ss_msg=$1; fi
}

# adlc_ss_safe <path> — 0 iff <path> is free of a newline, `..`, `:` and the
# characters that are live inside the double-quoted PATH line. A `:` would split
# the appended PATH entry in two, and `::` would add the current directory.
adlc_ss_safe() {
  case $1 in
    *"$adlc_ss_nl"* | *..* | *:* | *'"'* | *'$'* | *'`'* | *'\'*) return 1 ;;
  esac
  return 0
}

# adlc_ss_root_ok <root> — 0 iff <root> is this plugin's root: absolute,
# adlc_ss_safe, and holding a .claude-plugin/plugin.json that names adlc plus
# partials/.
adlc_ss_root_ok() {
  adlc_ss_r=$1
  case $adlc_ss_r in
    /*) ;;
    *) adlc_ss_note "CLAUDE_PLUGIN_ROOT is unset or not an absolute path; nothing written"; return 1 ;;
  esac
  if ! adlc_ss_safe "$adlc_ss_r"; then
    adlc_ss_note "CLAUDE_PLUGIN_ROOT holds a newline, '..', ':' or a shell metacharacter; nothing written"; return 1
  fi
  if [ ! -f "$adlc_ss_r/.claude-plugin/plugin.json" ]; then
    adlc_ss_note "CLAUDE_PLUGIN_ROOT has no .claude-plugin/plugin.json; nothing written"; return 1
  fi
  # Read once. The manifest is pretty-printed with a two-space indent, so its
  # top-level "name" is the only "name" key at exactly that depth; a nested one
  # such as author.name sits deeper and cannot satisfy the match.
  adlc_ss_m=$(cat "$adlc_ss_r/.claude-plugin/plugin.json") || adlc_ss_m=
  adlc_ss_n_top=$(printf '%s\n' "$adlc_ss_m" | command grep -c '^  "name"[[:space:]]*:')
  adlc_ss_n_adlc=$(printf '%s\n' "$adlc_ss_m" | command grep -c -x -F -e '  "name": "adlc",' -e '  "name": "adlc"')
  if [ "$adlc_ss_n_top" != 1 ] || [ "$adlc_ss_n_adlc" != 1 ]; then
    adlc_ss_note "CLAUDE_PLUGIN_ROOT is not the adlc plugin (plugin.json names another); nothing written"; return 1
  fi
  if [ ! -d "$adlc_ss_r/partials" ]; then
    adlc_ss_note "CLAUDE_PLUGIN_ROOT has no partials/; nothing written"; return 1
  fi
  return 0
}

# adlc_ss_cache_copy <root> <config-dir> — 0 iff <root> resolves to a directory
# under <config-dir>/plugins/cache/, both sides resolved with `cd -P`, so a
# symlink in the cache that leads to a working tree does not count. Sets
# adlc_ss_real to the resolved root, which is what the pointer gets.
adlc_ss_cache_copy() {
  adlc_ss_real=
  adlc_ss_cache=$(CDPATH= cd -P -- "$2/plugins/cache" && pwd -P) || return 1
  adlc_ss_real=$(CDPATH= cd -P -- "$1" && pwd -P) || return 1
  if [ -z "$adlc_ss_cache" ] || [ -z "$adlc_ss_real" ] || ! adlc_ss_safe "$adlc_ss_real"; then return 1; fi
  case $adlc_ss_real in
    "$adlc_ss_cache"/?*) return 0 ;;
  esac
  return 1
}

# adlc_ss_write <target> <content> — <content> and a newline into a temp file
# beside <target>, then `mv` over it. 1 on any failure, with the temp file gone.
adlc_ss_write() {
  adlc_ss_tmp=$(mktemp "$1.tmp.XXXXXX") || return 1
  if [ -z "$adlc_ss_tmp" ] || [ ! -f "$adlc_ss_tmp" ]; then return 1; fi
  if printf '%s\n' "$2" > "$adlc_ss_tmp" && mv -f "$adlc_ss_tmp" "$1"; then return 0; fi
  rm -f "$adlc_ss_tmp"
  return 1
}

# adlc_ss_create <target> <content> — as adlc_ss_write, but the temp file is
# hard-linked to <target>, which fails when anything is already at <target>, so
# nothing there is ever replaced. The temp file is removed either way.
adlc_ss_create() {
  adlc_ss_tmp=$(mktemp "$1.tmp.XXXXXX") || return 1
  if [ -z "$adlc_ss_tmp" ] || [ ! -f "$adlc_ss_tmp" ]; then return 1; fi
  adlc_ss_rc=1
  if printf '%s\n' "$2" > "$adlc_ss_tmp" && ln "$adlc_ss_tmp" "$1"; then adlc_ss_rc=0; fi
  rm -f "$adlc_ss_tmp"
  return "$adlc_ss_rc"
}

# adlc_ss_replace <file> <line> — every marker line in <file> gives way to one
# <line>, at the first marker line's place, through a temp file and `mv`.
adlc_ss_replace() {
  adlc_ss_tmp=$(mktemp "$1.tmp.XXXXXX") || return 1
  if [ -z "$adlc_ss_tmp" ] || [ ! -f "$adlc_ss_tmp" ]; then return 1; fi
  if ADLC_SS_MARKER=$adlc_ss_marker ADLC_SS_LINE=$2 awk '
       index($0, ENVIRON["ADLC_SS_MARKER"]) { if (!done) print ENVIRON["ADLC_SS_LINE"]; done = 1; next }
       { print }' "$1" > "$adlc_ss_tmp" && mv -f "$adlc_ss_tmp" "$1"; then
    return 0
  fi
  rm -f "$adlc_ss_tmp"
  return 1
}

adlc_ss_main() {
  # Each input is read once, here.
  adlc_ss_root=${CLAUDE_PLUGIN_ROOT-}
  adlc_ss_env=${CLAUDE_ENV_FILE-}
  adlc_ss_home=${HOME-}
  adlc_ss_cfgdir=${CLAUDE_CONFIG_DIR-}
  adlc_ss_ahset=${ADLC_HOME+x}
  adlc_ss_ahv=${ADLC_HOME-}
  adlc_ss_root_ok "$adlc_ss_root" || return 0
  case $adlc_ss_home in
    /*) ;;
    *) adlc_ss_note "HOME is unset or not an absolute path; nothing written"; return 0 ;;
  esac
  # Claude Code's own directory, where the plugin cache lives. Only an absolute
  # CLAUDE_CONFIG_DIR is taken; anything else means the default.
  case $adlc_ss_cfgdir in
    /*) ;;
    *) adlc_ss_cfgdir="$adlc_ss_home/.claude" ;;  # adlc-home: claude-code
  esac
  # The pointer's directory is the alias the root line's arm 3 reads by literal
  # (REQ-654 BR-3); it never moves with ADLC_HOME.
  adlc_ss_dir="$adlc_ss_home/.claude/adlc"  # adlc-home: alias
  # The config's directory is <ADLC_HOME>/adlc (REQ-654 BR-1): partials/adlc-home.sh's
  # rule, inlined. Unset is the pointer's directory, so by default 1 and 2 share it.
  adlc_ss_cdir=$adlc_ss_dir
  if [ -n "$adlc_ss_ahset" ]; then
    case $adlc_ss_ahv in
      /*)
        adlc_ss_ah=$adlc_ss_ahv
        while :; do
          case $adlc_ss_ah in
            ?*/) adlc_ss_ah=${adlc_ss_ah%/} ;;
            *) break ;;
          esac
        done
        adlc_ss_cdir="${adlc_ss_ah%/}/adlc"
        ;;
      *)
        adlc_ss_cdir=
        adlc_ss_note "ADLC_HOME is set but is not an absolute path; config not written"
        ;;
    esac
  fi

  if mkdir -p "$adlc_ss_dir"; then
    adlc_ss_ptr="$adlc_ss_dir/plugin-root"
    if ! adlc_ss_cache_copy "$adlc_ss_root" "$adlc_ss_cfgdir"; then
      # Never recorded. A pointer that is already there names another copy and
      # is left as it was; this session's unsubstituted skill text resolves
      # through it, so say so. With no pointer there is nothing to report.
      if [ -e "$adlc_ss_ptr" ] || [ -L "$adlc_ss_ptr" ]; then
        adlc_ss_note "the plugin root is not a plugin-cache copy (a --plugin-dir or local-path checkout); ~/.claude/adlc/plugin-root left as it was"  # adlc-home: alias
      fi
    elif [ -d "$adlc_ss_ptr" ]; then
      adlc_ss_note "~/.claude/adlc/plugin-root is a directory; plugin root not recorded"  # adlc-home: alias
    elif printf '%s\n' "$adlc_ss_real" | cmp -s - "$adlc_ss_ptr"; then
      : # already current: no write
    elif ! adlc_ss_write "$adlc_ss_ptr" "$adlc_ss_real"; then
      adlc_ss_note "could not write ~/.claude/adlc/plugin-root; plugin root not recorded"  # adlc-home: alias
    fi
  elif [ "$adlc_ss_cdir" = "$adlc_ss_dir" ]; then
    adlc_ss_note "could not create ~/.claude/adlc; plugin root and config not written"  # adlc-home: alias
    adlc_ss_cdir=
  else
    adlc_ss_note "could not create ~/.claude/adlc; plugin root not recorded"  # adlc-home: alias
  fi
  if [ -n "$adlc_ss_cdir" ]; then
    if [ "$adlc_ss_cdir" = "$adlc_ss_dir" ] || mkdir -p "$adlc_ss_cdir"; then
      adlc_ss_cfg="$adlc_ss_cdir/config.yml"
      if [ -e "$adlc_ss_cfg" ] || [ -L "$adlc_ss_cfg" ]; then
        : # present, in any form: never touched
      elif adlc_ss_create "$adlc_ss_cfg" "$adlc_ss_scaffold"; then
        :
      elif [ -e "$adlc_ss_cfg" ] || [ -L "$adlc_ss_cfg" ]; then
        : # another writer got there first, and its file stands
      else
        adlc_ss_note "could not write the machine config (ADLC_HOME/adlc/config.yml, default ~/.claude/adlc/config.yml); delegation stays at its default"  # adlc-home: default
      fi
    else
      adlc_ss_note "could not create the ADLC_HOME adlc directory; config not written"
    fi
  fi

  # 3. Unset means nothing to do, and no file is created.
  if [ -n "$adlc_ss_env" ]; then
    adlc_ss_line="export PATH=\"\$PATH:$adlc_ss_root/scripts\" $adlc_ss_marker"
    case $adlc_ss_env in
      /*)
        if [ -d "$adlc_ss_env" ]; then
          adlc_ss_note "CLAUDE_ENV_FILE is a directory; adlc not added to PATH"
        elif [ -f "$adlc_ss_env" ] && command grep -q -F -e "$adlc_ss_marker" "$adlc_ss_env"; then
          # An earlier run's line. This root's line, and no other, is a no-op.
          if [ "$(command grep -c -F -e "$adlc_ss_marker" "$adlc_ss_env")" = 1 ] \
             && command grep -q -x -F -e "$adlc_ss_line" "$adlc_ss_env"; then
            :
          elif ! adlc_ss_replace "$adlc_ss_env" "$adlc_ss_line"; then
            adlc_ss_note "could not update the adlc PATH line in CLAUDE_ENV_FILE; adlc may still resolve to an older plugin copy"
          fi
        else
          # A file that does not end in a newline would glue its last line to ours.
          adlc_ss_pre=
          if [ -s "$adlc_ss_env" ] && [ -n "$(tail -c 1 "$adlc_ss_env")" ]; then adlc_ss_pre=$adlc_ss_nl; fi
          if ! printf '%s%s\n' "$adlc_ss_pre" "$adlc_ss_line" >> "$adlc_ss_env"; then
            adlc_ss_note "could not append to CLAUDE_ENV_FILE; adlc not added to PATH"
          fi
        fi
        ;;
      *) adlc_ss_note "CLAUDE_ENV_FILE is not an absolute path; adlc not added to PATH" ;;
    esac
  fi
  return 0
}

# Every command's own output is discarded, so the one line below is all a user
# can see. A function call with redirections runs in this shell, so the note
# survives it.
adlc_ss_main </dev/null >/dev/null 2>&1
if [ -n "$adlc_ss_msg" ]; then
  printf 'adlc: session-start: %s\n' "$adlc_ss_msg" >&2
fi
exit 0
