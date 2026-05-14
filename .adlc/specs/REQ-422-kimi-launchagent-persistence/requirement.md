---
id: REQ-422
title: "Persistent MOONSHOT_API_KEY via macOS LaunchAgent — survives reboot, Cmd-Q, app updates"
status: draft
deployable: false
created: 2026-05-14
updated: 2026-05-14
component: "tools/kimi"
domain: "developer-experience"
stack: ["bash", "plist", "launchd"]
concerns: ["reliability", "privacy", "developer-experience"]
tags: ["kimi", "launchagent", "launchd", "persistence", "moonshot", "follow-up"]
---

## Description

REQ-415 added a one-shot `launchctl setenv MOONSHOT_API_KEY "$MOONSHOT_API_KEY"` step to
`install.sh`. That correctly populates the launchctl session env so that GUI-launched
Claude Code can inherit the key — **but only until the next reboot**. After reboot (or
after `launchctl unsetenv`), the env is empty and the user has to manually re-run the
step. In practice this means:

- Every macOS reboot → Kimi delegation silently falls back to Claude until the user
  re-runs `install.sh` from a terminal where the key is loaded.
- Even within a single boot, if Claude Code was launched (e.g. from Spotlight) **before**
  `launchctl setenv` ran, the app's process tree never sees the var. Bash subprocesses
  invoked by Claude inherit from Claude.app's env → `ask-kimi` exits with "key not set"
  → skill falls back to Claude. The user sees no Moonshot traffic and assumes Kimi isn't
  wired up.

This REQ adds a macOS **LaunchAgent** that runs at user login and re-exports
`MOONSHOT_API_KEY` into the launchctl session env. After it ships:

- Reboot → at login the agent runs → key is in the session env → any subsequent Claude
  Code launch inherits it.
- Cmd-Q + relaunch → the new Claude.app process inherits the (already-set) session env.
- App update → same.

**Key handling**: the plist itself MUST NOT contain the key value (plists end up in
Time Machine backups, iCloud, etc.). The LaunchAgent invokes a small helper script that
reads the key from the user's shell rc file at runtime and runs `launchctl setenv`.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| LaunchAgent plist | path | string | `~/Library/LaunchAgents/com.adlc-toolkit.kimi-setenv.plist` |
| LaunchAgent plist | Label | string | `com.adlc-toolkit.kimi-setenv` |
| LaunchAgent plist | RunAtLoad | bool | `true` (runs at every user login) |
| LaunchAgent plist | KeepAlive | bool | `false` (one-shot per login, exits after setenv) |
| setenv helper script | path | string | `~/.claude/kimi-launchctl-setenv.sh` |
| setenv helper script | reads from | string | first matching rc file in `~/.zshrc`, `~/.bash_profile`, `~/.bashrc` |
| install.sh integration | install action | bool | `install.sh` writes the script + plist, then `launchctl load`s the agent |
| install.sh integration | re-install action | bool | idempotent — `launchctl unload` + write + `launchctl load`; produces no duplicate state |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| user logs in | macOS login | LaunchAgent fires, helper script reads key from rc, runs `launchctl setenv` |
| install.sh run | user re-runs installer | plist + script regenerated; agent unloaded + reloaded |
| user updates key in `~/.zshrc` | manual edit | takes effect on next login; for current session, user runs `launchctl setenv ...` once manually OR logs out + back in |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| run the LaunchAgent | the logged-in user only (`~/Library/LaunchAgents` is user-scoped, not system-scoped) |
| read the key from rc | the helper script (user-mode, no sudo) |

## Business Rules

- [ ] BR-1: The plist file MUST NOT contain the literal `MOONSHOT_API_KEY` value. The
      agent invokes a helper script which reads the key from rc at runtime — plaintext
      key never lands in Time Machine / iCloud / `~/Library/LaunchAgents/`.
- [ ] BR-2: The LaunchAgent MUST be macOS-only. On Linux or any non-macOS host,
      `install.sh` must skip the plist + agent steps silently (the existing `launchctl
      setenv` block already does this — extend the pattern).
- [ ] BR-3: After install + log-out + log-in (no terminal interaction), `launchctl getenv
      MOONSHOT_API_KEY` MUST return the key in any new terminal AND in any new GUI app
      including Claude Code launched from Spotlight.
- [ ] BR-4: Re-running `install.sh` MUST be idempotent — no duplicate plist files, no
      duplicate `launchctl load` errors, no orphaned agent registrations.
- [ ] BR-5: The helper script MUST search for `MOONSHOT_API_KEY` in `~/.zshrc` first,
      then `~/.bash_profile`, then `~/.bashrc`. First match wins. If none found, the
      script logs a one-line message to its stdout/stderr (which goes to the launchd log)
      and exits 0 (NOT non-zero — exiting non-zero would cause launchd to try to restart).
- [ ] BR-6: The helper script MUST extract the key value safely — match the exact form
      `export MOONSHOT_API_KEY="..."` with `awk` and capture only the quoted value. Do
      NOT `eval` or `source` the rc file (avoids running arbitrary user code at login).
- [ ] BR-7: The plist's `Label` MUST be `com.adlc-toolkit.kimi-setenv` (reverse-DNS form
      per Apple convention). `RunAtLoad=true`, `KeepAlive=false` (one-shot).
- [ ] BR-8: `install.sh` MUST gracefully `launchctl unload` any existing agent before
      writing the new plist, then `launchctl load` the new one. If the agent doesn't
      exist yet, the unload step skips silently.
- [ ] BR-9: The plist MUST write its stdout + stderr to a known path
      (`/tmp/kimi-launchctl-setenv.{out,err}`) for debuggability. These files are
      transient — `/tmp` is wiped on reboot — so they don't accumulate.
- [ ] BR-10: The README troubleshooting section from REQ-415 MUST be updated to reflect
      the new permanent behavior: users no longer need to manually `launchctl setenv`
      after rebooting. Note the one remaining manual step: when changing the key in
      `~/.zshrc`, the user must log out + back in OR run `launchctl setenv` once for the
      current session.
- [ ] BR-11: REQ-415's existing pytest suite MUST still report 29/29 passing.

## Acceptance Criteria

- [ ] After `bash tools/kimi/install.sh` on macOS, the file
      `~/Library/LaunchAgents/com.adlc-toolkit.kimi-setenv.plist` exists and is a valid
      property list (verified by `plutil -lint`).
- [ ] After `install.sh`, the file `~/.claude/kimi-launchctl-setenv.sh` exists, is
      executable, and `bash -n` passes.
- [ ] `grep -c 'MOONSHOT_API_KEY' ~/Library/LaunchAgents/com.adlc-toolkit.kimi-setenv.plist`
      may show `MOONSHOT_API_KEY` as a string token (for documentation) but the actual
      key value MUST NOT appear there (verified by `grep -F "$MOONSHOT_API_KEY" <plist>`
      returning no match).
- [ ] After `install.sh`, `launchctl list | grep com.adlc-toolkit.kimi-setenv` shows the
      agent loaded.
- [ ] After log-out + log-in (or `launchctl kickstart -k gui/$(id -u)/com.adlc-toolkit.kimi-setenv`
      as a faster equivalent), `launchctl getenv MOONSHOT_API_KEY` returns the key.
- [ ] After quitting Claude Code (Cmd-Q) and re-launching from Spotlight, the new app
      process inherits the var — verified by invoking the Bash tool in a fresh session
      and running `bash -c 'echo $\{MOONSHOT_API_KEY:+set\}'` → prints `set`.
- [ ] Re-running `install.sh` produces no duplicate plist, no duplicate load error, no
      orphaned agent.
- [ ] On a non-macOS host (no `launchctl`), `install.sh` skips the LaunchAgent steps
      cleanly — no error.
- [ ] The plist + helper script handle a missing key in rc files (BR-5) without raising
      an error and without leaving the agent in a respawn loop.
- [ ] tools/kimi/README.md "Troubleshooting" section reflects the new permanent
      behavior; the one remaining manual step (key change → log out / re-setenv) is
      documented.
- [ ] REQ-413's pytest suite reports 29/29 passing.

## External Dependencies

- `launchctl` and `launchd` — macOS built-ins. Already used in REQ-415.
- No new third-party packages.

## Assumptions

- The user's login shell rc is one of `~/.zshrc`, `~/.bash_profile`, `~/.bashrc`. Other
  shells (fish, csh, nu) print a manual-instructions message — same out-of-scope policy
  as REQ-415 BR-3.
- The user-mode LaunchAgent runs in the user's GUI session; `launchctl setenv` from a
  user-mode agent correctly populates the session env that GUI app launches inherit.
  (Verified pattern; this is exactly how Homebrew + nvm setups do macOS env injection.)
- The helper script's `awk`-extraction approach is sufficient for the canonical
  `export VAR="value"` form. Multi-line exports or shell-substitution forms are not
  supported — install.sh writes the canonical form, so this is consistent.

## Open Questions

- [ ] OQ-1: Should the helper also export future vars (e.g. `KIMI_MODEL`,
      `ADLC_DISABLE_KIMI`)? Recommend: only `MOONSHOT_API_KEY` for this REQ — the others
      are either user-mode opt-outs (DISABLE) or have safe defaults (MODEL).
- [ ] OQ-2: Should we use macOS Keychain instead of reading from rc? Keychain is more
      secure (encrypted at rest, ACL-gated) but adds complexity (the `security` CLI,
      Keychain access prompts at first run). Recommend: defer to a future REQ; for now
      keep the existing "key in rc" pattern.
- [ ] OQ-3: Should `install.sh` detect the case where the user has previously hand-run
      `launchctl setenv MOONSHOT_API_KEY` and warn about the now-redundant manual step?
      Recommend: just leave that running; the new agent will overwrite at next login;
      no warning needed.

## Out of Scope

- Persistent storage of any other env var (`KIMI_MODEL`, `ADLC_DISABLE_KIMI`, etc.).
- Linux / non-macOS persistent-env support — different mechanism, different scope.
- macOS Keychain integration for key storage.
- A GUI for editing the key.
- Rotation / expiry policy for keys.

## Retrieved Context

- LESSON-006: tools/ carve-out + fail-loud installers — informs BR-4, BR-8 (idempotency,
  silent skip on non-macOS).
- LESSON-007: scrub-at-every-leak-point — informs BR-1 (no plaintext key in plist), BR-6
  (no `eval`/`source` of rc files).
- LESSON-008: skill delegation = untrusted data — not directly relevant; this REQ doesn't
  cross any LLM delegation boundary.
- LESSON-009: post-merge `/analyze` finds what verify misses — informs wrapup
  recommendation (run `/analyze` after this lands).

REQ-412, REQ-415 are direct ancestors (`status: complete`). REQ-416 (toolkit refactor,
`draft`) is unrelated; this REQ does not touch any of REQ-416's scope.
