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

# --- next steps ---------------------------------------------------------
echo ""
echo "Next steps (TASK-017): the CLAUDE.md routing block and the settings.json"
echo "allowlist for these CLIs are not installed yet — see REQ-412 TASK-017."
