---
id: LESSON-006
title: "Executable code in a markdown-only repo needs a documented tools/ carve-out; installers that mutate user config must fail loud and write atomically"
component: "adlc/toolkit"
domain: "adlc"
stack: ["python", "bash"]
concerns: ["maintainability", "security"]
tags: ["tools-dir", "install-script", "idempotency", "atomic-write", "fail-loud", "kimi"]
req: REQ-412
created: 2026-05-12
updated: 2026-05-12
---

## What Happened

REQ-412 added real Python CLI tools (`tools/kimi/`) plus an `install.sh` to the ADLC toolkit — a repo whose convention is "code is markdown, no build step." It also shipped an installer that appends a routing block to `~/.claude/CLAUDE.md` and merges allowlist entries into `~/.claude/settings.json`. The 6-agent verify pass caught: an `IndexError` waiting to happen on an empty API `choices` list, raw tracebacks instead of actionable errors on missing files, a non-atomic `settings.json` rewrite that could truncate the user's settings on a mid-write crash, and a PATH-idempotency check that double-gated on the live `$PATH` and so skipped the `~/.zshrc` append on a fresh non-login shell.

## Lesson

1. **If you must add executable code to a markdown/docs-only repo, isolate it under `tools/<name>/`, give it its own README and its own `install.sh`, and add an explicit carve-out paragraph to `conventions.md`.** Don't let it inherit (or silently violate) the repo's "no code" model — say so in writing.
2. **Installers that touch user-owned config files (`~/.zshrc`, `~/.claude/*`) must: back up first, write to a temp file then `os.replace()`/`mv` into place, and catch malformed input with an actionable message instead of aborting `set -eu` mid-run.** A partially-executed installer is worse than one that refuses to start.
3. **Idempotency keys belong in the file being edited, not in volatile process state.** Gate "append this line to the rc file" on `grep -F "$MARKER" "$rcfile"`, never on whether `$PATH` already contains the dir — the latter is true in the install shell but false in the next fresh shell.
4. **Shelling out to an external API: guard the response shape before indexing it** (`if not resp.choices: SystemExit(...)`) and turn every `FileNotFoundError`/`OSError` into a `SystemExit` with the offending path — "fail loud" means *actionable*, not *traceback*.

## Why It Matters

A corrupted `~/.claude/settings.json` or `~/.zshrc` is a bad afternoon for the user and erodes trust in toolkit installers. An undocumented `tools/` directory invites the next contributor to either "clean up" the code or scatter more of it elsewhere. Response-shape and file-IO guards are the difference between "the tool told me my model id was wrong" and "the tool printed 40 lines of Python stack trace."

## Applies When

Adding CLI tools / scripts to a repo that's otherwise markdown/config only; writing or reviewing any `install.sh` or setup script that edits files under the user's home directory; writing thin wrappers around OpenAI-compatible (or any) HTTP APIs.
