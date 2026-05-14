---
id: TASK-030
title: "Add LaunchAgent helper + plist templates + install.sh integration for persistent MOONSHOT_API_KEY"
status: complete
parent: REQ-422
created: 2026-05-14
updated: 2026-05-14
dependencies: []
---

## Description

One task delivering the full LaunchAgent persistence story: a helper shell script, a
LaunchAgent plist template, install.sh integration that writes both + loads the agent
idempotently, and a README update reflecting the new permanent behavior.

## Files to Create/Modify

### CREATE: `tools/kimi/kimi-launchctl-setenv.sh.in`

Helper script template. `install.sh` copies this to `~/.claude/kimi-launchctl-setenv.sh`
and `chmod +x` it. The `.in` suffix marks it as a template (no substitution actually
needed in this task — the script is self-contained — but the suffix signals install-time
copy and matches what TASK-031 might later add).

Contents:

```sh
#!/bin/sh
# Run by ~/Library/LaunchAgents/com.adlc-toolkit.kimi-setenv.plist at every user login.
# Pulls MOONSHOT_API_KEY from the user's shell rc and seeds the launchctl session env
# so GUI-launched apps (Claude Code from Spotlight, etc.) inherit the var.
#
# Safety: extracts only the literal `export MOONSHOT_API_KEY="..."` value with awk.
# Does NOT source or eval the rc file (avoids running arbitrary user code at login).
# Exits 0 on missing key (KeepAlive=false in the plist; non-zero would just clutter logs).
set -u

LOG="/tmp/kimi-launchctl-setenv.log"
echo "[$(date '+%Y-%m-%dT%H:%M:%S')] kimi-launchctl-setenv starting" >> "$LOG"

KEY=""
for rc in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc"; do
    if [ -r "$rc" ]; then
        K=$(awk -F'"' '/^export MOONSHOT_API_KEY=/ { print $2; exit }' "$rc" 2>/dev/null || true)
        if [ -n "$K" ]; then
            KEY="$K"
            echo "[$(date '+%Y-%m-%dT%H:%M:%S')] found key in $rc" >> "$LOG"
            break
        fi
    fi
done

if [ -n "$KEY" ]; then
    launchctl setenv MOONSHOT_API_KEY "$KEY"
    echo "[$(date '+%Y-%m-%dT%H:%M:%S')] launchctl setenv MOONSHOT_API_KEY done (length=${#KEY})" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%dT%H:%M:%S')] no MOONSHOT_API_KEY found in any rc file — skipping" >> "$LOG"
fi

exit 0
```

### CREATE: `tools/kimi/com.adlc-toolkit.kimi-setenv.plist.in`

LaunchAgent plist template. `install.sh` substitutes `__HOME__` and copies to
`~/Library/LaunchAgents/com.adlc-toolkit.kimi-setenv.plist`.

Contents:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.adlc-toolkit.kimi-setenv</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/sh</string>
        <string>__HOME__/.claude/kimi-launchctl-setenv.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardErrorPath</key>
    <string>/tmp/kimi-launchctl-setenv.err</string>
    <key>StandardOutPath</key>
    <string>/tmp/kimi-launchctl-setenv.out</string>
</dict>
</plist>
```

### MODIFY: `tools/kimi/install.sh`

Add a new section AFTER the existing `# --- launchctl setenv for GUI-launched apps`
block, BEFORE the `# --- MOONSHOT_API_KEY reminder` block. The new section:

```sh
# --- LaunchAgent persistence (macOS only) -------------------------------
# Installs a LaunchAgent that runs at every login and re-exports
# MOONSHOT_API_KEY into the launchctl session env, surviving reboots and
# Claude Code restarts. The plist itself never contains the key value —
# the agent invokes a helper script that reads from the rc file at runtime.
if command -v launchctl >/dev/null 2>&1; then
    AGENT_LABEL="com.adlc-toolkit.kimi-setenv"
    AGENT_PLIST="$HOME/Library/LaunchAgents/$AGENT_LABEL.plist"
    AGENT_HELPER="$HOME/.claude/kimi-launchctl-setenv.sh"
    HELPER_SRC="$REPO_ROOT/tools/kimi/kimi-launchctl-setenv.sh.in"
    PLIST_SRC="$REPO_ROOT/tools/kimi/com.adlc-toolkit.kimi-setenv.plist.in"

    mkdir -p "$HOME/Library/LaunchAgents"

    # Write helper script (copy + chmod)
    cp "$HELPER_SRC" "$AGENT_HELPER"
    chmod +x "$AGENT_HELPER"

    # Write plist with $HOME substituted (plist needs absolute path, not $HOME var)
    sed "s|__HOME__|$HOME|g" "$PLIST_SRC" > "$AGENT_PLIST"

    # Idempotent reload: unload first (silent if not loaded), then load
    launchctl bootout "gui/$(id -u)" "$AGENT_PLIST" 2>/dev/null || true
    if launchctl bootstrap "gui/$(id -u)" "$AGENT_PLIST" 2>/dev/null; then
        echo "Loaded LaunchAgent $AGENT_LABEL (persistent across reboots)"
    else
        # Fall back to legacy load/unload form on older macOS
        launchctl unload "$AGENT_PLIST" 2>/dev/null || true
        if launchctl load "$AGENT_PLIST" 2>/dev/null; then
            echo "Loaded LaunchAgent $AGENT_LABEL (persistent across reboots) [legacy form]"
        else
            echo "WARNING: could not load LaunchAgent at $AGENT_PLIST — env will NOT persist across reboots."
            echo "  Manual workaround: run 'launchctl setenv MOONSHOT_API_KEY \"\$MOONSHOT_API_KEY\"' after each reboot."
        fi
    fi
fi
```

### MODIFY: `tools/kimi/README.md`

Update the existing `### Troubleshooting` section's two bullets to reflect the new
permanent behavior:

- Replace the first bullet (GUI-launched Claude Code can't see your key) with: a brief
  note that `install.sh` now installs a LaunchAgent that re-populates the key at every
  login, so the GUI-inheritance problem self-heals after reboot. Add one sentence
  about the rare case where the user changes the key in `~/.zshrc`: in that case run
  `launchctl setenv MOONSHOT_API_KEY "$MOONSHOT_API_KEY"` once to update the current
  session (or log out + back in for it to take effect via the LaunchAgent).
- Add a third bullet: how to inspect the agent — `launchctl list | grep adlc-toolkit`
  to confirm it's loaded; `cat /tmp/kimi-launchctl-setenv.log` to see what it did at
  last login.

Keep the existing `~/.bash_profile` bullet about bash login shells unchanged.

## Acceptance Criteria

- [ ] After `bash tools/kimi/install.sh` on macOS, both files exist:
  - `~/.claude/kimi-launchctl-setenv.sh` (executable)
  - `~/Library/LaunchAgents/com.adlc-toolkit.kimi-setenv.plist`
- [ ] `plutil -lint ~/Library/LaunchAgents/com.adlc-toolkit.kimi-setenv.plist` reports OK.
- [ ] `grep -F "$MOONSHOT_API_KEY" ~/Library/LaunchAgents/com.adlc-toolkit.kimi-setenv.plist`
      returns NO match (the literal key value is NOT in the plist — BR-1).
- [ ] `launchctl list | grep com.adlc-toolkit.kimi-setenv` shows the agent loaded after
      install.sh ran successfully.
- [ ] Manually running the helper script (`sh ~/.claude/kimi-launchctl-setenv.sh`) then
      `launchctl getenv MOONSHOT_API_KEY` returns the key value.
- [ ] `cat /tmp/kimi-launchctl-setenv.log` shows the helper found the key and ran the
      setenv (path checked, length logged — NOT the key value).
- [ ] Re-running `install.sh` produces no duplicate plist, no orphaned agent, no
      "already loaded" error visible to the user.
- [ ] `bash -n tools/kimi/install.sh` passes.
- [ ] `bash -n tools/kimi/kimi-launchctl-setenv.sh.in` passes.
- [ ] On a non-macOS host (no `launchctl`), the entire LaunchAgent block is skipped
      (no error, no file written).
- [ ] If `MOONSHOT_API_KEY` is not present in any rc, helper logs the miss and exits 0
      — agent does not enter a respawn loop.
- [ ] tools/kimi/README.md Troubleshooting section reflects the new persistent
      behavior.
- [ ] REQ-413's pytest suite still reports 29/29 passing.

## Technical Notes

- `launchctl bootout` / `bootstrap` are the modern (10.10+) idempotent commands.
  Fall back to `unload` / `load` if `bootstrap` fails. Both forms produce the same
  state — pick whichever the OS supports.
- The plist path substitution uses `sed s|__HOME__|$HOME|g` — `|` as delimiter avoids
  conflict with `/` in paths.
- The helper writes to a log at `/tmp/kimi-launchctl-setenv.log` (NOT the plist's
  StandardOutPath, which is `.out` / `.err` — those receive whatever the script
  prints AND any launchd-side output). Both paths in `/tmp/` are wiped on reboot,
  consistent with the "transient" design.
- Do NOT touch `_common.py`, `ask-kimi`, `kimi-write`, `extract-chat`, or any SKILL.md
  file in this task.
- The agent is user-mode (`~/Library/LaunchAgents/`), not system-mode — no sudo
  required at install time.
