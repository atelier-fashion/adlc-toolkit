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
#   ./install.sh                 # fresh / repair install (symlinks, skills view, adlc shim, PATH)
#   ./install.sh --repair        # same as default; re-derives paths after a clone move
#   ./install.sh --dry-run       # print the action plan, change nothing
#   ./install.sh --with-delegation   # also run the (opt-in) delegation install
#
# Machine state lives under ADLC_HOME, default ~/.claude (REQ-654): the config, the
# delegate venv and the skills view. Claude Code's mount (~/.claude/skills and
# ~/.claude/agents) is installed whatever ADLC_HOME says; a skills-only view of the
# clone is mounted at ~/.agents/skills for the other harnesses.
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
            sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'
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

# --- ADLC_HOME (REQ-654 BR-1, BR-2) -----------------------------------------
# Machine state lives under ADLC_HOME, default ~/.claude, resolved by the same
# partial every skill uses — the copy beside THIS script, so the rule cannot drift.
# Resolved and validated before any mutation (LESSON-017): an ADLC_HOME that is set
# but empty or relative stops the install here, naming the variable, with nothing
# changed. With ADLC_HOME unset every path below is the one it always was.
if [ ! -f "$SCRIPT_DIR/partials/adlc-home.sh" ]; then
    echo "ERROR: $SCRIPT_DIR/partials/adlc-home.sh not found — run install.sh from a complete toolkit clone." >&2
    exit 1
fi
. "$SCRIPT_DIR/partials/adlc-home.sh"
if ! ADLC_HOME_DIR="$(adlc_home)"; then
    echo "install.sh: nothing changed — fix ADLC_HOME and re-run." >&2
    exit 1
fi

# Claude Code's own directory: its skills and agents mounts, installed on every
# run whatever ADLC_HOME says (REQ-654 BR-3, BR-6). ~/.claude/skills is also the
# compatibility alias the ToolkitRoot line and every vendored partial resolve
# through, so it must point at the clone root, never at the skills-only view.
CLAUDE_DIR="$HOME/.claude"  # adlc-home: claude-code
BIN_DIR="$HOME/bin"
# The skills-only view (ADR-4) and the mount the other harnesses read (ADR-5).
SKILLS_VIEW="$ADLC_HOME_DIR/adlc/skills-view"
AGENTS_MOUNT="$HOME/.agents/skills"
ACTIONS=0   # count of real mutations performed (for the BR-1 summary)

PLANS=0     # count of planned mutations (--dry-run)
note()  { printf '%s\n' "$*"; }
plan()  { PLANS=$((${PLANS:-0} + 1)); printf '  would: %s\n' "$*"; }
acted() { ACTIONS=$((ACTIONS + 1)); printf '  done: %s\n' "$*"; }

# --- atomic write helper (BR-2) -------------------------------------------
# atomic_write <target-path> <content-as-single-arg> [generated] : backup existing,
# write a temp file in the target dir, fsync via rename. Content is passed by
# argument (NOT a pipe) so the acted() counter increments in the caller's shell,
# not a lost subshell — keeping the BR-1 "actions taken" summary honest. A third
# argument `generated` skips the backup: the file is this installer's own output
# with no user content, and a .bak of it would only keep a stale clone path on
# disk after a --repair (REQ-654 AC-9).
atomic_write() {
    target="$1"; content="$2"; generated="${3:-}"
    if [ "$DRY" -eq 1 ]; then
        plan "write $target"
        return 0
    fi
    mkdir -p "$(dirname "$target")"
    tmp="$(mktemp "${target}.tmp.XXXXXX")"
    printf '%s\n' "$content" > "$tmp"
    if [ -e "$target" ] && [ ! -L "$target" ] && [ "$generated" != "generated" ]; then
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
# <ADLC_HOME>/delegate-venv/bin/python3 when it is a regular executable file
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
# (LESSON-395). $HOME and ADLC_HOME are expanded by the shim at RUN time, not
# stamped here (REQ-654 ADR-3).
ensure_adlc_shim() {
    shim="$BIN_DIR/adlc"
    want="#!/usr/bin/env bash
# The ONE interpreter rule (REQ-609 BR-8, ADR-2) — see install.sh,
# tools/adlc/checks.py::_delegate_interpreter, partials/forge.sh::_adlc_forge_python.
# The venv lives under ADLC_HOME, default ~/.claude, resolved here at run time by
# partials/adlc-home.sh's rule (REQ-654 ADR-3). An unusable ADLC_HOME means no
# venv: python3 from PATH, and adlc itself then names the problem.
_h=\"\$HOME/.claude\"  # adlc-home: default
if [ -n \"\${ADLC_HOME+x}\" ]; then
  case \"\$ADLC_HOME\" in /*) _h=\"\${ADLC_HOME%/}\" ;; *) _h=\"\" ;; esac
fi
_v=\"\$_h/delegate-venv/bin/python3\"
_y=\"\"
if [ -n \"\$_h\" ]; then
  for _d in \"\$_h\"/delegate-venv/lib/python*/site-packages/yaml; do
    if [ -d \"\$_d\" ]; then _y=1; fi
  done
fi
if [ -n \"\$_h\" ] && [ -f \"\$_v\" ] && [ -x \"\$_v\" ] && [ -n \"\$_y\" ]; then
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
    atomic_write "$shim" "$want" generated
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
    venv="$ADLC_HOME_DIR/delegate-venv"
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
    cfg="$ADLC_HOME_DIR/adlc/config.yml"
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

# --- the skills-only view (REQ-654 BR-4, ADR-4) ----------------------------
# One absolute symlink per skill: <view>/<name> -> <clone>/<name> for every
# <clone>/<name>/SKILL.md at depth one. The view is the toolkit's own machine
# state, so a link that points elsewhere is repointed (what --repair after a clone
# move needs) and a link for a name that is no longer a skill is removed. Anything
# in it that is not a symlink is left alone, with a warning.

# toolkit_skill_names — one name per line. Hidden directories are not matched by
# the glob, and a name outside the safe charset is skipped, never interpolated.
toolkit_skill_names() {
    for tsn_d in "$REPO_ROOT"/*/; do
        tsn_n="$(basename "$tsn_d")"
        case "$tsn_n" in
            *[!A-Za-z0-9._-]*|[!A-Za-z0-9]*) continue ;;
        esac
        if [ -f "$REPO_ROOT/$tsn_n/SKILL.md" ]; then printf '%s\n' "$tsn_n"; fi
    done
    return 0
}

# is_toolkit_skill <name> — membership by pattern, not a `| grep -q` pipeline:
# under `pipefail` an early-exiting grep can make the pipeline fail on a match.
NL='
'
is_toolkit_skill() {
    case "$NL$SKILL_NAMES$NL" in
        *"$NL$1$NL"*) return 0 ;;
    esac
    return 1
}

# link_entry <target> <link> <verb> — create or repoint one symlink, or plan it.
link_entry() {
    if [ "$DRY" -eq 1 ]; then
        plan "$3 $2 -> $1"
        return 0
    fi
    ln -sfn "$1" "$2"
    acted "$3 $2 -> $1"
}

# unlink_entry <link> <why> — remove one symlink this installer made, or plan it.
unlink_entry() {
    if [ "$DRY" -eq 1 ]; then
        plan "remove $1 ($2)"
        return 0
    fi
    rm -f "$1"
    acted "removed $1 ($2)"
}

ensure_skills_view() {
    esv_before=$((ACTIONS + PLANS))
    if [ ! -d "$SKILLS_VIEW" ]; then
        if [ "$DRY" -eq 1 ]; then
            plan "create skills view $SKILLS_VIEW"
        else
            mkdir -p "$SKILLS_VIEW"
            acted "created skills view $SKILLS_VIEW"
        fi
    fi
    while IFS= read -r esv_n; do
        [ -n "$esv_n" ] || continue
        esv_link="$SKILLS_VIEW/$esv_n"
        esv_want="$REPO_ROOT/$esv_n"
        if [ -L "$esv_link" ]; then
            if [ "$(readlink "$esv_link")" != "$esv_want" ]; then
                link_entry "$esv_want" "$esv_link" "repointed view link"
            fi
        elif [ -e "$esv_link" ]; then
            note "  WARN: $esv_link is not a symlink — left alone; move it aside to let install.sh manage it"
        else
            link_entry "$esv_want" "$esv_link" "linked view entry"
        fi
    done <<ESV_EOF
$SKILL_NAMES
ESV_EOF
    for esv_e in "$SKILLS_VIEW"/*; do
        [ -L "$esv_e" ] || continue
        esv_n="$(basename "$esv_e")"
        if ! is_toolkit_skill "$esv_n"; then
            unlink_entry "$esv_e" "no longer a skill"
        fi
    done
    if [ $((ACTIONS + PLANS)) -eq "$esv_before" ]; then
        note "  ok: $SKILLS_VIEW current ($(printf '%s\n' "$SKILL_NAMES" | grep -c .) skills)"
    fi
}

# --- the ~/.agents/skills mount (REQ-654 BR-5, ADR-5) -----------------------
# Classified before it is touched, and the state found is always printed, so
# --dry-run names it. Nothing the user owns is replaced: in a directory that
# already exists (or that a symlink of theirs leads to) every toolkit skill gets
# its own link to the view entry, a name already taken by a non-toolkit entry is
# skipped and reported, and ownership is told by a link's TARGET, never its name.

# mount_per_skill <dir> — one link per toolkit skill inside <dir>.
mount_per_skill() {
    mps_dir="$1"
    mps_taken=""
    while IFS= read -r mps_n; do
        [ -n "$mps_n" ] || continue
        mps_e="$mps_dir/$mps_n"
        mps_want="$SKILLS_VIEW/$mps_n"
        if [ -L "$mps_e" ]; then
            mps_t="$(readlink "$mps_e")"
            if [ "$mps_t" = "$mps_want" ]; then
                continue
            fi
            case "$mps_t" in
                */adlc/skills-view/"$mps_n")
                    link_entry "$mps_want" "$mps_e" "repointed mount link"
                    continue
                    ;;
            esac
        fi
        if [ -e "$mps_e" ] || [ -L "$mps_e" ]; then
            mps_taken="$mps_taken $mps_n"
            continue
        fi
        link_entry "$mps_want" "$mps_e" "linked mount entry"
    done <<MPS_EOF
$SKILL_NAMES
MPS_EOF
    for mps_e in "$mps_dir"/*; do
        [ -L "$mps_e" ] || continue
        mps_n="$(basename "$mps_e")"
        mps_t="$(readlink "$mps_e")"
        case "$mps_t" in
            "$SKILLS_VIEW/$mps_n"|*/adlc/skills-view/"$mps_n") ;;
            *) continue ;;
        esac
        if ! is_toolkit_skill "$mps_n"; then
            unlink_entry "$mps_e" "no longer a skill"
        fi
    done
    if [ -n "$mps_taken" ]; then
        note "  skipped (name taken by a non-toolkit entry, left untouched):$mps_taken"
    fi
}

ensure_agents_mount() {
    eam_m="$AGENTS_MOUNT"
    if [ -L "$eam_m" ]; then
        eam_t="$(readlink "$eam_m")"
        if [ "$eam_t" = "$SKILLS_VIEW" ]; then
            note "  found: $eam_m is a symlink to the skills view"
            note "  ok: $eam_m -> $SKILLS_VIEW"
            return 0
        fi
        if [ -d "$eam_m" ]; then
            note "  found: $eam_m is a symlink to a directory ($eam_t)"
            mount_per_skill "$eam_m"
            return 0
        fi
        case "$eam_t" in
            */adlc/skills-view)
                note "  found: $eam_m is a dangling symlink to an earlier skills view ($eam_t)"
                link_entry "$SKILLS_VIEW" "$eam_m" "repointed"
                ;;
            *)
                note "  found: $eam_m is a dangling symlink to $eam_t, which install.sh did not make"
                note "  WARN: left alone; move it aside and re-run to mount the skills view there"
                ;;
        esac
        return 0
    fi
    if [ -d "$eam_m" ]; then
        note "  found: $eam_m is a directory you own"
        mount_per_skill "$eam_m"
        return 0
    fi
    if [ -e "$eam_m" ]; then
        note "  found: $eam_m is a file, not a directory"
        note "  WARN: left alone; move it aside and re-run to mount the skills view there"
        return 0
    fi
    note "  found: $eam_m is absent"
    if [ "$DRY" -eq 1 ]; then
        plan "symlink $eam_m -> $SKILLS_VIEW"
        return 0
    fi
    mkdir -p "$(dirname "$eam_m")"
    ln -s "$SKILLS_VIEW" "$eam_m"
    acted "symlinked $eam_m -> $SKILLS_VIEW"
}

# --- run -------------------------------------------------------------------
# Preflight first: nothing below it mutates until every input is known good
# (LESSON-017). The skill list is read once and every later step uses it.
SKILL_NAMES="$(toolkit_skill_names)"
if [ -z "$SKILL_NAMES" ]; then
    echo "ERROR: no <dir>/SKILL.md found under $REPO_ROOT — not a toolkit clone." >&2
    exit 1
fi
if [ -L "$SKILLS_VIEW" ] || { [ -e "$SKILLS_VIEW" ] && [ ! -d "$SKILLS_VIEW" ]; }; then
    echo "ERROR: $SKILLS_VIEW exists and is not a directory install.sh made. Move it aside, then re-run." >&2
    exit 1
fi

note "ADLC toolkit installer  (mode: $MODE)"
note "  repo root: $REPO_ROOT"
note "  ADLC_HOME: $ADLC_HOME_DIR ($(adlc_home_source))"
note ""
note "symlinks:"
ensure_symlink "$REPO_ROOT" "$CLAUDE_DIR/skills"
ensure_symlink "$REPO_ROOT/agents" "$CLAUDE_DIR/agents"
if [ "$ADLC_HOME_DIR" != "$CLAUDE_DIR" ]; then
    ensure_symlink "$REPO_ROOT" "$ADLC_HOME_DIR/skills"
    ensure_symlink "$REPO_ROOT/agents" "$ADLC_HOME_DIR/agents"
fi
note "skills view:"
ensure_skills_view
note "agents mount (~/.agents/skills):"
ensure_agents_mount
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
