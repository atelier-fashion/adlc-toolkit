---
id: REQ-412
title: "Kimi K2.5 Delegation Tooling for Token-Efficient Claude Code Sessions"
status: complete
deployable: false
created: 2026-05-12
updated: 2026-05-12
component: "env/tooling"
domain: "developer-experience"
stack: ["python", "bash", "markdown", "openai-sdk"]
concerns: ["cost", "performance"]
tags: ["kimi", "delegation", "token-budget", "cli-tools", "claude-md", "moonshot"]
---

## Description

Claude Code sessions burn token allocation on work that requires little or no reasoning:
reading large files to answer a narrow question, generating boilerplate test/config files,
and rewriting documentation after a session. This REQ introduces a "cheap worker" pattern
(per the pattern described in Kunal Bhardwaj's Medium article): three small CLI tools that
Claude invokes via its Bash tool to offload I/O-heavy work to **Kimi K2.5** (Moonshot AI,
OpenAI-compatible API), while reasoning, debugging, and safety-critical work stay on Claude.

The deliverables:

1. **`ask-kimi`** — bulk file reader. Takes a list of file paths and a question, packs the
   files into a corpus (files first, question last, to exploit Moonshot prefix caching),
   asks Kimi, prints a structured summary to stdout.
2. **`kimi-write`** — boilerplate generator. Takes a spec string, an optional reference/context
   file, and a target output path; Kimi generates the file and writes it to disk for Claude to
   review and surgically edit.
3. **`extract-chat`** — Claude Code session transcript cleaner. Reads a `~/.claude/projects/<proj>/<session>.jsonl`
   transcript and emits just the human-readable conversation text (no tool calls, system prompts,
   or binary data) to stdout or a target file. Feeds the doc-update pipeline (`extract-chat` →
   `ask-kimi` → Claude applies edits).
4. **Python venv** at a fixed path with the `openai` package installed; the three scripts are
   shebanged to that venv's interpreter so they run regardless of the active shell environment.
5. **`MOONSHOT_API_KEY` config** — exported from the user's shell rc; the API key value itself is
   supplied by the user, never committed.
6. **Global `~/.claude/CLAUDE.md` routing section** — instructs Claude when to delegate (files
   >~400 lines, 3+ files, boilerplate generation, doc updates) and, critically, when NOT to
   (architectural decisions, debugging, safety/security-critical code, tasks under ~2000 tokens,
   anything needing exact line numbers).
7. **`~/.claude/settings.json` allowlist entries** for `ask-kimi`, `kimi-write`, `extract-chat`
   so they don't trigger a permission prompt on every call.

A separate follow-up (out of scope here, see Out of Scope) wires delegation into specific ADLC
skills (`/wrapup` knowledge capture, `/analyze`, `/architect` context-reading).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| ask-kimi invocation | `paths` | string[] | required, ≥1 path, each must be a readable file |
| ask-kimi invocation | `question` | string | required |
| ask-kimi invocation | `max_tokens` | number | default 8192 (reading), must cover Kimi thinking + answer |
| kimi-write invocation | `spec` | string | required — description of what to generate |
| kimi-write invocation | `context` | string (path) | optional — reference file Kimi reads for patterns |
| kimi-write invocation | `target` | string (path) | required — output file path; parent dir must exist |
| kimi-write invocation | `max_tokens` | number | default 16384 (generation) |
| extract-chat invocation | `jsonl_path` | string (path) | required, must be a readable JSONL transcript |
| extract-chat invocation | `output` | string (path) | optional — defaults to stdout |
| env config | `MOONSHOT_API_KEY` | string (secret) | required at runtime; sourced from shell env; never logged |
| env config | venv path | string (path) | fixed location, contains `openai` package |
| env config | Moonshot base_url | string | `https://api.moonshot.ai/v1` |
| env config | model id | string | Kimi K2.5 model identifier |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| delegation call | Claude runs `ask-kimi`/`kimi-write` via Bash per CLAUDE.md routing | corpus + question / spec + context |
| empty-response guard trip | Kimi consumes entire `max_tokens` on internal reasoning, leaving no answer | tool exits non-zero with a clear diagnostic, not silent empty output |
| missing-key error | `MOONSHOT_API_KEY` unset when a tool runs | tool exits non-zero with an actionable message |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| run `ask-kimi` / `kimi-write` / `extract-chat` | local developer (allowlisted, no prompt) |
| edit `~/.claude/CLAUDE.md` routing section | toolkit maintainer |
| supply `MOONSHOT_API_KEY` value | user only (Claude never enters or reads the key value) |

## Business Rules

- [ ] BR-1: The three CLI tools MUST be invocable from any directory and any shell — achieved by
      shebanging to an absolute venv interpreter path, not relying on an activated venv or PATH order.
- [ ] BR-2: `ask-kimi` MUST place file contents BEFORE the question in the request message sequence
      so repeated questions against the same file set hit Moonshot's prefix cache.
- [ ] BR-3: Every tool MUST set `max_tokens` high enough to cover Kimi's internal "thinking" tokens
      plus the visible answer (defaults: 8192 read / 16384 generate), and MUST detect an empty
      completion and exit non-zero with a diagnostic rather than printing nothing.
- [ ] BR-4: No tool may print, log, or echo the `MOONSHOT_API_KEY` value; a missing key produces an
      actionable error, not a stack trace.
- [ ] BR-5: `extract-chat` output MUST exclude tool-call payloads, system prompts, and binary/base64
      blobs — only human + assistant natural-language turns.
- [ ] BR-6: The `~/.claude/CLAUDE.md` routing section MUST include an explicit "When NOT to delegate"
      list covering: architectural decisions, debugging, safety- and security-critical code, tasks
      under ~2000 tokens, and any task needing exact line numbers for editing.
- [ ] BR-7: `kimi-write` MUST write to the `target` path only and MUST NOT overwrite a file outside
      the requested target; Claude reviews the generated file before it is treated as final.
- [ ] BR-8: Adding the allowlist entries MUST NOT broaden any other permission in `~/.claude/settings.json`.

## Acceptance Criteria

- [ ] A Python venv exists at the documented fixed path with `openai` importable.
- [ ] `ask-kimi --paths <f1> <f2> --question "..."` returns a structured text summary using Kimi K2.5;
      verified against ≥2 real files totaling >400 lines.
- [ ] Running `ask-kimi` twice against the same file set with different questions demonstrably reuses
      the cached corpus prefix (observable via Moonshot usage/cost or response metadata).
- [ ] `kimi-write --spec "..." --context <ref> --target <out>` produces `<out>` on disk with content
      matching the spec; running it does not modify any file other than `<out>`.
- [ ] `extract-chat <session>.jsonl` emits clean conversation text with zero tool-call/system-prompt
      lines; piping its output into `ask-kimi` for a doc-update question works end to end.
- [ ] With `MOONSHOT_API_KEY` unset, each tool exits non-zero with a message naming the missing var.
- [ ] With `max_tokens` artificially low enough to be consumed by reasoning, the tool exits non-zero
      with an "empty completion" diagnostic rather than printing nothing.
- [ ] `~/.claude/CLAUDE.md` exists and contains the delegation routing section including the
      "When NOT to delegate" list from BR-6.
- [ ] `~/.claude/settings.json` allowlists the three commands; invoking them in a fresh Claude Code
      session produces no permission prompt, and no other permission entry changed (diff-verified).
- [ ] In a real Claude Code session, asking a multi-file codebase question causes Claude to self-route
      to `ask-kimi` based solely on the CLAUDE.md rules, with no extra prompting.

## External Dependencies

- **Moonshot AI Kimi K2.5 API** — OpenAI-compatible endpoint `https://api.moonshot.ai/v1`. User has
  already purchased credit. Requires `MOONSHOT_API_KEY`.
- **`openai` Python package** — installed into the dedicated venv.
- **Python 3** — system Python 3.9 is available; venv may use it or a newer interpreter if preferred.

## Assumptions

- The machine-global symlink install model means a `~/.claude/CLAUDE.md` change takes effect for every
  project immediately (consistent with the toolkit's install model).
- Kimi K2.5 exposes a "thinking"/reasoning mode whose tokens count against `max_tokens`; budgeting
  defaults of 8192/16384 are sufficient for typical read/generate tasks (tunable later).
- This REQ is `deployable: false` — it changes local dev environment + toolkit docs/skills, with no
  application deploy artifact.
- The repo home for tracking this work is `adlc-toolkit` because the follow-up wiring touches ADLC
  skills, even though the CLI tools and venv live under `~/bin` and `~/.claude` rather than in-repo.

## Open Questions

- [ ] OQ-1: Exact filesystem locations — confirm `~/bin/` for the scripts (already on PATH? user's PATH
      did not show `~/bin`, so PATH may need an entry) and the venv path (proposal: `~/.claude/kimi-venv/`).
- [ ] OQ-2: Where should `MOONSHOT_API_KEY` be set — `~/.zshrc` export (simplest), macOS Keychain +
      wrapper (more secure), or user-managed elsewhere?
- [ ] OQ-3: Should the three scripts and the CLAUDE.md routing block be version-controlled in
      `adlc-toolkit` (e.g., under a `tools/` dir + `templates/`) so they survive machine re-setup, or
      kept purely local?
- [ ] OQ-4: Exact Kimi K2.5 model identifier string for the `model=` parameter (article wrote
      `kimi-k2.5`; confirm against current Moonshot API docs).
- [ ] OQ-5: Should `kimi-write` refuse to run when `target` already exists (require `--force`), to
      prevent accidental clobber beyond what BR-7 covers?

## Out of Scope

- Wiring delegation into specific ADLC skills (`/wrapup` Step 4 knowledge capture, `/analyze` audits,
  `/architect` context-reading) — tracked as a follow-up REQ once the tools are proven.
- Per-project (non-global) CLAUDE.md routing variants.
- Supporting worker models other than Kimi K2.5 (DeepSeek, Gemini Flash, Qwen, etc.) — the pattern
  generalizes but this REQ ships only the Kimi path.
- Any automatic cost dashboard / usage reporting tooling.
- Routing reasoning, debugging, or safety/security-critical work to Kimi — explicitly prohibited by BR-6.
- Changes to consumer-project (`atelier-fashion`, etc.) repos.

## Retrieved Context

No prior context retrieved — no tagged documents matched this area.
