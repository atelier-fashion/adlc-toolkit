# Architecture — REQ-415 Hotfix Bundle

## Approach

Three disjoint task groups, all parallelizable, each addressing a specific set of BRs:

1. **SKILL.md edits** (BR-1 path-traversal, BR-2 redaction, BR-6 Prerequisites, BR-7
   Co-Authored-By) — four files: `analyze/SKILL.md`, `optimize/SKILL.md`, `status/SKILL.md`,
   `wrapup/SKILL.md`.
2. **install.sh updates** (BR-3 shell detection, BR-4 `launchctl setenv`, BR-10 idempotency)
   — one file: `tools/kimi/install.sh`.
3. **Repo cleanup** (BR-5 gitignore + remove tracked state files, BR-8 stray LESSON dup,
   BR-9 README troubleshooting) — four files: `.gitignore`, the three tracked
   `pipeline-state.json` files (removed), `tools/kimi/README.md`, and the stray
   `LESSON-005-...2.md` (removed).

No task overlaps another's file set. Tier 1 fires all three in parallel.

## Key Decisions (ADRs)

### ADR-1: `..`-rejection lives next to the regex, in the skill markdown
The path-traversal fix is a one-bullet addition in the BR-3 validation section of each
skill: "MUST also reject any path containing a `..` segment, in addition to the regex
match." Keeping the rejection rule in the same paragraph as the regex makes the safety
property auditable in one place.

### ADR-2: Credential redaction is a multi-pattern `sed` chain, still inline
The redaction `sed` stays inline in `wrapup/SKILL.md` (deferring the "extract to
`kimi-redact` helper" idea from REQ-415 OQ-1 to a future REQ). The chain is built as a
single `sed -E` with `|`-separated alternation across the BR-2 patterns:
```
sed -E 's/(sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}|Bearer [A-Za-z0-9._-]{20,}|[A-Z_]+_(API_KEY|TOKEN)[[:space:]]*[=:][[:space:]]*[^[:space:]]+|MOONSHOT_API_KEY[[:space:]]*[=:][[:space:]]*[^[:space:]]+)/[REDACTED]/g'
```
Pattern order doesn't matter for correctness (all are `|`-alternation), but `MOONSHOT_API_KEY`
goes last so the `[A-Z_]+_(API_KEY|TOKEN)` pattern doesn't shadow it (it actually matches
the same string but with a different group; `[REDACTED]` is the same output so it's fine).

### ADR-3: `install.sh` detects shell via `getent passwd $USER`-or-`dscl` (macOS portable)
macOS doesn't ship `getent`. The portable detection on macOS:
```sh
LOGIN_SHELL=$(dscl . -read /Users/"$USER" UserShell 2>/dev/null | awk '{print $2}')
[ -z "$LOGIN_SHELL" ] && LOGIN_SHELL="$SHELL"
case "$(basename "$LOGIN_SHELL")" in
  zsh)  RC="$HOME/.zshrc" ;;
  bash) RC="$HOME/.bash_profile" ;;
  *)    RC="" ;;  # unknown — print manual instructions, skip rc edit
esac
```
On Linux `getent` exists but the script falls back to `$SHELL` if `dscl` is absent — works
on both. ADR rationale: prefer the persisted-user-default over the in-process `$SHELL`
because the latter can be overridden inside the `bash install.sh` invocation. We want the
shell the user's *future terminals* will launch.

### ADR-4: `launchctl setenv` is opportunistic, not required
Run it when `launchctl` exists (macOS only) and `MOONSHOT_API_KEY` is set in the install
shell. Skip silently on Linux or when the var is unset. This makes GUI-launched Claude Code
inherit the key for the rest of the boot session. Persistence across reboot is deferred to
a future REQ (would need a `LaunchAgent` plist; out of scope here).

### ADR-5: `.gitignore` pattern targets `.adlc/specs/*/pipeline-state.json` specifically
Not `**/pipeline-state.json` (too broad — could mask future legitimate uses) and not the
filename alone. The `.adlc/specs/*/pipeline-state.json` shape matches exactly how
`/proceed` writes the file and nothing else.

### ADR-6: `git rm --cached` for the three stale state files
They're committed; we need to remove them from tracking without deleting from disk during
the task. `git rm --cached` does exactly this. After commit + .gitignore add, they remain
on disk in their pre-REQ-415 state (consumers can `rm` them locally if they want).

### ADR-7: Stale Co-Authored-By trailer becomes model-agnostic
Per OQ-4 recommendation: `Co-Authored-By: Claude <noreply@anthropic.com>` (no model name).
The model name drifted from 4.6 to 4.7 in two months; making it model-agnostic stops the
drift permanently.

### ADR-8: README troubleshooting section is short and points-only
A single `### Troubleshooting` subsection with two bullets: "GUI-launched Claude Code can't
see your key — run `launchctl setenv MOONSHOT_API_KEY \"$MOONSHOT_API_KEY\"` or restart
from a terminal" and "bash login shell? `install.sh` writes to `~/.bash_profile`; if you
hand-edited `~/.zshrc` before, switch to `~/.bash_profile` or run `chsh -s /bin/zsh` and
restart Terminal." Stays under 15 lines.

## Proposed addition to `.adlc/context/conventions.md`

Add one line under "What NOT to do":
> **Don't commit `pipeline-state.json`** — it's a transient per-run state file. The
> `.gitignore` pattern `.adlc/specs/*/pipeline-state.json` excludes it. Re-introducing it
> as a tracked file is a regression.

## Task Breakdown

```
TASK-024  SKILL.md edits — path-traversal regex, broader credential redaction,
          Prerequisites blocks, model-agnostic Co-Authored-By
          (analyze, optimize, status, wrapup)

TASK-025  install.sh — shell detection (zsh vs bash via dscl/getent),
          launchctl setenv for GUI-launched Claude Code inheritance,
          re-run idempotency preserved

TASK-026  Repo cleanup — .gitignore pattern, git rm --cached the 3 stale
          pipeline-state.json files, delete stray LESSON-005 dup,
          README troubleshooting subsection
```

No dependencies between the three. **Tier 1**: all three in parallel.
