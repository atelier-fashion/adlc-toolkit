---
id: TASK-017
title: "CLAUDE.md delegation routing block, settings.json allowlist, README, conventions note"
status: complete
parent: REQ-412
created: 2026-05-12
updated: 2026-05-12
dependencies: [TASK-014, TASK-015, TASK-016]
---

## Description

Wire the tools into Claude Code's behavior: write the canonical delegation routing block into
`tools/kimi/README.md`, have `install.sh` append it to `~/.claude/CLAUDE.md` (idempotent, marker-guarded),
add allowlist entries for the three commands to `~/.claude/settings.json`, and add the `tools/`
carve-out note to the repo conventions doc.

## Files to Create/Modify

- `tools/kimi/README.md` — full setup guide + the canonical CLAUDE.md routing block (between
  `<!-- kimi-delegation:start -->` / `<!-- kimi-delegation:end -->` markers). The block contains:
  - `### ask-kimi — bulk reading` — when to use (files >~400 lines, or 3+ files); usage line; "use the
    summary instead of reading the files yourself".
  - `### kimi-write — boilerplate generation` — when to use (tests, config, docstrings, repetitive
    patterns); usage line; "then review and edit only what needs fixing".
  - `### Documentation workflow` — `extract-chat` → `ask-kimi` → apply edits; "prefer this over
    re-reading the conversation and rewriting docs directly".
  - `### When NOT to delegate` — MANDATORY list: tasks under ~2000 tokens; architectural decisions;
    debugging; safety- and security-critical code; anything needing exact line numbers for editing.
    One-line summary: "Claude = thinking. Kimi = I/O."
- `tools/kimi/install.sh` (MODIFY, from TASK-013) — add a step that appends the routing block from
  README between the markers to `~/.claude/CLAUDE.md` (create the file if absent); skip if the markers
  are already present. Add a step that merges the three allowlist entries into `~/.claude/settings.json`
  using a Python one-liner against the venv interpreter (parse JSON, add missing entries to the
  permissions allow list, write back) — idempotent, and it must NOT alter any other key.
- `.adlc/context/conventions.md` (MODIFY) — add the `tools/` exception note under "Code is markdown,
  not code" (text in architecture.md "Proposed addition").
- `README.md` (repo root, MODIFY) — add a one-line pointer to `tools/kimi/README.md` in the catalog.

## Acceptance Criteria

- [ ] `tools/kimi/README.md` contains the routing block with all four sections, including the
      "When NOT to delegate" list with all five items.
- [ ] After `install.sh`, `~/.claude/CLAUDE.md` contains the marker-delimited routing block exactly once;
      a second `install.sh` run does not duplicate it.
- [ ] After `install.sh`, `~/.claude/settings.json` allowlists `ask-kimi`, `kimi-write`, `extract-chat`;
      a diff against the pre-run file shows ONLY those additions, no other key changed; re-running does
      not add duplicates.
- [ ] In a fresh Claude Code session (consumer project), invoking the three commands produces no
      permission prompt.
- [ ] In a real Claude Code session, asking a multi-file codebase question causes Claude to self-route
      to `ask-kimi` based solely on the CLAUDE.md rules, with no extra prompting.
- [ ] `.adlc/context/conventions.md` has the `tools/` carve-out note; repo `README.md` references
      `tools/kimi/`.

## Technical Notes

- The settings.json merge MUST be structure-preserving: load with `json` (or `json5` if the file has
  comments — check first; Claude Code `settings.json` is plain JSON), append to the existing
  `permissions.allow` array only if absent, `json.dump` with `indent=2`. Back up to `settings.json.bak`
  before writing.
- Marker-guarded append pattern: `grep -q 'kimi-delegation:start' ~/.claude/CLAUDE.md || cat block >> ...`.
- Do NOT broaden any existing permission (spec BR-8) — only add the three specific command entries.
- Keep the routing block tight; the "When NOT to delegate" section is the load-bearing part — make it
  unambiguous so Claude doesn't over-route reasoning work to Kimi (spec BR-6).
