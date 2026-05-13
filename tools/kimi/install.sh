#!/bin/sh
# Idempotent installer for the Kimi delegation CLIs.
# POSIX sh only — no bashisms, no GNU-specific flags.
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="$HOME/.claude/kimi-venv"
BIN_DIR="$HOME/bin"
ZSHRC="$HOME/.zshrc"
PATH_MARKER="# added by adlc-toolkit kimi install.sh"

CLIS="ask-kimi kimi-write extract-chat"

# --- venv ---------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv at $VENV_DIR"
    mkdir -p "$HOME/.claude"
    python3 -m venv "$VENV_DIR"
fi
echo "Installing/upgrading openai into venv"
"$VENV_DIR/bin/pip" install --upgrade openai

# --- ~/bin wrappers (regenerated each run) ------------------------------
mkdir -p "$BIN_DIR"
for name in $CLIS; do
    wrapper="$BIN_DIR/$name"
    cat > "$wrapper" <<EOF
#!/bin/sh
exec "$VENV_DIR/bin/python3" "$REPO_ROOT/tools/kimi/$name" "\$@"
EOF
    chmod +x "$wrapper"
    echo "Wrote wrapper $wrapper"
done

# --- PATH entry in ~/.zshrc (marker-guarded) ----------------------------
case ":$PATH:" in
    *":$BIN_DIR:"*)
        : # already on PATH
        ;;
    *)
        if [ -f "$ZSHRC" ] && grep -F "$PATH_MARKER" "$ZSHRC" >/dev/null 2>&1; then
            echo "PATH entry already present in $ZSHRC"
        else
            echo "Appending ~/bin to PATH in $ZSHRC"
            {
                echo ""
                echo "$PATH_MARKER"
                echo 'export PATH="$HOME/bin:$PATH"'
            } >> "$ZSHRC"
        fi
        ;;
esac

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
    "$VENV_DIR/bin/python3" - "$SETTINGS" <<'PYEOF'
import json, sys
path = sys.argv[1]
with open(path) as f:
    data = json.load(f)
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
with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PYEOF
    echo "Merged Kimi allowlist entries into $SETTINGS"
else
    echo ""
    echo "Note: $SETTINGS does not exist — not creating it."
    echo "Add these to its permissions.allow list manually:"
    echo '  "Bash(ask-kimi:*)", "Bash(kimi-write:*)", "Bash(extract-chat:*)"'
fi

# --- next steps ---------------------------------------------------------
echo ""
echo "Done. Restart your shell (or 'source ~/.zshrc') and set MOONSHOT_API_KEY."
