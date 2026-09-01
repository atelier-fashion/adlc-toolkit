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

- `adlc-read` — read one or more files and answer a question about them, returning a summary.
- `adlc-write` — generate boilerplate (tests, config, docstrings, repetitive patterns) to a target file.
- `extract-chat` — flatten a Claude Code session `.jsonl` transcript into plain text (feeds `adlc-read`).

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
| 4 | legacy key-env continuity | `MOONSHOT_API_KEY` / `KIMI_API_KEY` |
| 5 | shipped defaults | `https://api.moonshot.ai/v1`, `kimi-k2.6`, `MOONSHOT_API_KEY` |

The `enabled` flag follows this same order — rank 2 (`ADLC_DELEGATE_ENABLED`)
outranks rank 3 (the config file), which outranks rank 4 (a legacy key). It did
not before BUG-205, when a legacy key silently outranked the config file and an
explicit `enabled: false` never took effect.

### Opt-in (delegation is OFF by default)

On a fresh install delegation transmits nothing until you explicitly opt in.
Opt-in is satisfied by **any one** of:

- `ADLC_DELEGATE_ENABLED=1` in the environment, OR
- `enabled: true` under `delegate:` in the config file, OR
- an already-set legacy `KIMI_API_KEY` / `MOONSHOT_API_KEY` — key continuity for
  pre-config installs, **unless the config file says `enabled: false`**, which
  overrides it.

Setting only `ADLC_DELEGATE_BASE_URL` / `_MODEL` is **not** opt-in.

### The CLIs enforce this themselves

`adlc-read` and `adlc-write` refuse to transmit unless delegation is opted in, and
exit non-zero with an actionable message. This is deliberate redundancy with the
shell gate: the gate is **vendored per repo** (`.adlc/partials/delegate-gate.sh`,
sourced ahead of the toolkit copy), so a repo carrying a stale copy could otherwise
call straight through a correct opt-out. A control that lives only in the layer that
gets copied around is not a control (BUG-206).

The refusal fires before any provider resolution or network touch. `--dry-run`,
`--print-enabled`, and `--version` still work while delegation is off — a dry run
sends nothing, and the probes are how you diagnose a disabled setup.

Delegating skills already treat a non-zero exit as "fall back and read directly", so
a refusal degrades exactly like a missing binary.

### Turning delegation off

Writing `enabled: false` under `delegate:` turns delegation off, and outranks
any legacy key in the environment. `ADLC_DISABLE_DELEGATE=1` forces it off from
the environment, overriding everything including `ADLC_DELEGATE_ENABLED=1`.

An **absent** `enabled` key is not the same as `enabled: false`. Absence is a
default and yields to the key-continuity rule above; a written `false` is an
instruction and does not. Before BUG-205 the two were collapsed, so an exported
`MOONSHOT_API_KEY` re-enabled delegation on a machine whose config said `false`
— and since `install.sh` scaffolds a config containing exactly that line, that
was the default posture of any install with a key in the environment.

If you rely on a legacy key to opt in and your config carries the scaffolded
`enabled: false`, delegation is now **off**. Set `enabled: true` (or export
`ADLC_DELEGATE_ENABLED=1`) to turn it back on. Check which way a machine will
resolve with:

```
adlc-read --version      # prints the resolved `enabled:` value
```

### Config file

Default location `~/.claude/adlc/config.yml` (override with `ADLC_CONFIG`):

```yaml
delegate:
  enabled: true                       # true => opt in; false => opt OUT, and
                                      # outranks a legacy key. Absent => defer
                                      # to the key-continuity rule.
  base_url: "https://api.groq.com/openai/v1"
  model: "llama-3.3-70b-versatile"
  api_key_env: "GROQ_API_KEY"         # the NAME of an env var, never the key
```

`api_key_env` must be the **name** of an environment variable, in
`UPPER_SNAKE_CASE`. The value the whole cascade resolves to is validated —
including an `ADLC_DELEGATE_API_KEY_ENV` override, which outranks the file — so
a key pasted into either place is refused with an actionable error before any
network call. The refusal never echoes the offending value.

## Setup

1. **Get an API key** for your provider (the default is a Moonshot key from
   <https://platform.moonshot.ai/> → Console → API Keys).
2. **Run the installer:**
   ```bash
   bash tools/delegate/install.sh
   ```
   This creates a Python venv at `~/.claude/delegate-venv`, installs the `openai`
   client into it, writes wrapper scripts to `~/bin/` (for `adlc-read`,
   `adlc-write`, `extract-chat`), adds
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
```

### Version & resolved provider (`--version`)

All three CLIs accept `--version` (or `-V`). It is scanned out of the arguments
*before* parsing, so it needs no other arguments (`adlc-write --version` works
without `--spec`/`--target`), and it runs before every guard — no network call,
no API key, no config file, and no `openai` SDK required. The scan is
value-aware: it only matches `--version`/`-V` in *flag* position, so
`adlc-read --question -V` asks about the string `-V` (and gets argparse's own
error) rather than silently printing the version, and it stops at `--`.

`adlc-read` and `adlc-write` also print the provider a **real call would
resolve**, through the same resolver and the same precedence table as above — so
it answers "which endpoint is this install actually talking to?" without reading
the config file, the environment, and `_common.py` by hand. That includes
rank 1: `--model` / `--base-url` passed alongside `--version` are reflected in
the output, in both the `--model VALUE` and `--model=VALUE` forms. The API key
**value** is never read or printed; only the *name* of the env var holding it:

```bash
$ adlc-read --version
adlc-toolkit <version>
base_url: https://api.groq.com/openai/v1
model: llama-3.3-70b-versatile
api_key_env: GROQ_API_KEY
enabled: true
```

`extract-chat` has no provider config, so it prints the version line only:

```bash
$ extract-chat --version
adlc-toolkit <version>
```

The output is a stable, machine-parseable contract (exit 0, stdout): the first
line is always `adlc-toolkit <version>` — the first line of the repo `VERSION`
file, resolved from the script's own location, so it reports the toolkit's
version and not anything derived from the directory you ran it in (nor, when the
toolkit is vendored inside another git repo, that host repo's version) —
followed by exactly the `base_url`, `model`, `api_key_env`, and `enabled`
(`true`/`false`) lines.

If the printed `base_url` carries credentials (`https://user:pass@host/v1`), the
userinfo is redacted to `***@host` **on the print path only** — the real call
still receives the URL intact.

If provider resolution is **refused** — the resolved `api_key_env` is a key
value rather than an `UPPER_SNAKE_CASE` env var name, whether it came from the
config file or from `ADLC_DELEGATE_API_KEY_ENV` — `--version` never crashes with
a traceback. It prints the version line plus a single diagnostic line in place
of the config block, and still exits 0. The refused value is never echoed back:

```bash
$ adlc-read --version
adlc-toolkit <version>
config_error: config 'delegate.api_key_env' must be the NAME of an environment variable (e.g. MY_PROVIDER_KEY), not a key value. ...
```

A config file that simply cannot be *parsed* is a different case: the minimal
reader yields no `delegate:` keys, resolution falls through to the shipped
defaults, and `--version` reports those with no `config_error:` line — matching
what a real call would resolve. `config_error:` means refused, not "unreadable".

## CLAUDE.md routing block

`install.sh` appends the canonical routing block to `~/.claude/CLAUDE.md`, and
skips the append if the `delegate-routing:start` marker (or the legacy
`kimi-delegation:start` marker from a pre-REQ-522 install) is already present so
re-running is safe.

<!-- Canonical routing block lives at claude-md-routing.txt — hash-pinned at claude-md-routing.txt.sha256 -->

The block content (including its `<!-- delegate-routing:start -->` /
`<!-- delegate-routing:end -->` HTML-comment markers) is the verbatim contents
of [`claude-md-routing.txt`](claude-md-routing.txt). To preview what gets
appended, `cat` that file.

### Updating the Claude routing block

The routing block is hash-pinned (REQ-426 BR-1 / ADR-1) so a casual edit
to the canonical file cannot silently change every developer's
`~/.claude/CLAUDE.md` on the next `install.sh` run. Workflow:

1. Edit `tools/delegate/claude-md-routing.txt` with the new content.
2. Regenerate the pin (match install.sh's hashing — it hashes the file content
   with trailing newlines collapsed to one):

   ```sh
   ROUTING_CONTENT=$(cat tools/delegate/claude-md-routing.txt)
   printf '%s\n' "$ROUTING_CONTENT" | shasum -a 256 | awk '{print $1}' > tools/delegate/claude-md-routing.txt.sha256
   ```

   (Use `sha256sum` instead of `shasum -a 256` on Linux — both produce the
   same hex digest.)
3. Commit both files in the same PR. Reviewers see the diff in both, so a
   stealth edit to the .txt without bumping the .sha256 is impossible to land.

`install.sh` recomputes the hash of the .txt at install time and refuses
to modify `~/.claude/CLAUDE.md` if the digest does not match the pinned
value. The marker-guarded append (no double-injection) is unchanged.

### Updating dependencies

Python dependencies for the venv are pinned in `tools/delegate/requirements.txt`
with exact `==` versions for reproducibility (REQ-416 BR-6/BR-7). `install.sh`
installs strictly from that file — there is no `--upgrade` flag, so re-running
the installer will not silently pull a newer `openai` SDK that breaks the CLIs.

To bump a pinned version:

1. Open a hotfix REQ (the pinned API surface is part of the toolkit contract —
   a bump that changes call shapes is a real change worth tracking).
2. Edit `tools/delegate/requirements.txt` to the new pin.
3. Delete `~/.claude/delegate-venv` and re-run `bash tools/delegate/install.sh` on a
   clean state to verify the new pin installs cleanly.
4. Run the `tools/delegate/tests/` pytest suite against the new venv.
5. Land the bump with the rest of the hotfix.

### Troubleshooting

- **GUI-launched Claude Code can't see `MOONSHOT_API_KEY`** — usually self-heals via the
  LaunchAgent below, but `adlc-read` also has a last-resort rc-file fallback that reads the
  default Moonshot key directly from `~/.zshrc` (or `~/.bash_profile` / `~/.bashrc`) when the
  env is empty. As long as the export is in one of those files, the default-provider tools
  work regardless of how Claude Code was launched. (Custom provider key vars are expected to
  be set in the environment directly.)
- **The LaunchAgent** — `install.sh` installs `com.adlc-toolkit.delegate-setenv` that runs at
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
  loaded; `cat ~/Library/Logs/delegate-launchctl-setenv.log` shows what it did at the last
  login (path checked, key length — never the key value itself).
- **`.in` files** — `tools/delegate/*.in` are install-time templates. `install.sh` copies and
  substitutes (`__HOME__` → your `$HOME`) into the deployed locations. Do not run them in
  place; edit the `.in` source and re-run `install.sh`.
- **Security trade-off (deliberate)** — once the launchctl session env has the key, ANY
  GUI app the user launches can read it via `launchctl getenv` or its own process env.
  This is the cost of making GUI-launched Claude Code see the key. A compromised
  user-space process can already read `~/.zshrc`; this widens that exposure modestly.
