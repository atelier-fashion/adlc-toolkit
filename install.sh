#!/usr/bin/env bash
# install.sh — one-command ADLC toolkit installer (REQ-519).
#
# Idempotent and repair-capable (BR-1): a second run on a healthy machine
# changes nothing; a run on a broken machine fixes only what is broken;
# idempotency is keyed on file/symlink CONTENT, not process state. Every user
# file mutation is backup + temp-write + rename atomic and fail-loud (BR-2). No
# hardcoded user-specific absolute paths beyond $HOME and the install-time
# derived $REPO_ROOT (BR-3). Delegation is never enabled by default (BR-9).
#
# Usage:
#   ./install.sh                 # fresh / repair install (symlinks, adlc shim, PATH)
#   ./install.sh --repair        # same as default; re-derives paths after a clone move
#   ./install.sh --dry-run       # print the action plan, change nothing
#   ./install.sh --with-delegation   # also run the (opt-in) delegation install
#
# Ends with an embedded `adlc doctor` report.

set -euo pipefail

# --- arg parse -------------------------------------------------------------
MODE="install"          # install | dry-run   (repair is just install; both repair)
WITH_DELEGATION=0
for arg in "$@"; do
    case "$arg" in
        --dry-run)         MODE="dry-run" ;;
        --repair)          MODE="install" ;;   # repair == idempotent reinstall
        --with-delegation) WITH_DELEGATION=1 ;;
        -h|--help)
            sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "install.sh: unknown option '$arg' (try --help)" >&2
            exit 2
            ;;
    esac
done

DRY=0
[ "$MODE" = "dry-run" ] && DRY=1

# --- REPO_ROOT (canonical repo, not a worktree) ----------------------------
# Mirror tools/delegate/install.sh: --git-common-dir returns the canonical .git even
# when run from a worktree, so symlinks point at the real checkout (BR-3).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMMON_DIR="$(git -C "$SCRIPT_DIR" rev-parse --git-common-dir 2>/dev/null || true)"
CANON_ROOT=""
if [ -n "$COMMON_DIR" ]; then
    case "$COMMON_DIR" in
        /*) : ;;
        *)  COMMON_DIR="$(cd "$SCRIPT_DIR" && cd "$COMMON_DIR" && pwd)" ;;
    esac
    CANON_ROOT="$(dirname "$COMMON_DIR")"
fi
# Prefer the canonical repo root (so a normal clone symlinks to the real
# checkout, not a transient worktree), but fall back to SCRIPT_DIR when the
# canonical root does not yet carry the toolkit files — e.g. running from a
# worktree whose branch adds tools/adlc/ before it has merged to the canonical
# checkout. SCRIPT_DIR is always a valid checkout containing install.sh's
# siblings, so it is a safe base.
if [ -n "$CANON_ROOT" ] && [ -f "$CANON_ROOT/tools/adlc/adlc.py" ]; then
    REPO_ROOT="$CANON_ROOT"
elif [ -f "$SCRIPT_DIR/tools/adlc/adlc.py" ]; then
    REPO_ROOT="$SCRIPT_DIR"
else
    echo "ERROR: could not resolve toolkit root (tried '$CANON_ROOT' and '$SCRIPT_DIR')." >&2
    echo "Run install.sh from the root of the cloned toolkit repository." >&2
    exit 1
fi

CLAUDE_DIR="$HOME/.claude"
BIN_DIR="$HOME/bin"
ACTIONS=0   # count of real mutations performed (for the BR-1 summary)

note()  { printf '%s\n' "$*"; }
plan()  { printf '  would: %s\n' "$*"; }
acted() { ACTIONS=$((ACTIONS + 1)); printf '  done: %s\n' "$*"; }

# --- atomic write helper (BR-2) -------------------------------------------
# atomic_write <target-path> <content-as-single-arg> : backup existing, write a
# temp file in the target dir, fsync via rename. Content is passed by argument
# (NOT a pipe) so the acted() counter increments in the caller's shell, not a
# lost subshell — keeping the BR-1 "actions taken" summary honest.
atomic_write() {
    target="$1"; content="$2"
    if [ "$DRY" -eq 1 ]; then
        plan "write $target"
        return 0
    fi
    mkdir -p "$(dirname "$target")"
    tmp="$(mktemp "${target}.tmp.XXXXXX")"
    printf '%s\n' "$content" > "$tmp"
    if [ -e "$target" ] && [ ! -L "$target" ]; then
        cp -p "$target" "$target.bak"
    fi
    mv "$tmp" "$target"
    acted "wrote $target"
}

# --- symlink mutator (content-compared, idempotent BR-1) -------------------
ensure_symlink() {
    src="$1"; link="$2"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$src" ]; then
        note "  ok: $link already -> $src"
        return 0
    fi
    if [ -e "$link" ] && [ ! -L "$link" ]; then
        echo "ERROR: $link exists and is not a symlink. Move it aside, then re-run." >&2
        exit 1
    fi
    if [ "$DRY" -eq 1 ]; then
        plan "symlink $link -> $src"
        return 0
    fi
    mkdir -p "$(dirname "$link")"
    ln -sfn "$src" "$link"
    acted "symlinked $link -> $src"
}

# --- adlc shim (no hardcoded path beyond derived REPO_ROOT, BR-3/BR-11) -----
# The shim carries THE ONE INTERPRETER RULE (REQ-609 BR-8, ADR-2): prefer
# $HOME/.claude/delegate-venv/bin/python3 when it is a regular executable file
# AND that venv carries a `yaml` package directory under lib/python*/site-packages/;
# otherwise python3 from $PATH. The same rule is written out in
# tools/adlc/checks.py::_delegate_interpreter and partials/forge.sh::_adlc_forge_python
# — a partial cannot import Python and a Python module cannot be sourced by sh,
# so it exists three times and each site names the other two. Change one, change
# all three.
#
# Both halves earn their place. The PyYAML half: a venv created before REQ-609
# carries `openai` and no PyYAML, and this very function rewrites the shim
# BEFORE any venv refresh (a plain `./install.sh` refreshes none at all), so
# without it the shim would point every config read at the one interpreter on
# the machine that cannot parse the file. The fallback half: the venv exists
# only after --with-delegation, and a shim that `exec`s a missing interpreter
# would break `adlc doctor` on exactly the machine that most needs it
# (LESSON-395). $HOME is expanded by the shim at RUN time, not stamped here.
ensure_adlc_shim() {
    shim="$BIN_DIR/adlc"
    want="#!/usr/bin/env bash
# The ONE interpreter rule (REQ-609 BR-8, ADR-2) — see install.sh,
# tools/adlc/checks.py::_delegate_interpreter, partials/forge.sh::_adlc_forge_python.
_v=\"\$HOME/.claude/delegate-venv/bin/python3\"
_y=\"\"
for _d in \"\$HOME\"/.claude/delegate-venv/lib/python*/site-packages/yaml; do
  if [ -d \"\$_d\" ]; then _y=1; fi
done
if [ -f \"\$_v\" ] && [ -x \"\$_v\" ] && [ -n \"\$_y\" ]; then
  exec \"\$_v\" \"$REPO_ROOT/tools/adlc/adlc.py\" \"\$@\"
fi
exec python3 \"$REPO_ROOT/tools/adlc/adlc.py\" \"\$@\""
    # Whole-text comparison: the idempotency key is the shim's CONTENT, so a
    # machine carrying the old single-line shim is re-stamped rather than
    # reported "already current" (BR-1, LESSON-017).
    if [ -f "$shim" ] && [ "$(cat "$shim")" = "$want" ]; then
        note "  ok: $shim already current"
        return 0
    fi
    if [ "$DRY" -eq 1 ]; then
        plan "write adlc shim $shim -> $REPO_ROOT/tools/adlc/adlc.py (delegate venv python3 when present)"
        return 0
    fi
    atomic_write "$shim" "$want"
    chmod +x "$shim"
}

# --- delegate venv PyYAML report (REQ-609 BR-8, ADR-2) ---------------------
# `ensure_adlc_shim` above runs BEFORE any venv work, and a plain `./install.sh`
# does no venv work at all — so a machine whose venv predates REQ-609 keeps an
# interpreter the shim deliberately skips. The rule keeps that CORRECT; this
# says it out loud, because "adlc quietly runs a different python3 than you
# think" is not a thing an operator should have to discover.
#
# It never pip-installs: touching a venv the operator did not ask to touch is a
# mutation outside the --with-delegation opt-in (BR-9). It never aborts either
# — the fallback works, so this is a degraded machine, not a broken install.
report_venv_pyyaml() {
    venv="$HOME/.claude/delegate-venv"
    if [ ! -f "$venv/bin/python3" ] || [ ! -x "$venv/bin/python3" ]; then
        note "  ok: no delegate venv — adlc runs \$PATH's python3"
        return 0
    fi
    venv_yaml=""
    # Same test as the shim, unmatched-glob-safe: bash leaves an unmatched glob
    # literal, and `[ -d ]` on the literal is false.
    for d in "$venv"/lib/python*/site-packages/yaml; do
        if [ -d "$d" ]; then venv_yaml=1; fi
    done
    if [ -n "$venv_yaml" ]; then
        note "  ok: delegate venv has PyYAML — adlc runs $venv/bin/python3"
        return 0
    fi
    note "  WARN: $venv exists but has no PyYAML, so adlc falls back to \$PATH's"
    note "        python3 and the delegate CLIs cannot parse the ADLC config."
    note "  fix:  $venv/bin/pip install -r $REPO_ROOT/tools/delegate/requirements.txt"
    return 0
}

# --- PATH wiring (marker-guarded, idempotent BR-1) -------------------------
PATH_MARKER="# >>> adlc-toolkit (REQ-519) >>>"
PATH_MARKER_END="# <<< adlc-toolkit (REQ-519) <<<"
ensure_path() {
    # Pick the rc file by the REAL login shell, not $SHELL (BR-6).
    login_shell="$(dscl . -read "/Users/$USER" UserShell 2>/dev/null | awk '{print $2}')"
    [ -z "$login_shell" ] && login_shell="$(getent passwd "$USER" 2>/dev/null | awk -F: '{print $7}')"
    case "$login_shell" in
        *zsh)  rc="$HOME/.zshrc" ;;
        *bash) rc="$HOME/.bash_profile" ;;
        *)     rc="$HOME/.profile" ;;
    esac
    if [ -f "$rc" ] && grep -F "$PATH_MARKER" "$rc" >/dev/null 2>&1; then
        note "  ok: PATH marker already in $rc"
        return 0
    fi
    if [ "$DRY" -eq 1 ]; then
        plan "append PATH ($BIN_DIR) marker block to $rc"
        return 0
    fi
    existing=""
    [ -f "$rc" ] && existing="$(cat "$rc")"$'\n'
    block="${PATH_MARKER}
export PATH=\"${BIN_DIR}:\$PATH\"
${PATH_MARKER_END}"
    atomic_write "$rc" "${existing}${block}"
}

# --- config scaffold (never overwrite existing; delegation off BR-9) -------
ensure_config() {
    cfg="$CLAUDE_DIR/adlc/config.yml"
    if [ -f "$cfg" ]; then
        note "  ok: config exists ($cfg) — left untouched"
        return 0
    fi
    if [ "$DRY" -eq 1 ]; then
        plan "scaffold $cfg (delegation disabled)"
        return 0
    fi
    atomic_write "$cfg" "# ADLC toolkit config (scaffolded by install.sh, REQ-519).
# Delegation is OFF by default (REQ-515 BR-11). To enable, set enabled: true and
# provide an API key per the provider you choose; then run:
#   ./install.sh --with-delegation
delegate:
  enabled: false"
}

# --- run -------------------------------------------------------------------
note "ADLC toolkit installer  (mode: $MODE)"
note "  repo root: $REPO_ROOT"
note ""
note "symlinks:"
ensure_symlink "$REPO_ROOT" "$CLAUDE_DIR/skills"
ensure_symlink "$REPO_ROOT/agents" "$CLAUDE_DIR/agents"
note "adlc CLI:"
ensure_adlc_shim
note "PATH:"
ensure_path
note "config:"
ensure_config

# --- optional delegation (opt-in only, BR-9) -------------------------------
note "delegation:"
if [ "$WITH_DELEGATION" -eq 1 ]; then
    note "  Data-governance notice: delegation sends file contents to a third-party"
    note "  model provider. Only enable it for repositories whose contents you are"
    note "  permitted to share. See tools/delegate/README.md."
    if [ "$DRY" -eq 1 ]; then
        plan "run tools/delegate/install.sh (delegation opt-in)"
    else
        note "  running tools/delegate/install.sh ..."
        bash "$REPO_ROOT/tools/delegate/install.sh"
        acted "installed delegation tools"
    fi
else
    note "  skipped (opt-in). Re-run with --with-delegation to install (off by default)."
fi
report_venv_pyyaml

# --- summary + embedded doctor (BR-1 summary, System Model install event) --
note ""
if [ "$DRY" -eq 1 ]; then
    note "Dry run: no changes made. Re-run without --dry-run to apply."
else
    note "Install summary: $ACTIONS action(s) taken; everything else was already current."
fi
note ""
note "doctor report:"
# Call adlc.py directly (PATH not yet re-sourced in this shell).
python3 "$REPO_ROOT/tools/adlc/adlc.py" doctor || true
