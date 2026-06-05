---
id: TASK-075
title: "Rewrite architect footprint-publish: derive per-repo from tasks, iterate all PRs, move after task creation"
status: complete
parent: REQ-484
created: 2026-06-05
updated: 2026-06-05
dependencies: []
# repo omitted — single-repo project; attributes to primary (adlc-toolkit)
---

## Description

Close the cross-repo write-side gap in `/architect` footprint publishing (REQ-484 core).
Three coupled changes to `architect/SKILL.md`:

1. **Move the publish step after task creation (OQ-1, ADR-2).** The footprint-publish step
   currently lives at Step 2 ("Explore the Codebase") item 3 — BEFORE Step 4 creates the task
   files. Move it to a new step that runs AFTER Step 4, so per-repo `repo:` attribution from
   tasks is available. Renumber downstream steps accordingly.
2. **Derive each repo's footprint from task files, not the architecture-mapper output
   (BR-1, BR-6, ADR-1).** For each touched repo, the footprint is the union of
   `## Files to Create/Modify` paths across tasks whose `repo:` frontmatter equals that repo
   id. A task with NO `repo:` field attributes to the **primary** repo (single-repo projects
   omit `repo:`), so single-repo REQs derive from tasks via this same path — NOT via the BR-4
   mapper-fallback.
3. **Publish to EVERY touched repo's PR, not just the first (BR-2, BR-3).** Replace the
   `prnum=$(… | head -1)` selection with a loop over every `repos[*].prNumber` recorded in
   `pipeline-state.json`. Each PR receives ONLY its own repo's lines, repo-qualified
   `<repo-id>:<path-or-glob>`, in a single fenced `adlc-footprint` block (idempotent — replace
   any prior block).

Plus the supporting rules: graceful degradation (BR-4), sanitization parity (BR-5), single-repo
equivalence (BR-3).

## Files to Create/Modify

- `architect/SKILL.md` — Move the footprint-publish step from Step 2 item 3 to a new Step 5
  (after Step 4 "Break Into Tasks"); renumber old Step 5 (Update Status) → Step 6 and old
  Step 6 (Present for Review) → Step 7. Rewrite the publish shell block to: (a) read each
  touched repo's `prNumber` from `pipeline-state.json` and loop over all of them (no `head -1`);
  (b) derive that repo's path set from task files grouped by `repo:` (absent `repo:` → primary);
  (c) sanitize each emitted line (charset `^[A-Za-z0-9_.-]*:?[A-Za-z0-9_./*-]+$`, reject `..`);
  (d) skip a repo with zero attributable files with a one-line note (never an empty block);
  (e) fall back to architecture-mapper paths attributed to primary with a
  `source: mapper-fallback` notice when a task has no file list or a repo has no attributing
  tasks; (f) keep the standalone-`/architect` skip-with-note behavior (no draft PR → skip).

## Acceptance Criteria

- [ ] The footprint-publish step runs AFTER task files are created within the same `/architect`
      invocation (resolves OQ-1). The old Step 2 item 3 publish block is gone; a new step after
      Step 4 holds it. Downstream steps are renumbered consistently (Update Status, Present).
- [ ] The publish loop iterates EVERY touched repo's `prNumber` from `pipeline-state.json`
      (`repos[*].prNumber`), not `head -1`. Each PR gets only its own repo's repo-qualified
      lines in one fenced `adlc-footprint` block (idempotent replace).
- [ ] Per-repo footprint is derived from task files: union of `## Files to Create/Modify` paths
      across tasks whose `repo:` equals the repo id; a `repo:`-absent task attributes to the
      primary repo (BR-1, BR-6).
- [ ] Single-repo REQs degenerate to one repo / one PR / one block, derived from tasks via BR-1
      (NOT the mapper-fallback, never flagged "coarse") — equivalent in intent to REQ-483 (BR-3).
- [ ] Every emitted line passes charset validation `^[A-Za-z0-9_.-]*:?[A-Za-z0-9_./*-]+$` and
      contains no `..`, BEFORE being written to any PR body (BR-5, LESSON-008).
- [ ] A task missing a file list, or a touched repo with no attributing tasks, degrades to the
      architecture-mapper paths attributed to primary with a one-line `source: mapper-fallback`
      notice; a repo with genuinely zero attributable files is skipped with a note — never an
      empty block (BR-4).
- [ ] Standalone `/architect` (no `/proceed`, no draft PR) still skips publishing with a
      one-line note (REQ-483 behavior preserved).
- [ ] The new shell block is split-free (newline iteration via `printf '%s\n' | while read -r`,
      no unquoted word-splitting) so it behaves identically under sh and zsh (LESSON-329), uses
      `mktemp` + EXIT trap for any temp file, and passes `tools/lint-skills` if present.

## Technical Notes

- **Parsing task `repo:`**: read each `tasks/TASK-*.md` frontmatter `repo:` field; if absent or
  commented, treat as primary. Determine the primary repo id from `pipeline-state.json`
  (`repos.<id>.primary == true`).
- **Parsing the Files list**: extract bullet lines under the `## Files to Create/Modify`
  heading. Each bullet is `` - `path` — description ``; capture the backtick-quoted path (or the
  first whitespace-delimited token if not backtick-quoted). Strip the description after `—`.
- **Reuse the existing block's idioms**: `tick=$(printf '\140\140\140')`,
  `mktemp "${TMPDIR:-/tmp}/footprint.XXXXXX"`, `trap 'rm -f "$tmp"' EXIT`,
  `sed "/^${tick}adlc-footprint/,/^${tick}/d"` to strip the prior block, then re-append the new
  block. These are already correct in the current block — preserve them.
- **Iterating prNumbers**: parse all `prNumber` values + their owning repo ids from
  `pipeline-state.json`. Keep the parse robust (the current `sed -n 's/.*"prNumber"...'` grabs
  numbers but loses repo association — switch to a per-repo parse, e.g. iterate repo ids then
  pull each repo's `prNumber` and `primary` flag).
- **Sanitization (BR-5)**: identical to the read side in `manifest/SKILL.md` — reject lines with
  `..`, then `grep -E '^[A-Za-z0-9_.-]*:?[A-Za-z0-9_./*-]+$'`. The current block already does
  `grep -vE '\.\.' | grep -E '...'` — keep that, applied per repo.
- **Do NOT** broadcast a path to all PRs or infer a repo from the path string (BR-6) — repo is
  decided solely by the task's `repo:` tag.
- **Keep it markdown-only** — this is a SKILL.md edit; no executable code, no new partial.
