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

`install.sh` appends everything between the two `kimi-delegation` HTML-comment
markers below to `~/.claude/CLAUDE.md`, and skips the append if those markers
are already present so re-running is safe. To preview what gets appended, run
the marker-range `sed` extraction over this file.

<!-- kimi-delegation:start -->
## Kimi K2.5 Delegation Tools (token saving)

You have three CLIs for offloading token-heavy I/O to Kimi K2.5. Use them to
keep your context window focused on reasoning. The rules below are mandatory.

### ask-kimi — bulk reading

Use when you'd otherwise read a file longer than ~400 lines, or when answering
one question would require reading 3+ files. Usage:

```
ask-kimi --paths <f1> <f2> ... --question "<q>"
```

Use the returned summary instead of reading the files yourself.

### kimi-write — boilerplate generation

Use for tests, config scaffolding, docstrings, and other repetitive patterns.
Usage:

```
kimi-write --spec "<what to generate>" --context <reference file> --target <output file>
```

Then review the generated file and edit only what needs fixing. Add `--force`
to overwrite an existing target.

### Documentation workflow

To update docs after a working session, don't re-read the conversation and
rewrite the docs by hand. Instead:

```
extract-chat ~/.claude/projects/<proj>/<session>.jsonl -o /tmp/chat.txt
ask-kimi --paths /tmp/chat.txt <doc>.md --question "What doc updates are needed? Give exact edits."
```

Then apply the returned edits. Prefer this over re-reading the conversation and
rewriting docs directly.

### When NOT to delegate

Do **not** route to Kimi for:

- Tasks under ~2000 tokens — the delegation round-trip costs more than it saves.
- Architectural decisions.
- Debugging.
- Safety- and security-critical code.
- Anything that requires exact line numbers for editing.

**Claude = thinking. Kimi = I/O.**
<!-- kimi-delegation:end -->
