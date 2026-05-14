#!/bin/sh
# Idempotent installer for the Kimi delegation CLIs.
# POSIX sh only — no bashisms, no GNU-specific flags.
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="$HOME/.claude/kimi-venv"
BIN_DIR="$HOME/bin"
PATH_MARKER="# added by adlc-toolkit kimi install.sh"

# Determine the user's persistent login shell — fall back to $SHELL.
LOGIN_SHELL=$(dscl . -read "/Users/$USER" UserShell 2>/dev/null | awk '{print $2}')
[ -z "$LOGIN_SHELL" ] && LOGIN_SHELL="${SHELL:-}"
case "$(basename "$LOGIN_SHELL")" in
    zsh)  RC="$HOME/.zshrc" ;;
    bash) RC="$HOME/.bash_profile" ;;
    *)    RC="" ;;
esac

CLIS="ask-kimi kimi-write extract-chat"

# --- venv ---------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv at $VENV_DIR"
    mkdir -p "$HOME/.claude"
    python3 -m venv "$VENV_DIR"
fi
echo "Installing/upgrading openai + pytest into venv"
"$VENV_DIR/bin/pip" install --upgrade openai pytest

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
if command -v launchctl >/dev/null 2>&1; then
    if [ -n "${MOONSHOT_API_KEY:-}" ]; then
        launchctl setenv MOONSHOT_API_KEY "$MOONSHOT_API_KEY"
        echo "Exported MOONSHOT_API_KEY into launchctl session env (visible to GUI-launched Claude Code until reboot)"
    else
        echo "Skipping launchctl setenv: MOONSHOT_API_KEY not set in this shell"
    fi
fi

# --- MOONSHOT_API_KEY reminder (printed, never written) -----------------
echo ""
echo "Reminder: add the following to ~/.zshrc (not done automatically):"
echo '  export MOONSHOT_API_KEY="..."'
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
echo "Done. Restart your shell (or 'source ~/.zshrc') and set MOONSHOT_API_KEY."
