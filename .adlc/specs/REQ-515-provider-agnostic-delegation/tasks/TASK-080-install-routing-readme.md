---
id: TASK-080
title: "install.sh shims/allowlist + provider-neutral routing.txt + README"
status: draft
parent: REQ-515
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-078]
---

## Description

Update the installer to install the new CLIs plus back-compat shims, neutralize
user-facing prose, and rewrite the CLAUDE.md routing block and README
provider-neutral (BR-1, BR-7, BR-8). Add the data-governance disclosure (BR-11).

## Files to Create/Modify

- `tools/kimi/install.sh` — `CLIS="adlc-read adlc-write extract-chat"`; ALSO write
  `~/bin` shim wrappers for `ask-kimi`/`kimi-write`; allowlist merges BOTH new and
  old `Bash(...)` entries; neutralize reminder/printed text; keep the
  hash-validated routing append + TOCTOU/atomicity guards intact.
- `tools/kimi/claude-md-routing.txt` — rewrite provider-neutral ("Claude =
  thinking, the delegate = I/O"), parameterized tool names, config-file mention,
  third-party-transmission + company-approval disclosure (BR-11).
- `tools/kimi/claude-md-routing.txt.sha256` — regenerate to match.
- `tools/kimi/README.md` — provider-neutral rewrite with a config-file section,
  precedence table, opt-in/disable explanation, and the data-governance notice.

## Acceptance Criteria

- [ ] `install.sh` installs `adlc-read`/`adlc-write`/`extract-chat` AND
      `ask-kimi`/`kimi-write` shims; all on PATH after install.
- [ ] settings.json allowlist contains both new and legacy `Bash(...)` entries.
- [ ] Routing block is provider-neutral, parameterized, and states delegation
      transmits source content to the configured third-party endpoint and that
      company approval is the adopter's responsibility (BR-11).
- [ ] `.sha256` matches the rewritten routing text (installer hash check passes).
- [ ] Installer stays fail-loud/atomic (backup, temp-write, `os.replace`); all new
      shell BSD/zsh-safe; launchctl steps skip-with-notice on Linux, not fail (BR-8).
- [ ] README documents config location (`~/.claude/adlc/config.yml`, `ADLC_CONFIG`
      override), precedence (BR-2), opt-in (BR-11), key-never-in-file (BR-3).

## Technical Notes

- The routing block keeps the `kimi-delegation:start/end` markers for back-compat
  idempotency (install.sh greps `kimi-delegation:start`) — do NOT rename the
  marker or existing installs would double-append.
- Regenerate sha: `shasum -a 256 claude-md-routing.txt` — but note install.sh
  hashes `printf '%s\n' "$content"`; match that exact form when regenerating.
- launchctl/LaunchAgent blocks already guard with `command -v launchctl` — leave
  the macOS-only persistence intact; only neutralize comments/printed strings,
  keeping the `MOONSHOT_API_KEY` env handling for the legacy default key var.
