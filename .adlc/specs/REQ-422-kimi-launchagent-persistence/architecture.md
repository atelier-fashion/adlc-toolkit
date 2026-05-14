# Architecture — REQ-422 LaunchAgent Persistence

## Approach

Add one helper script + one plist template + one new `install.sh` section. Single file
edit beyond the two new files. macOS-only behavior, gated cleanly on
`command -v launchctl`.

```
tools/kimi/
├── kimi-launchctl-setenv.sh.in    (NEW)  helper script template — install.sh
│                                          copies to ~/.claude/kimi-launchctl-setenv.sh
├── com.adlc-toolkit.kimi-setenv.plist.in (NEW)  LaunchAgent plist template — install.sh
│                                          substitutes the home path and writes to
│                                          ~/Library/LaunchAgents/
└── install.sh                     (MODIFIED) — new section after the existing
                                              launchctl setenv block:
                                              (1) write helper script,
                                              (2) write plist,
                                              (3) launchctl unload (silent if absent),
                                              (4) launchctl load.
```

## Key Decisions (ADRs)

### ADR-1: Helper script reads from rc files, not from the plist
The plist's `ProgramArguments` invokes `/bin/sh <helper-script>`. The helper reads the
key from `~/.zshrc` / `~/.bash_profile` / `~/.bashrc` at runtime and calls
`launchctl setenv`. **The plist contains no secret material** — only the path to the
helper. Plists are plaintext, end up in Time Machine + iCloud backups, and may sync to
other devices. Putting the key directly in the plist would leak it widely (BR-1).

### ADR-2: `awk` extraction, never `source`
The helper script uses `awk -F'"' '/^export MOONSHOT_API_KEY=/ {print $2; exit}'` to pull
the key value out of the first matching `export MOONSHOT_API_KEY="..."` line. **It does
NOT `source` or `eval` the rc file** — that would execute arbitrary user code at every
login, including any shell tricks lurking in the rc. The narrow `awk` form is robust to
the canonical export shape install.sh writes (LESSON-007 — scrub at every leak point).

### ADR-3: User-mode LaunchAgent (not system-mode)
The plist lives at `~/Library/LaunchAgents/`, not `/Library/LaunchAgents/` or
`/Library/LaunchDaemons/`. User-mode runs in the user's GUI session (which is what we
need — `launchctl setenv` must populate the user's session env, not the system's).
User-mode also avoids needing sudo at install time.

### ADR-4: `RunAtLoad=true, KeepAlive=false` — fire once per login
The script is idempotent (re-running `launchctl setenv` just overwrites) but there's no
reason to run it more than once per login. `KeepAlive=true` would cause launchd to
restart the script in a tight loop if anything ever exited non-zero — wrong shape for
this task.

### ADR-5: Helper exits 0 even on "no key found" (BR-5)
If the user removes the key from their rc (or never set it), the helper logs to stderr
and exits 0. Exiting non-zero would (with KeepAlive=false) be benign for launchd but
would clutter the launchd log with "exit status: 1" warnings on every login. Exit 0 +
log = the right signal.

### ADR-6: install.sh idempotency via unload-then-load
On re-run, install.sh does `launchctl bootout gui/$(id -u) <plist>` (or the older
`launchctl unload` fallback) before writing the new plist + loading it. This is the
launchd-canonical idempotent pattern; doing nothing if the plist is unchanged isn't
sufficient because we want re-runs to pick up bug fixes.

### ADR-7: Plist label uses reverse-DNS form
`com.adlc-toolkit.kimi-setenv` — follows Apple's LaunchAgent labeling convention. Lets
the user `launchctl list | grep adlc-toolkit` to inspect.

### ADR-8: Logs to `/tmp/kimi-launchctl-setenv.{out,err}`
Stdout + stderr go to `/tmp/` rather than `~/Library/Logs/` so they don't accumulate
across reboots (macOS wipes `/tmp/` on reboot). For debugging a "why isn't my key
loaded" situation, the user can `cat /tmp/kimi-launchctl-setenv.err` right after login.

## Task Breakdown

```
TASK-030  install.sh + helper script template + plist template — single task
          (small, all-in-one — helper, plist, install.sh integration, README update)
```

One task, no parallelism needed (small surface, all in install.sh's domain).
