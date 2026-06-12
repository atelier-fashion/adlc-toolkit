# Delegation CLIs (provider-agnostic)

Small command-line tools that let a Claude Code session delegate token-heavy
I/O work — bulk file reading, boilerplate generation, documentation diffs — to a
configured *delegate* model behind any OpenAI-compatible chat-completions
endpoint. The point is to keep Claude's context window focused on reasoning
while a cheap model does the mechanical reading and writing. Introduced by
REQ-412; made provider-agnostic by REQ-515.

The shipped defaults point at [Kimi K2.5](https://platform.moonshot.ai/)
(Moonshot AI), so an existing setup keeps working with zero changes. A new
adopter can point the same tools at any OpenAI-compatible provider (Ollama,
Groq, DeepSeek, an Anthropic OpenAI-compat key, etc.) via a config file or env
vars — see [Configuration](#configuration).

Commands:

- `adlc-read` — read one or more files and answer a question about them, returning a summary. (Legacy name: `ask-kimi`.)
- `adlc-write` — generate boilerplate (tests, config, docstrings, repetitive patterns) to a target file. (Legacy name: `kimi-write`.)
- `extract-chat` — flatten a Claude Code session `.jsonl` transcript into plain text (feeds `adlc-read`).

The legacy `ask-kimi` / `kimi-write` names remain installed as shims for the two
commands above — existing scripts and muscle memory keep working.

> **Privacy & data governance:** `adlc-read` and `adlc-write` send file contents
> to the configured third-party endpoint. **Whether that transmission is
> permitted is the adopter's responsibility** — confirm your company's
> data-handling policy before enabling delegation. Only the basename of each
> path is included in the request — full filesystem paths stay local. Every real
> run prints a one-line stderr notice; silence it with `--no-warn` or
> `ADLC_DELEGATE_NO_WARN=1`. `extract-chat` is purely local and makes no API calls.

## Configuration

A "provider" is three values: a **base URL**, a **model name**, and the **name
of an env var** holding the API key (the key value itself is never stored in any
file). They are resolved by the following precedence (highest first):

| Precedence | Source | Keys |
|-----------:|--------|------|
| 1 | CLI flags | `--model`, `--base-url` |
| 2 | `ADLC_DELEGATE_*` env | `ADLC_DELEGATE_MODEL`, `ADLC_DELEGATE_BASE_URL`, `ADLC_DELEGATE_API_KEY_ENV` |
| 3 | config file | `delegate.base_url`, `delegate.model`, `delegate.api_key_env` |
| 4 | legacy env | `KIMI_MODEL`, `MOONSHOT_API_KEY` / `KIMI_API_KEY` |
| 5 | shipped defaults | `https://api.moonshot.ai/v1`, `kimi-k2.5`, `MOONSHOT_API_KEY` |

### Opt-in (delegation is OFF by default)

On a fresh install delegation transmits nothing until you explicitly opt in.
Opt-in is satisfied by **any one** of:

- `enabled: true` under `delegate:` in the config file, OR
- `ADLC_DELEGATE_ENABLED=1` in the environment, OR
- an already-set legacy `KIMI_API_KEY` / `MOONSHOT_API_KEY` (continuity for
  today's installs — these stay enabled exactly as before).

Setting only `ADLC_DELEGATE_BASE_URL` / `_MODEL` is **not** opt-in. Force
delegation off entirely with `ADLC_DISABLE_DELEGATE=1` (or the legacy
`ADLC_DISABLE_KIMI=1`).

### Config file

Default location `~/.claude/adlc/config.yml` (override with `ADLC_CONFIG`):

```yaml
delegate:
  enabled: true                       # opt-in; absent/false => disabled
  base_url: "https://api.groq.com/openai/v1"
  model: "llama-3.3-70b-versatile"
  api_key_env: "GROQ_API_KEY"         # the NAME of an env var, never the key
```

`api_key_env` must be the **name** of an environment variable. If a key-looking
value is found there, the tools refuse with an actionable error before any
network call.

## Setup

1. **Get an API key** for your provider (the default is a Moonshot key from
   <https://platform.moonshot.ai/> → Console → API Keys).
2. **Run the installer:**
   ```bash
   bash tools/kimi/install.sh
   ```
   This creates a Python venv at `~/.claude/kimi-venv`, installs the `openai`
   client into it, writes wrapper scripts to `~/bin/` (for `adlc-read`,
   `adlc-write`, `extract-chat`, plus `ask-kimi` / `kimi-write` shims), adds
   `~/bin` to your `PATH`, appends the routing block to `~/.claude/CLAUDE.md`,
   and adds the commands to the allowlist in `~/.claude/settings.json`. It is
   idempotent — safe to re-run.
3. **Set your API key** in your shell rc (the installer does not write it):
   ```bash
   export MOONSHOT_API_KEY="sk-..."      # or your provider's key var
   ```
4. **Restart your shell** (or `source ~/.zshrc`) so `PATH` and the env var take effect.

## Usage

```bash
# Ask a question across one or more files
adlc-read --paths src/foo.py src/bar.py --question "How does foo call bar? Summarize the data flow."

# Override the provider per-invocation
adlc-read --paths notes.md --question "summarize" --model some-model --base-url https://host/v1

# Generate boilerplate to a file
adlc-write --spec "pytest tests for the parse_args function" --context src/cli.py --target tests/test_cli.py
adlc-write --spec "..." --context ref.py --target out.py --force   # overwrite an existing target

# Flatten a session transcript to plain text
extract-chat ~/.claude/projects/<proj>/<session>.jsonl -o /tmp/chat.txt

# Legacy names still work (shims for adlc-read / adlc-write)
ask-kimi --paths src/foo.py --question "..."
```

## CLAUDE.md routing block

`install.sh` appends the canonical routing block to `~/.claude/CLAUDE.md`, and
skips the append if the `kimi-delegation:start` marker is already present so
re-running is safe. The marker name is kept for back-compat with existing
installs even though the block content is now provider-neutral.

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
2. Regenerate the pin (match install.sh's hashing — it hashes the file content
   with trailing newlines collapsed to one):

   ```sh
   ROUTING_CONTENT=$(cat tools/kimi/claude-md-routing.txt)
   printf '%s\n' "$ROUTING_CONTENT" | shasum -a 256 | awk '{print $1}' > tools/kimi/claude-md-routing.txt.sha256
   ```

   (Use `sha256sum` instead of `shasum -a 256` on Linux — both produce the
   same hex digest.)
3. Commit both files in the same PR. Reviewers see the diff in both, so a
   stealth edit to the .txt without bumping the .sha256 is impossible to land.

`install.sh` recomputes the hash of the .txt at install time and refuses
to modify `~/.claude/CLAUDE.md` if the digest does not match the pinned
value. The marker-guarded append (no double-injection) is unchanged.

### Updating dependencies

Python dependencies for the venv are pinned in `tools/kimi/requirements.txt`
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
  LaunchAgent below, but `adlc-read` also has a last-resort rc-file fallback that reads the
  default Moonshot key directly from `~/.zshrc` (or `~/.bash_profile` / `~/.bashrc`) when the
  env is empty. As long as the export is in one of those files, the default-provider tools
  work regardless of how Claude Code was launched. (Custom provider key vars are expected to
  be set in the environment directly.)
- **The LaunchAgent** — `install.sh` installs `com.adlc-toolkit.kimi-setenv` that runs at
  every login and re-populates the launchctl session env from your rc. If you change the
  key in `~/.zshrc` mid-session, run `launchctl setenv MOONSHOT_API_KEY "$MOONSHOT_API_KEY"`
  once to update the current session (or log out + back in).
- **bash login shell?** `install.sh` writes the PATH entry to `~/.bash_profile` (not
  `~/.zshrc`) when your login shell is bash. If you previously hand-edited `~/.zshrc`
  and you're on bash, either copy the lines to `~/.bash_profile` or run
  `chsh -s /bin/zsh` and restart Terminal.app for the change to take effect.
- **Linux** — the venv, CLIs, gate, and telemetry all work on Linux. The macOS-only
  launchctl / LaunchAgent steps are skipped with a notice (not a failure) when `launchctl`
  is absent; set your key var in the environment the usual way.
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
