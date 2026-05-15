#!/bin/sh
# Idempotent installer for the Kimi delegation CLIs.
# POSIX sh only — no bashisms, no GNU-specific flags.
set -eu

# Resolve REPO_ROOT to the CANONICAL repo, not any worktree (e.g. Claude Code's
# per-session `.claude/worktrees/<id>` or ADLC pipeline `.worktrees/REQ-xxx`).
# Wrappers must point at a path that survives session/pipeline cleanup. We use
# `git rev-parse --git-common-dir` which returns the canonical .git directory
# regardless of which worktree is calling — its parent is the canonical repo
# root. Fall back to the script-relative path if git isn't available.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMMON_DIR="$(git -C "$SCRIPT_DIR" rev-parse --git-common-dir 2>/dev/null || true)"
if [ -n "$COMMON_DIR" ]; then
    case "$COMMON_DIR" in
        /*) ;;
        *)  COMMON_DIR="$(cd "$SCRIPT_DIR" && cd "$COMMON_DIR" 2>/dev/null && pwd || echo "")" ;;
    esac
fi
if [ -n "$COMMON_DIR" ] && [ -d "$COMMON_DIR" ]; then
    REPO_ROOT="$(dirname "$COMMON_DIR")"
else
    REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
# Sanity check — the resolved REPO_ROOT must contain tools/kimi/ask-kimi.
if [ ! -f "$REPO_ROOT/tools/kimi/ask-kimi" ]; then
    echo "ERROR: could not resolve canonical repo root (tried $REPO_ROOT). Re-run install.sh from the repo's tools/kimi/ directory." >&2
    exit 1
fi
VENV_DIR="$HOME/.claude/kimi-venv"
BIN_DIR="$HOME/bin"
PATH_MARKER="# added by adlc-toolkit kimi install.sh"

# Determine the user's persistent login shell — fall back to $SHELL.
# `dscl` is macOS-only; guard with command -v so the script works on Linux too.
# `|| true` keeps set -eu from aborting if dscl exits nonzero on a fluke.
USER_NAME="${USER:-$(id -un 2>/dev/null || echo "")}"
LOGIN_SHELL=""
if command -v dscl >/dev/null 2>&1 && [ -n "$USER_NAME" ]; then
    LOGIN_SHELL=$(dscl . -read "/Users/$USER_NAME" UserShell 2>/dev/null | awk '{print $2}' || true)
fi
[ -z "$LOGIN_SHELL" ] && LOGIN_SHELL="${SHELL:-}"
case "$(basename "$LOGIN_SHELL")" in
    zsh*)  RC="$HOME/.zshrc" ;;
    bash*) RC="$HOME/.bash_profile" ;;
    *)     RC="" ;;
esac

CLIS="ask-kimi kimi-write extract-chat"

# --- venv ---------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv at $VENV_DIR"
    mkdir -p "$HOME/.claude"
    python3 -m venv "$VENV_DIR"
fi
echo "Installing pinned dependencies from requirements.txt into venv"
"$VENV_DIR/bin/pip" install -r "$REPO_ROOT/tools/kimi/requirements.txt"

# --- ~/bin wrappers (regenerated each run) ------------------------------
# Note: wrappers are path-stamped to this repo's location ($REPO_ROOT).
# If you move the toolkit clone, re-run this script to regenerate them.
mkdir -p "$BIN_DIR"
for name in $CLIS; do
    wrapper="$BIN_DIR/$name"
    cat > "$wrapper" <<EOF
#!/bin/sh
exec "$VENV_DIR/bin/python3" "$REPO_ROOT/tools/kimi/$name" "\$@"
EOF
    chmod +x "$wrapper"
    echo "Wrote wrapper $wrapper (-> $REPO_ROOT/tools/kimi/$name)"
done

# --- PATH entry in shell rc (marker-guarded) ----------------------------
# Idempotency is keyed solely on the marker line — do not also gate on the
# current shell's $PATH, since a non-login shell may not have run the rc yet.
if [ -n "$RC" ]; then
    if [ -f "$RC" ] && grep -F "$PATH_MARKER" "$RC" >/dev/null 2>&1; then
        echo "PATH entry already present in $RC"
    else
        echo "Appending ~/bin to PATH in $RC"
        {
            echo ""
            echo "$PATH_MARKER"
            echo 'export PATH="$HOME/bin:$PATH"'
        } >> "$RC"
    fi
else
    echo "Login shell $(basename "$LOGIN_SHELL") not auto-supported — add these lines manually to your shell rc:"
    echo "    $PATH_MARKER"
    echo '    export PATH="$HOME/bin:$PATH"'
    echo '    export MOONSHOT_API_KEY="..."'
fi

# --- launchctl setenv for GUI-launched apps (macOS only) ---------------
# Fast-path for the current boot session (the LaunchAgent below makes this
# permanent across future reboots, but the agent only fires at next login).
if command -v launchctl >/dev/null 2>&1; then
    if [ -n "${MOONSHOT_API_KEY:-}" ]; then
        launchctl setenv MOONSHOT_API_KEY "$MOONSHOT_API_KEY"
        echo "Exported MOONSHOT_API_KEY into launchctl session env (current boot — LaunchAgent below handles future reboots)"
    else
        echo "Skipping launchctl setenv: MOONSHOT_API_KEY not set in this shell"
    fi
fi

# --- LaunchAgent persistence (macOS only) -------------------------------
# Installs a LaunchAgent that runs at every user login and re-exports
# MOONSHOT_API_KEY into the launchctl session env, surviving reboots and
# Claude Code restarts. The plist itself never contains the key value —
# the agent invokes a helper script that reads from the rc file at runtime.
#
# Security note: `launchctl setenv` puts the key in the session env, where
# any GUI app the user launches can read it via `launchctl getenv` or its
# own process env. This is the deliberate trade-off of the feature (enables
# GUI-launched Claude Code to see the key). A compromised user-space process
# already has access to ~/.zshrc anyway.
if command -v launchctl >/dev/null 2>&1; then
    AGENT_LABEL="com.adlc-toolkit.kimi-setenv"
    AGENT_PLIST="$HOME/Library/LaunchAgents/$AGENT_LABEL.plist"
    AGENT_HELPER="$HOME/.claude/kimi-launchctl-setenv.sh"
    HELPER_SRC="$REPO_ROOT/tools/kimi/kimi-launchctl-setenv.sh.in"
    PLIST_SRC="$REPO_ROOT/tools/kimi/com.adlc-toolkit.kimi-setenv.plist.in"

    mkdir -p "$HOME/Library/LaunchAgents"
    mkdir -p "$HOME/Library/Logs"

    # Ensure existing telemetry log is owner-readable only (REQ-424 BR-11).
    # Idempotent — emit-telemetry.sh creates the log via umask 077 on first write,
    # but if a prior install or manual touch left it world-readable, fix it here.
    TELEMETRY_LOG="$HOME/Library/Logs/adlc-skill-telemetry.log"
    if [ -f "$TELEMETRY_LOG" ]; then
        chmod 600 "$TELEMETRY_LOG"
        echo "Ensured $TELEMETRY_LOG has mode 0600"
    fi

    # ORDER MATTERS: bootout FIRST (so no live agent is mid-execution while
    # we overwrite its files), THEN write files, THEN bootstrap (loads new).
    launchctl bootout "gui/$(id -u)" "$AGENT_PLIST" 2>/dev/null || true

    # Write helper script (copy — plist invokes via /bin/sh <script>; +x harmless but kept for direct-invoke debugging)
    cp "$HELPER_SRC" "$AGENT_HELPER"
    chmod +x "$AGENT_HELPER"

    # Write plist with $HOME substituted (plist needs absolute path, not $HOME var)
    sed "s|__HOME__|$HOME|g" "$PLIST_SRC" > "$AGENT_PLIST"

    # Validate the plist BEFORE attempting to load — catches a malformed
    # template / failed substitution at install time rather than at next login.
    if ! plutil -lint "$AGENT_PLIST" >/dev/null 2>&1; then
        echo "WARNING: generated plist at $AGENT_PLIST failed plutil -lint — agent NOT loaded."
        echo "  This is a bug in install.sh's plist template substitution. File an issue with the contents of $AGENT_PLIST."
    elif launchctl bootstrap "gui/$(id -u)" "$AGENT_PLIST" 2>/dev/null; then
        echo "Loaded LaunchAgent $AGENT_LABEL (persistent across reboots)"
    else
        # Fall back to legacy load form on older macOS
        if launchctl load "$AGENT_PLIST" 2>/dev/null; then
            echo "Loaded LaunchAgent $AGENT_LABEL (persistent across reboots) [legacy form]"
        else
            echo "WARNING: could not load LaunchAgent at $AGENT_PLIST — env will NOT persist across reboots."
            echo "  Manual workaround: run 'launchctl setenv MOONSHOT_API_KEY \"\$MOONSHOT_API_KEY\"' after each reboot."
        fi
    fi
fi

# --- MOONSHOT_API_KEY reminder (printed, never written) -----------------
echo ""
REMINDER_RC="${RC:-your shell rc file}"
echo "Reminder: add the following to $REMINDER_RC (not done automatically):"
echo '  export MOONSHOT_API_KEY="<your-key-here>"'
if [ -n "${MOONSHOT_API_KEY:-}" ]; then
    echo "  (MOONSHOT_API_KEY is currently set in this shell)"
else
    echo "  (MOONSHOT_API_KEY is currently NOT set in this shell)"
fi

# --- CLAUDE.md routing block (marker-guarded append) --------------------
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
README="$REPO_ROOT/tools/kimi/README.md"
mkdir -p "$HOME/.claude"
if [ -f "$CLAUDE_MD" ] && grep -q 'kimi-delegation:start' "$CLAUDE_MD"; then
    echo "Kimi routing block already present in $CLAUDE_MD"
else
    echo "Appending Kimi routing block to $CLAUDE_MD"
    {
        echo ""
        sed -n '/kimi-delegation:start/,/kimi-delegation:end/p' "$README"
    } >> "$CLAUDE_MD"
fi

# --- settings.json allowlist merge --------------------------------------
SETTINGS="$HOME/.claude/settings.json"
if [ -f "$SETTINGS" ]; then
    cp "$SETTINGS" "$SETTINGS.bak"
    echo "Backed up $SETTINGS to $SETTINGS.bak"
    if "$VENV_DIR/bin/python3" - "$SETTINGS" <<'PYEOF'
import json, os, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except json.JSONDecodeError as exc:
    sys.exit(f"{path} is not valid JSON ({exc}); not modified — fix it and re-run.")
if not isinstance(data, dict):
    sys.exit(f"{path} top level is not a JSON object; not modified.")
perms = data.get("permissions")
if not isinstance(perms, dict):
    perms = {}
    data["permissions"] = perms
allow = perms.get("allow")
if not isinstance(allow, list):
    allow = []
    perms["allow"] = allow
for entry in ("Bash(ask-kimi:*)", "Bash(kimi-write:*)", "Bash(extract-chat:*)"):
    if entry not in allow:
        allow.append(entry)
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, path)
PYEOF
    then
        echo "Merged Kimi allowlist entries into $SETTINGS"
    else
        echo "WARNING: could not update $SETTINGS — add these to its permissions.allow manually:"
        echo '  "Bash(ask-kimi:*)", "Bash(kimi-write:*)", "Bash(extract-chat:*)"'
    fi
else
    echo ""
    echo "Note: $SETTINGS does not exist — not creating it."
    echo "Add these to its permissions.allow list manually:"
    echo '  "Bash(ask-kimi:*)", "Bash(kimi-write:*)", "Bash(extract-chat:*)"'
fi

# --- next steps ---------------------------------------------------------
echo ""
if [ -n "${RC:-}" ]; then
    echo "Done. Restart your shell (or 'source $RC') and set MOONSHOT_API_KEY."
else
    echo "Done. Add the lines above to your shell rc, then restart your shell, and set MOONSHOT_API_KEY."
fi
