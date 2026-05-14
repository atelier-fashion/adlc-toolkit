---
id: LESSON-011
title: "macOS process-env inheritance is one-way and frozen-at-fork; the only reliable way to get a key into a GUI-launched app's subprocesses is to make the app re-read it at runtime — design a self-healing rc-fallback into the tool, not just the installer"
component: "tools/kimi"
domain: "developer-experience"
stack: ["python", "bash", "launchd", "macos"]
concerns: ["reliability", "env-inheritance", "developer-experience"]
tags: ["launchctl", "rc-fallback", "env-inheritance", "kimi", "macos", "self-healing"]
req: REQ-422
created: 2026-05-14
updated: 2026-05-14
---

## What Happened

REQ-412..REQ-417 shipped a working Kimi delegation tooling. The user reported almost no
Moonshot traffic despite invoking `/analyze`, `/wrapup`, `/spec` repeatedly across sessions.
Each diagnostic round looked like a one-off, but they were the same root cause stacked
five different ways:

1. REQ-412: `MOONSHOT_API_KEY` lives in `~/.zshrc`. Works in terminal-launched zsh.
2. REQ-415: GUI-launched Claude Code (from Spotlight/Dock) doesn't source `~/.zshrc` —
   added `launchctl setenv MOONSHOT_API_KEY` to `install.sh` so the launchctl session
   env carries it. Works until reboot.
3. After reboot: launchctl session env is empty until something repopulates it. Added
   REQ-422's LaunchAgent (`com.adlc-toolkit.kimi-setenv`) to run at every login and
   re-export the key. Works for future Claude Code launches.
4. **Still broke for the running app**: if Claude.app was launched BEFORE `launchctl
   setenv` ran (typical after reboot, before the user even thinks about Kimi), its
   process tree inherited an empty env. Every Bash subprocess thereafter — including
   every `ask-kimi` call — sees no key, exits "not set," and the skill falls back to
   Claude silently. No traffic to Moonshot, user thinks Kimi isn't wired up.
5. **The fix**: add a last-resort rc-file fallback inside `_common.get_client()`. When
   `os.environ[MOONSHOT_API_KEY]` is empty, read it directly from `~/.zshrc` /
   `~/.bash_profile` / `~/.bashrc` with a narrow `awk`-style extraction. **No
   `source`/`eval`** — safe even if the rc has arbitrary shell code.

After REQ-422 shipped, the empirical test in /wrapup itself: `ask-kimi` returned exit 0
with a real 798-char Moonshot response, in this same already-running Claude Code process
that had been stuck for hours. The rc-fallback works.

## Lesson

1. **macOS env inheritance is frozen-at-fork.** A running process never picks up env
   changes from outside — `launchctl setenv`, `~/.zshrc` edits, anything. There is no
   "refresh the env" API. The only escape is a new process — or having the tool
   bypass env entirely.
2. **Don't design tool reliability on env propagation alone.** If your tool depends on a
   secret being in `os.environ`, you've coupled correctness to "when was this process
   launched relative to when the secret got set up?" That dependency is invisible until
   it fails silently, and on macOS it WILL fail silently the first time a user opens
   your dependent app before running your installer.
3. **The fix shape is "self-healing": let the tool fall back to reading the canonical
   source of truth at runtime.** For Kimi, the canonical source is `~/.zshrc`. For
   other tools it might be `~/.config/<tool>/credentials` or a Keychain entry. Whatever
   it is, the tool — not just the installer — needs to be able to find the secret
   without depending on env propagation having worked at launch time.
4. **A LaunchAgent is necessary but not sufficient.** It fixes "future GUI launches see
   the env." It does NOT fix "the GUI app that's already running can't see the env." Both
   problems need to be addressed; only the rc-fallback addresses the second.
5. **Safety on the rc-read path: `awk`, never `source`.** Reading user-controlled shell
   files at runtime is fine — running them is not. A 5-line `awk` extraction over a
   canonical `export VAR="value"` form is robust and audit-friendly (LESSON-007's
   "scrub at every leak point" applies here too: the rc file is one of those points).

## Why It Matters

The failure mode here was epistemic, not just operational. Each diagnostic round produced
a "fix" that worked in some condition the user didn't always meet — and there was no
in-band signal when the fix didn't apply (the skill silently falls back to Claude). Five
REQs in, the user reasonably wondered if Kimi was actually wired up at all. The
rc-fallback eliminates the conditions entirely: `ask-kimi` finds the key as long as
`~/.zshrc` has the export, regardless of every other piece of state. The lesson is
broader than Kimi — any tool that depends on macOS env propagation needs an in-tool
fallback path or it will silently fail on the population of users whose process launch
order happens to be wrong.

## Applies When

Designing or reviewing any tool that reads a credential from `os.environ` and runs on
macOS; writing any installer that depends on `launchctl setenv` for its working state;
debugging "the tool works in my terminal but not when called from a GUI app" reports;
proposing a LaunchAgent / launchd plist as the answer to an env-inheritance bug (it
isn't, by itself).
