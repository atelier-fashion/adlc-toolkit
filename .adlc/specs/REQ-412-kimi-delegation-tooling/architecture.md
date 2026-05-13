# Architecture — REQ-412 Kimi K2.5 Delegation Tooling

## Approach

Three small Python CLI tools that Claude Code invokes via its Bash tool to offload I/O-heavy
work to Kimi K2.5 (Moonshot, OpenAI-compatible API). The tools, a shared helper module, and the
`~/.claude/CLAUDE.md` routing block are **version-controlled in `adlc-toolkit`** under a new
`tools/kimi/` directory, with an `install.sh` that provisions the venv and symlinks the scripts
onto the user's PATH. This keeps the machine reproducible after a re-setup while respecting that
the actual runtime artifacts (venv, `~/bin` symlinks, `~/.zshrc` export, `~/.claude/settings.json`
allowlist) live outside the repo.

```
adlc-toolkit/
└── tools/kimi/
    ├── _common.py        # client factory, key-check, empty-completion guard, corpus packing
    ├── ask-kimi          # CLI: bulk file reader
    ├── kimi-write        # CLI: boilerplate generator
    ├── extract-chat      # CLI: Claude Code JSONL transcript cleaner
    ├── install.sh        # creates ~/.claude/kimi-venv, pip install openai, symlinks to ~/bin
    └── README.md         # setup + the canonical CLAUDE.md routing block to paste/append
```

Runtime layout (created by `install.sh`, not in repo):
- Venv: `~/.claude/kimi-venv/` with `openai` installed
- Scripts: `~/bin/ask-kimi`, `~/bin/kimi-write`, `~/bin/extract-chat` → symlinks into `tools/kimi/`
- Each script's shebang: `#!/Users/<user>/.claude/kimi-venv/bin/python3` — written by `install.sh`
  from a `.in` template OR (simpler) the scripts use `#!/usr/bin/env python3` and `install.sh`
  prepends the venv `bin` to a wrapper. **Decision: scripts ship with a placeholder shebang
  `#!/usr/bin/env python3`; `install.sh` generates real launcher symlinks via small wrapper
  scripts in `~/bin` that exec the venv interpreter.** (Avoids committing a machine-specific path.)
- `~/.zshrc`: append `export MOONSHOT_API_KEY="..."` (value supplied by the user) and ensure
  `~/bin` is on PATH (`export PATH="$HOME/bin:$PATH"`)
- `~/.claude/CLAUDE.md`: created/appended with the delegation routing block
- `~/.claude/settings.json`: allowlist entries for the three commands

## Open Questions — resolved

| OQ | Resolution |
|----|-----------|
| OQ-1 paths | Scripts symlinked into `~/bin` (PATH entry added by `install.sh` if missing). Venv at `~/.claude/kimi-venv/`. |
| OQ-2 key storage | `~/.zshrc` export `MOONSHOT_API_KEY`. Keychain deferred (could be a future enhancement). |
| OQ-3 version control | Yes — scripts + `_common.py` + `install.sh` + routing block live in `adlc-toolkit/tools/kimi/`. |
| OQ-4 model id | Configurable via env `KIMI_MODEL`, default `kimi-k2.5` (a per-tool `--model` flag overrides). Real id confirmed against Moonshot docs during implementation. |
| OQ-5 kimi-write clobber | `kimi-write` refuses to overwrite an existing `--target` unless `--force` is passed. |

## Key Decisions (ADRs)

### ADR-1: Ship runtime code in `adlc-toolkit` despite the "code is markdown" convention
The toolkit conventions say it's markdown-only with no build step. These three CLI tools are real
Python. **Rationale**: the alternative (a separate repo, or purely-local untracked scripts) is
worse — a new repo is maintenance overhead for ~200 lines; untracked local scripts don't survive
machine re-setup and can't be reviewed. `tools/kimi/` is a clearly-bounded exception, isolated
under one directory, with its own README. The toolkit's symlink-install model doesn't apply to it
(it has its own `install.sh`). Convention doc gets a one-line carve-out note.

### ADR-2: Shared `_common.py` helper, not three copies of boilerplate
Client construction (`base_url`, key check), the `max_tokens` empty-completion guard, and corpus
packing (files-first ordering for prefix-cache hits) are identical across all three tools.
Centralize in `_common.py`; the three CLI scripts are thin argument-parsing + I/O wrappers.

### ADR-3: Hard "When NOT to delegate" list lives in `~/.claude/CLAUDE.md`, canonical copy in repo
The routing rules must be global (every project). `install.sh` appends them to `~/.claude/CLAUDE.md`
if not already present (idempotent via a marker comment `<!-- kimi-delegation:start -->` /
`<!-- kimi-delegation:end -->`). The canonical text lives in `tools/kimi/README.md` so it's
reviewable and re-installable.

### ADR-4: Fail loud, never silent
Per spec BR-3/BR-4: missing `MOONSHOT_API_KEY` → non-zero exit with the var name; an empty
completion (Kimi spent all `max_tokens` on reasoning) → non-zero exit with an "empty completion,
raise --max-tokens" diagnostic. No tool prints partial/empty output and exits 0.

## "Testing" in this repo

No test runner (per conventions — toolkit is markdown, and now a tiny bit of Python with no CI).
Validation is manual dogfooding, captured as acceptance-criteria checks in the tasks:
- Smoke-test each CLI against real files with a live `MOONSHOT_API_KEY`
- Verify failure modes (unset key, tiny `--max-tokens`, existing target without `--force`)
- Verify `install.sh` is idempotent (re-run produces no duplicate PATH/CLAUDE.md entries)
- Verify a real Claude Code session self-routes to `ask-kimi` from the CLAUDE.md rules alone

A follow-up REQ may add a minimal `pytest` smoke suite under `tools/kimi/tests/` if the surface grows.

## Proposed addition to `.adlc/context/conventions.md`

Add under "Code is markdown, not code":
> **Exception — `tools/`**: the `tools/` directory may contain real executable code (e.g.
> `tools/kimi/` Python CLIs) with its own `install.sh`. It is exempt from the markdown-only rule
> and from the symlink-install model. Each subdirectory carries its own README.

## Task Breakdown

```
TASK-013 (venv + install.sh + _common.py)   ── foundational
   ├── TASK-014 (ask-kimi)        depends: 013
   ├── TASK-015 (kimi-write)      depends: 013
   └── TASK-016 (extract-chat)    depends: 013
            └── TASK-017 (CLAUDE.md routing block + settings.json allowlist + README + conventions note)
                                  depends: 014, 015, 016
```

Tier 1: TASK-013
Tier 2: TASK-014, TASK-015, TASK-016 (parallel)
Tier 3: TASK-017
