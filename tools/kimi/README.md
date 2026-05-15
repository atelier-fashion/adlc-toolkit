# Kimi K2.5 Delegation CLIs

Small command-line tools that let a Claude Code session delegate token-heavy
I/O work — bulk file reading, boilerplate generation, documentation diffs — to
[Kimi K2.5](https://platform.moonshot.ai/) (Moonshot AI). The point is to keep
Claude's context window focused on reasoning while a cheap model does the
mechanical reading and writing. Introduced by REQ-412.

Three commands:

- `ask-kimi` — read one or more files and answer a question about them, returning a summary.
- `kimi-write` — generate boilerplate (tests, config, docstrings, repetitive patterns) to a target file.
- `extract-chat` — flatten a Claude Code session `.jsonl` transcript into plain text (feeds `ask-kimi`).

> **Privacy:** `ask-kimi` and `kimi-write` send file contents to the Moonshot
> API. Only the basename of each path is included in the request — full
> filesystem paths stay local. Every real run prints a one-line stderr notice;
> silence it with `--no-warn` or `KIMI_NO_WARN=1`. `extract-chat` is purely
> local and makes no API calls.

## Setup

1. **Get a Moonshot API key** from <https://platform.moonshot.ai/> (Console → API Keys).
2. **Run the installer:**
   ```bash
   bash tools/kimi/install.sh
   ```
   This creates a Python venv at `~/.claude/kimi-venv`, installs the `openai`
   client into it, writes wrapper scripts to `~/bin/`, adds `~/bin` to your
   `PATH` in `~/.zshrc`, appends the routing block below to `~/.claude/CLAUDE.md`,
   and adds the three commands to the allowlist in `~/.claude/settings.json`.
   It is idempotent — safe to re-run.
3. **Add your API key to `~/.zshrc`:**
   ```bash
   export MOONSHOT_API_KEY="sk-..."
   ```
   (the installer does not write this for you).
4. **Restart your shell** (or `source ~/.zshrc`) so `PATH` and the env var take effect.

## Usage

```bash
# Ask a question across one or more files
ask-kimi --paths src/foo.py src/bar.py --question "How does foo call bar? Summarize the data flow."

# Generate boilerplate to a file
kimi-write --spec "pytest tests for the parse_args function" --context src/cli.py --target tests/test_cli.py
kimi-write --spec "..." --context ref.py --target out.py --force   # overwrite an existing target

# Flatten a session transcript to plain text
extract-chat ~/.claude/projects/<proj>/<session>.jsonl -o /tmp/chat.txt
```

## CLAUDE.md routing block

`install.sh` appends the canonical Kimi routing block to `~/.claude/CLAUDE.md`,
and skips the append if the `kimi-delegation:start` marker is already present
so re-running is safe.

<!-- Canonical routing block lives at claude-md-routing.txt — hash-pinned at claude-md-routing.txt.sha256 -->

The block content (including its `<!-- kimi-delegation:start -->` /
`<!-- kimi-delegation:end -->` HTML-comment markers) is the verbatim contents
of [`claude-md-routing.txt`](claude-md-routing.txt). To preview what gets
appended, `cat` that file.

### Updating the Claude routing block

The routing block is hash-pinned (REQ-426 BR-1 / ADR-1) so a casual edit
to the canonical file cannot silently change every developer's
`~/.claude/CLAUDE.md` on the next `install.sh` run. Workflow:

1. Edit `tools/kimi/claude-md-routing.txt` with the new content.
2. Regenerate the pin:

   ```sh
   shasum -a 256 tools/kimi/claude-md-routing.txt | awk '{print $1}' > tools/kimi/claude-md-routing.txt.sha256
   ```

   (Use `sha256sum` instead of `shasum -a 256` on Linux — both produce the
   same hex digest.)
3. Commit both files in the same PR. Reviewers see the diff in both, so a
   stealth edit to the .txt without bumping the .sha256 is impossible to land.

`install.sh` recomputes the hash of the .txt at install time and refuses
to modify `~/.claude/CLAUDE.md` if the digest does not match the pinned
value. The marker-guarded append (no double-injection) is unchanged.

### Updating dependencies

Python dependencies for the Kimi venv are pinned in `tools/kimi/requirements.txt`
with exact `==` versions for reproducibility (REQ-416 BR-6/BR-7). `install.sh`
installs strictly from that file — there is no `--upgrade` flag, so re-running
the installer will not silently pull a newer `openai` SDK that breaks the CLIs.

To bump a pinned version:

1. Open a hotfix REQ (the pinned API surface is part of the toolkit contract —
   a bump that changes call shapes is a real change worth tracking).
2. Edit `tools/kimi/requirements.txt` to the new pin.
3. Delete `~/.claude/kimi-venv` and re-run `bash tools/kimi/install.sh` on a
   clean state to verify the new pin installs cleanly.
4. Run the `tools/kimi/tests/` pytest suite against the new venv.
5. Land the bump with the rest of the hotfix.

### Troubleshooting

- **GUI-launched Claude Code can't see `MOONSHOT_API_KEY`** — usually self-heals via the
  LaunchAgent below, but `ask-kimi` also has a last-resort rc-file fallback that reads the
  key directly from `~/.zshrc` (or `~/.bash_profile` / `~/.bashrc`) when the env is empty.
  As long as the export is in one of those files, `ask-kimi` works regardless of how
  Claude Code was launched.
- **The LaunchAgent** — `install.sh` installs `com.adlc-toolkit.kimi-setenv` that runs at
  every login and re-populates the launchctl session env from your rc. If you change the
  key in `~/.zshrc` mid-session, run `launchctl setenv MOONSHOT_API_KEY "$MOONSHOT_API_KEY"`
  once to update the current session (or log out + back in).
- **bash login shell?** `install.sh` writes the PATH entry to `~/.bash_profile` (not
  `~/.zshrc`) when your login shell is bash. If you previously hand-edited `~/.zshrc`
  and you're on bash, either copy the lines to `~/.bash_profile` or run
  `chsh -s /bin/zsh` and restart Terminal.app for the change to take effect.
- **Inspect the LaunchAgent** — `launchctl list | grep adlc-toolkit` confirms it's
  loaded; `cat ~/Library/Logs/kimi-launchctl-setenv.log` shows what it did at the last
  login (path checked, key length — never the key value itself).
- **`.in` files** — `tools/kimi/*.in` are install-time templates. `install.sh` copies and
  substitutes (`__HOME__` → your `$HOME`) into the deployed locations. Do not run them in
  place; edit the `.in` source and re-run `install.sh`.
- **Security trade-off (deliberate)** — once the launchctl session env has the key, ANY
  GUI app the user launches can read it via `launchctl getenv` or its own process env.
  This is the cost of making GUI-launched Claude Code see the key. A compromised
  user-space process can already read `~/.zshrc`; this widens that exposure modestly.
