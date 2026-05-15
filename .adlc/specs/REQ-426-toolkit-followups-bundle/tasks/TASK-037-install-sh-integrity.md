---
id: TASK-037
title: "Hash-pin install.sh CLAUDE.md routing block"
status: draft
parent: REQ-426
created: 2026-05-15
updated: 2026-05-15
dependencies: []
---

## Description

Resolve REQ-426 BR-1 (ADR-1). Extract the CLAUDE.md routing block out of
`tools/kimi/README.md` into a dedicated canonical file and pin its SHA-256.
`install.sh` recomputes and refuses to write on mismatch.

## Files to Create/Modify

- `tools/kimi/claude-md-routing.txt` — NEW. The canonical routing block,
  currently extracted from the `kimi-delegation:start` / `kimi-delegation:end`
  markers in `tools/kimi/README.md`. Copy that block content verbatim.
- `tools/kimi/claude-md-routing.txt.sha256` — NEW. Single-line file
  containing the SHA-256 hex digest of `claude-md-routing.txt`. Generate
  with `shasum -a 256 tools/kimi/claude-md-routing.txt | awk '{print $1}' > tools/kimi/claude-md-routing.txt.sha256`.
- `tools/kimi/install.sh` — MODIFIED. Replace the sed-extraction-from-README
  logic with: (a) recompute hash of `claude-md-routing.txt`, (b) compare
  to pinned hash, (c) refuse with clear error on mismatch, (d) on match,
  `cat` the file's contents into the marker-guarded append block in
  `~/.claude/CLAUDE.md` (existing logic for the marker guard stays
  unchanged).
- `tools/kimi/README.md` — MODIFIED. Replace the inline routing block
  between the start/end markers with a one-line pointer to
  `claude-md-routing.txt`. Document the hash-pin workflow in a new
  "Updating the Claude routing block" subsection: edit the .txt file,
  regenerate the .sha256 with the documented `shasum` command, commit
  both in one PR. Reviewers see the diff in both files.

## Acceptance Criteria

- [ ] `tools/kimi/claude-md-routing.txt` exists with the routing block
      content.
- [ ] `tools/kimi/claude-md-routing.txt.sha256` exists with the matching
      digest.
- [ ] `tools/kimi/install.sh` reads from the .txt file and validates the
      hash before any write to `~/.claude/CLAUDE.md`.
- [ ] Tampering test: modify `claude-md-routing.txt` without updating the
      .sha256, re-run `install.sh`, confirm it exits non-zero with a
      clear error AND does NOT modify `~/.claude/CLAUDE.md`.
- [ ] Normal-flow test: from a clean state, run `install.sh`, confirm
      hash matches and the marker-guarded append happens once.
- [ ] Idempotency test: run `install.sh` twice, confirm no double-append
      (existing marker guard handles this — verify still works).
- [ ] `tools/kimi/README.md` documents the bump workflow.
- [ ] REQ-413 pytest suite still passes (BR-8 inherited from REQ-416).

## Technical Notes

- Use `shasum -a 256` (BSD-compatible, present on macOS); fall back to
  `sha256sum` (Linux). Detect with `command -v`:
  ```sh
  if command -v shasum >/dev/null 2>&1; then
    HASH_CMD="shasum -a 256"
  else
    HASH_CMD="sha256sum"
  fi
  ACTUAL_HASH=$($HASH_CMD "$REPO_ROOT/tools/kimi/claude-md-routing.txt" | awk '{print $1}')
  ```
- Pinned hash read with `cat`, trimmed of whitespace.
- Refuse pattern:
  ```sh
  if [ "$ACTUAL_HASH" != "$PINNED_HASH" ]; then
    echo "ERROR: claude-md-routing.txt hash mismatch — refusing to modify ~/.claude/CLAUDE.md" >&2
    echo "  Pinned:   $PINNED_HASH" >&2
    echo "  Computed: $ACTUAL_HASH" >&2
    echo "  If this change is intentional, update tools/kimi/claude-md-routing.txt.sha256 in the same commit." >&2
    exit 1
  fi
  ```
- The marker-guarded append logic (`# kimi-delegation:start` / `:end`)
  already prevents double-appends in `~/.claude/CLAUDE.md`. Leave it
  intact — this task only changes the SOURCE of the appended content.
- POSIX-only, no GNU-specific flags.
