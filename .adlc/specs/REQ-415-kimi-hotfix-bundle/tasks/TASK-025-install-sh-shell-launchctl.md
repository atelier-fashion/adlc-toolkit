---
id: TASK-025
title: "install.sh: detect login shell (zsh/bash), write to correct rc, run launchctl setenv for GUI inheritance"
status: complete
parent: REQ-415
created: 2026-05-13
updated: 2026-05-13
dependencies: []
---

## Description

Modify `tools/kimi/install.sh` so that:

1. **Login-shell detection** — uses `dscl . -read /Users/$USER UserShell` on macOS (with
   `$SHELL` as a fallback) to determine where to write the PATH marker. The current
   hardcoded `ZSHRC="$HOME/.zshrc"` becomes a derived `RC=` whose value is:
   - `~/.zshrc` when the login shell is zsh
   - `~/.bash_profile` when the login shell is bash
   - empty (with a printed manual-instruction message) for any other shell
2. **`launchctl setenv` step** — after the PATH section, on macOS only, when
   `MOONSHOT_API_KEY` is set in the install shell, run `launchctl setenv MOONSHOT_API_KEY
   "$MOONSHOT_API_KEY"` so GUI-launched Claude Code inherits the var for this boot session.
   Print one line describing the action (without echoing the value). Skip silently when
   `launchctl` is absent (Linux) or the key is unset.
3. **Idempotency preserved** — re-running the installer should still produce zero
   duplicates in the chosen rc file, zero error from `launchctl setenv` (it's natively
   idempotent), and zero changes to `~/.claude/CLAUDE.md` / `~/.claude/settings.json`
   beyond the existing REQ-412/414 behavior.

## Files to Create/Modify

- `tools/kimi/install.sh` — replace the PATH-section block (currently the `ZSHRC=...`
  hardcode + the marker-guarded `~/.zshrc` append) with a shell-detection block that picks
  the right rc file. Add a new section (after the PATH section, before the next-steps echo)
  for `launchctl setenv`. Update the existing non-zsh warning echo to reflect the new
  multi-shell behavior.

## Acceptance Criteria

- [ ] `bash -n tools/kimi/install.sh` passes.
- [ ] When run on a machine whose login shell is bash, the script writes the PATH marker
      to `~/.bash_profile` and NOT to `~/.zshrc` (verified by `grep -F 'adlc-toolkit kimi
      install.sh' ~/.bash_profile` after run, and the inverse on `~/.zshrc` — assuming the
      file existed empty before).
- [ ] When run on a machine whose login shell is zsh, behavior is unchanged from the
      REQ-414 baseline — PATH marker goes to `~/.zshrc` exactly once.
- [ ] When run on a machine with an unknown login shell (e.g., fish), no rc file is
      touched; a clear `echo` prints which lines the user should add manually.
- [ ] On macOS with `MOONSHOT_API_KEY` set in the install shell, `launchctl setenv
      MOONSHOT_API_KEY "$MOONSHOT_API_KEY"` runs (verified by `launchctl getenv
      MOONSHOT_API_KEY` returning the value after the install).
- [ ] On macOS with `MOONSHOT_API_KEY` UNSET in the install shell, the `launchctl setenv`
      step is skipped (and an `echo` notes the skip).
- [ ] On a non-macOS host (no `launchctl`), the entire `launchctl` step is skipped silently
      — no error, no spurious message.
- [ ] Re-running `install.sh` twice on the same machine produces no duplicate marker line
      in the chosen rc file, and `launchctl getenv MOONSHOT_API_KEY` continues to return
      the value on the second run.
- [ ] The REQ-414 idempotency for `~/.claude/CLAUDE.md` and `~/.claude/settings.json` is
      preserved — no duplicates introduced.

## Technical Notes

- macOS shell detection (preferred):
  ```sh
  LOGIN_SHELL=$(dscl . -read /Users/"$USER" UserShell 2>/dev/null | awk '{print $2}')
  [ -z "$LOGIN_SHELL" ] && LOGIN_SHELL="$SHELL"
  case "$(basename "$LOGIN_SHELL")" in
    zsh)  RC="$HOME/.zshrc" ;;
    bash) RC="$HOME/.bash_profile" ;;
    *)    RC="" ;;
  esac
  ```
- `launchctl setenv` step:
  ```sh
  if command -v launchctl >/dev/null 2>&1; then
    if [ -n "${MOONSHOT_API_KEY:-}" ]; then
      launchctl setenv MOONSHOT_API_KEY "$MOONSHOT_API_KEY"
      echo "Exported MOONSHOT_API_KEY into launchctl session env (until reboot)"
    else
      echo "Skipping launchctl setenv: MOONSHOT_API_KEY not set in install shell"
    fi
  fi
  ```
- Wrap the rc-append block in `[ -n "$RC" ]` so unknown-shell users skip cleanly.
- Do NOT touch the CLAUDE.md routing block section, the settings.json merge section, or
  any other part of install.sh beyond the PATH detection + new launchctl step.
- BSD/macOS shell only — no GNU-isms.
