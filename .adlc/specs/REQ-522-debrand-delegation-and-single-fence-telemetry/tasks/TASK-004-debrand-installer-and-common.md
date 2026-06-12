---
id: TASK-004
title: "De-brand installer, remove CLI shims, migrate LaunchAgent, drop legacy non-key env reads"
status: complete
parent: REQ-522
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-001]
---

## Description

Finish the de-brand on the install/runtime surface (BR-2, BR-3, BR-8, ADR-5, ADR-6):
remove the `ask-kimi`/`kimi-write` shims, rename the venv + path/CLAUDE.md markers +
plist + setenv helper, make the installer MIGRATE an existing Kimi LaunchAgent (unload
old, load new) rather than leaving both, and drop the legacy `KIMI_MODEL`/`KIMI_NO_WARN`
non-key env reads in `_common.py` (key vars stay).

## Files to Create/Modify

- `install.sh` (root) — `tools/kimi/` → `tools/delegate/` in the 4 references; run
  `tools/delegate/install.sh`; de-brand the PATH/comment prose.
- `tools/delegate/install.sh` — sanity-check `tools/delegate/adlc-read`; `CLIS` keep
  `adlc-read adlc-write extract-chat`; REMOVE the `LEGACY_SHIMS="ask-kimi kimi-write"`
  block entirely (BR-3); venv `~/.claude/kimi-venv` → `~/.claude/delegate-venv` (and
  migrate: if the old venv exists, recreate under the new name or repoint — at minimum
  stop creating the kimi-named one); PATH_MARKER → `# added by adlc-toolkit delegate install.sh`;
  CLAUDE.md routing: write a `delegate-routing:start` block but on upgrade recognize the
  legacy `kimi-delegation:start` anchor too (ADR-6) so the block is replaced, not
  duplicated; settings.json permission list drops the `Bash(ask-kimi:*)`/`Bash(kimi-write:*)`
  legacy entries.
  - LaunchAgent (BR-8): `AGENT_LABEL` `com.adlc-toolkit.kimi-setenv` →
    `com.adlc-toolkit.delegate-setenv`; `AGENT_HELPER` `~/.claude/kimi-launchctl-setenv.sh`
    → `~/.claude/delegate-launchctl-setenv.sh`; `HELPER_SRC`/`PLIST_SRC` → renamed
    `.in` files. **Migration**: before loading the new agent, `launchctl bootout`
    (and `rm -f`) any existing `com.adlc-toolkit.kimi-setenv.plist` so both don't run.
- `tools/delegate/com.adlc-toolkit.kimi-setenv.plist.in` →
  `tools/delegate/com.adlc-toolkit.delegate-setenv.plist.in` — `git mv`; label inside
  → `com.adlc-toolkit.delegate-setenv`; helper path → `delegate-launchctl-setenv.sh`.
- `tools/delegate/kimi-launchctl-setenv.sh.in` →
  `tools/delegate/delegate-launchctl-setenv.sh.in` — `git mv`; de-brand the log path
  (`kimi-launchctl-setenv.log` → `delegate-launchctl-setenv.log`) and comments;
  KEEP `MOONSHOT_API_KEY` (data).
- `tools/delegate/_common.py` — remove the legacy `KIMI_MODEL` read (keep
  `ADLC_DELEGATE_MODEL`) and the legacy `KIMI_NO_WARN` read (keep `ADLC_DELEGATE_NO_WARN`);
  KEEP `KIMI_API_KEY`/`MOONSHOT_API_KEY` (key continuity) and the Moonshot/`kimi-k2.5`
  default *values* (data). De-brand surrounding comments that describe identifiers, but
  the "today's Moonshot/Kimi values" data comment may reference Kimi as provider data.
- `tools/delegate/ask-kimi`, `tools/delegate/kimi-write` — DELETE (BR-3).
- `tools/delegate/README.md` — de-brand (it documents the CLIs/shims/launchd).

## Acceptance Criteria

- [ ] `ask-kimi` / `kimi-write` files and installer shim block are gone; only
      `adlc-read`/`adlc-write`/`extract-chat` are installed.
- [ ] No `~/.claude/kimi-venv`, `kimi-launchctl-setenv.sh`, or
      `com.adlc-toolkit.kimi-setenv` is created by a fresh install.
- [ ] An upgrade install `bootout`s the old `com.adlc-toolkit.kimi-setenv` agent and
      loads `com.adlc-toolkit.delegate-setenv` (no duplicate agents).
- [ ] `_common.py` no longer reads `KIMI_MODEL`/`KIMI_NO_WARN`; still reads the key vars
      and resolves the Moonshot defaults.
- [ ] `ADLC_DISABLE_KIMI` is not an accepted disable flag anywhere in the installer.
- [ ] `plutil -lint` passes on the generated delegate plist.

## Technical Notes

- The plist `Label` and the filename must both change (BR-8) — a plist whose filename
  and Label disagree fails to load cleanly.
- Validate-before-mutate (LESSON-017): `plutil -lint` the new plist before
  `launchctl bootstrap`, exactly as the existing code does.
- POSIX/zsh/BSD-safe (BR-7).
